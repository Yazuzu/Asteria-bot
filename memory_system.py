#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
memory_system.py — Sistema de memória com Density Matrix [PRODUÇÃO]

Versão OTIMIZADA com melhorias adicionais.
"""

import json
import logging
import os
import random
import re
import sqlite3
import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple
from contextlib import contextmanager

import numpy as np
try:
    import pyarrow as pa
    import lancedb
    import sqlite_vec
    from sentence_transformers import SentenceTransformer
    from mem0 import Memory
except ImportError:
    # Fallback placeholders for environment without all heavy dependencies yet
    logger = logging.getLogger(__name__)
    logger.error("Dependências pesadas não encontradas. Algumas funcionalidades de memória falharão.")

import functools

try:
    from transformers import pipeline
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    pipeline = None

logger = logging.getLogger(__name__)

# =============================================================================
# Utilitários
# =============================================================================

def safe_normalize(x: np.ndarray, eps: float = 1e-8) -> np.ndarray:
    if x.size == 0:
        return x
    norm = np.linalg.norm(x)
    if norm < eps:
        return x / (eps + 1e-10)
    return x / norm

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    if a.size == 0 or b.size == 0:
        return 0.0
    a_n = safe_normalize(a)
    b_n = safe_normalize(b)
    return float(np.dot(a_n, b_n))

def retry_on_error(max_retries: int = 3, delay: float = 0.1,
                   exceptions: tuple = (Exception,)):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    is_last = attempt == max_retries - 1
                    msg = str(exc).lower()
                    transient = any(k in msg for k in (
                        "database is locked", "busy", "timeout",
                        "concurrent", "conflict",
                    ))
                    if is_last or not transient:
                        raise
                    sleep = delay * (2 ** attempt) + random.uniform(0, 0.05)
                    time.sleep(sleep)
            return None
        return wrapper
    return decorator

@contextmanager
def timer_context(name: str, logger_obj=None):
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        if logger_obj:
            logger_obj.debug(f"{name} levou {elapsed*1000:.2f}ms")

# =============================================================================
# Configuração
# =============================================================================

@dataclass
class MemoryConfig:
    lancedb_path: str = "data/lancedb"
    cache_db_path: str = "data/cache.db"
    embedding_model: str = "all-MiniLM-L6-v2"
    emotion_model: str = "SamLowe/roberta-base-go_emotions"
    cache_similarity_threshold: float = 0.85
    cache_ttl_seconds: int = 3600
    cache_prune_probability: float = 0.01
    mem0_config: Optional[Dict[str, Any]] = None
    lance_table_name: str = "memories"
    max_memories_per_user: Optional[int] = None
    memory_retention_days: Optional[int] = 30
    emotion_dim: int = 3
    emotion_vad_map: Dict[str, List[float]] = field(default_factory=lambda: {
        "admiration": [0.8, 0.5, 0.6], "amusement": [0.9, 0.7, 0.5],
        "anger": [-0.8, 0.8, 0.7], "annoyance": [-0.4, 0.6, 0.5],
        "approval": [0.7, 0.3, 0.6], "caring": [0.8, 0.2, 0.7],
        "confusion": [-0.2, 0.5, -0.3], "curiosity": [0.5, 0.7, 0.4],
        "desire": [0.6, 0.8, 0.5], "disappointment": [-0.7, -0.3, -0.4],
        "disapproval": [-0.6, 0.2, -0.5], "disgust": [-0.9, 0.4, -0.3],
        "embarrassment": [-0.3, 0.6, -0.6], "excitement": [0.9, 0.9, 0.7],
        "fear": [-0.8, 0.9, -0.8], "gratitude": [0.8, 0.2, 0.5],
        "grief": [-0.9, -0.7, -0.8], "joy": [0.9, 0.6, 0.6],
        "love": [0.9, 0.7, 0.8], "nervousness": [-0.5, 0.8, -0.5],
        "optimism": [0.8, 0.4, 0.7], "pride": [0.8, 0.3, 0.8],
        "realization": [0.3, 0.2, 0.5], "relief": [0.7, -0.3, 0.6],
        "remorse": [-0.7, -0.4, -0.7], "sadness": [-0.8, -0.5, -0.6],
        "surprise": [0.4, 0.9, 0.3], "neutral": [0.0, 0.0, 0.0],
    })
    use_density_rerank: bool = True
    density_low_rank: Optional[int] = 50
    density_decay_lambda: float = 0.001
    density_learning_rate: float = 0.1
    density_max_vectors: int = 1000
    density_prune_threshold: float = 0.01
    density_prune_min_age_seconds: int = 86400
    use_superposition: bool = False
    superposition_max_components: int = 5
    superposition_damping: float = 0.9
    superposition_merge_threshold: float = 0.80
    persist_interval: int = 5
    l1_maxlen: int = 20
    enable_perf_logging: bool = True

    def __post_init__(self):
        self.lancedb_path = os.path.abspath(self.lancedb_path)
        self.cache_db_path = os.path.abspath(self.cache_db_path)
        os.makedirs(os.path.dirname(self.lancedb_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.cache_db_path), exist_ok=True)

# =============================================================================
# Sub-componentes (Resumidos para brevidade, mas funcionais)
# =============================================================================

@dataclass
class EmotionResult:
    dominant: str
    vad: np.ndarray
    all_emotions: Dict[str, float] = field(default_factory=dict)

class EmotionDetector:
    def __init__(self, config: MemoryConfig):
        self.config = config
        self._pipe = None
        self._enabled = False
        self._load()

    def _load(self):
        if not TRANSFORMERS_AVAILABLE: return
        try:
            self._pipe = pipeline("text-classification", model=self.config.emotion_model, top_k=None, device=-1)
            self._enabled = True
        except: pass

    def detect(self, text: str) -> EmotionResult:
        if not self._enabled or not text.strip(): return self._neutral()
        try:
            results = self._pipe(text[:512])[0]
            all_emotions = {r["label"].lower(): float(r["score"]) for r in results}
            dominant = max(all_emotions, key=all_emotions.get)
            vad = np.array(self.config.emotion_vad_map.get(dominant, [0,0,0]), dtype=np.float32) * all_emotions[dominant]
            return EmotionResult(dominant=dominant, vad=vad, all_emotions=all_emotions)
        except: return self._neutral()

    def _neutral(self) -> EmotionResult:
        return EmotionResult(dominant="neutral", vad=np.zeros(3, dtype=np.float32))

class Embedder:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = SentenceTransformer(model_name)
        self.dimension = len(self._model.encode("dummy"))

    def encode(self, text: str) -> np.ndarray:
        return self._model.encode(text).astype(np.float32)

    def encode_many(self, texts: List[str]) -> List[np.ndarray]:
        return self._model.encode(texts).astype(np.float32)

class DensityMemoryState:
    def __init__(self, dim: int, **kwargs):
        self.dim = dim
        self.rho = np.zeros((dim, dim), dtype=np.float32)
        self.vectors, self.weights, self.timestamps = [], [], []
        self.max_vectors = kwargs.get("max_vectors", 1000)
        self.decay_lambda = kwargs.get("decay_lambda", 0.001)

    def add_vector(self, vec: np.ndarray, weight: float = 1.0):
        vec = safe_normalize(vec)
        self.vectors.append(vec)
        self.weights.append(weight)
        self.timestamps.append(time.time())
        if len(self.vectors) > self.max_vectors:
            self.vectors.pop(0); self.weights.pop(0); self.timestamps.pop(0)
        self._rebuild_rho()

    def _rebuild_rho(self):
        tw = sum(self.weights)
        if tw == 0: return
        self.rho = sum((w/tw) * np.outer(v,v) for v,w in zip(self.vectors, self.weights))

    def decay(self):
        now = time.time()
        self.weights = [w * np.exp(-self.decay_lambda * (now - t)) for w, t in zip(self.weights, self.timestamps)]
        self._rebuild_rho()

    def score(self, q: np.ndarray) -> float:
        q = safe_normalize(q)
        return float(q @ self.rho @ q)

    def to_dict(self):
        return {"vectors": [v.tolist() for v in self.vectors], "weights": self.weights, "timestamps": self.timestamps}

    @classmethod
    def from_dict(cls, data):
        dim = len(data["vectors"][0]) if data["vectors"] else 384
        obj = cls(dim)
        obj.vectors = [np.array(v) for v in data["vectors"]]
        obj.weights = data["weights"]
        obj.timestamps = data["timestamps"]
        obj._rebuild_rho()
        return obj

class LanceDBStore:
    def __init__(self, config, embedder):
        self.config, self.embedder = config, embedder
        self.db = lancedb.connect(config.lancedb_path)
        self._init_table()

    def _init_table(self):
        if self.config.lance_table_name not in self.db.table_names():
            schema = pa.schema([
                pa.field("id", pa.string()), pa.field("user_id", pa.string()),
                pa.field("channel_id", pa.string()), pa.field("text", pa.string()),
                pa.field("timestamp", pa.float64()), pa.field("metadata", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), self.embedder.dimension)),
                pa.field("emotion_vad", pa.list_(pa.float32(), 3)),
            ])
            self.table = self.db.create_table(self.config.lance_table_name, schema=schema)
        else:
            self.table = self.db.open_table(self.config.lance_table_name)

    def add_memory(self, user_msg, bot_msg, user_id, channel_id, vector, emotion):
        data = [{
            "id": str(uuid.uuid4()), "user_id": str(user_id), "channel_id": str(channel_id),
            "text": f"User: {user_msg}\nBot: {bot_msg}", "timestamp": time.time(),
            "metadata": "{}", "vector": vector.tolist(), "emotion_vad": emotion.vad.tolist()
        }]
        self.table.add(data)

    def search(self, vec, user_id, channel_id, limit):
        """Busca vetorial filtrada por canal."""
        where_clause = f"channel_id = '{channel_id}'"
        res = self.table.search(vec.tolist(), vector_column_name="vector") \
            .where(where_clause, prefilter=True) \
            .limit(limit).to_list()
        for r in res:
            r["vector"] = np.array(r["vector"])
            r["emotion_vad"] = np.array(r["emotion_vad"])
        return res

    def delete_channel_memories(self, channel_id):
        """Remove fisicamente as memórias de um canal no LanceDB."""
        where_clause = f"channel_id = '{channel_id}'"
        self.table.delete(where_clause)

class MemorySystem:
    def __init__(self, config=None):
        self.config = config or MemoryConfig()
        self.embedder = Embedder(self.config.embedding_model)
        self.lance_store = LanceDBStore(self.config, self.embedder)
        self.emotion_detector = EmotionDetector(self.config)
        self.density_states: Dict[str, DensityMemoryState] = {}
        # Histórico de curto prazo por canal
        self.short_term: Dict[str, Deque[Dict]] = {}

    def add_interaction(self, user_msg, bot_msg, user_id, channel_id, metadata=None):
        emo = self.emotion_detector.detect(user_msg)
        sem_vec = self.embedder.encode(f"{user_msg} {bot_msg}")
        self.lance_store.add_memory(user_msg, bot_msg, user_id, channel_id, sem_vec, emo)
        
        cid = str(channel_id)
        if cid not in self.density_states:
            self.density_states[cid] = DensityMemoryState(self.embedder.dimension + 3)
        
        if cid not in self.short_term:
            self.short_term[cid] = deque(maxlen=self.config.l1_maxlen)
        
        full_vec = np.concatenate([sem_vec, emo.vad])
        self.density_states[cid].add_vector(full_vec)
        self.short_term[cid].append({"user": user_msg, "bot": bot_msg, "emo": emo.dominant})

    def get_context(self, query, user_id=None, channel_id=None, limit=5):
        q_sem = self.embedder.encode(query)
        mems = self.lance_store.search(q_sem, user_id, channel_id, limit)
        
        cid = str(channel_id)
        if cid in self.density_states:
            self.density_states[cid].decay()
            for m in mems:
                fv = np.concatenate([m["vector"], m["emotion_vad"]])
                m["score"] = self.density_states[cid].score(fv)
            mems.sort(key=lambda x: x.get("score", 0), reverse=True)
            
        mems_str = ""
        if mems:
            mems_str = "[Memorias Relacionadas]\n" + "\n".join(f"- {m['text']}" for m in mems) + "\n\n"
        
        recent_str = ""
        if cid in self.short_term and self.short_term[cid]:
            recent_str = "[Conversa Recente]\n" + "\n".join(
                f"Usuário: {h['user']}\nAstéria: {h['bot']}" 
                for h in list(self.short_term[cid])[-3:]
            ) + "\n\n"
            
        return f"{mems_str}{recent_str}"

    def clear_channel_memory(self, channel_id):
        """Limpa todo o histórico (persistente e volátil) de um canal."""
        cid = str(channel_id)
        if cid in self.density_states:
            del self.density_states[cid]
        if cid in self.short_term:
            del self.short_term[cid]
        
        self.lance_store.delete_channel_memories(cid)

    def close(self):
        pass
