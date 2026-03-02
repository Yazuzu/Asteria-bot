"""
memory_system.py — Sistema de memória com Density Matrix v2.3.
Adaptado para estrutura flat.
"""
from __future__ import annotations

import functools
import json
import logging
import random
import sqlite3
import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor, Future
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple

import numpy as np
import config

# Configuração de Logs local
logger = logging.getLogger("asteria.memory")

# ─────────────────────────────────────────────────────────────────────────────
# Exceções customizadas
# ─────────────────────────────────────────────────────────────────────────────

class MemorySystemError(Exception):
    """Exceção base do sistema de memória."""

class EmbeddingError(MemorySystemError):
    """Falha ao gerar embeddings."""

class StorageError(MemorySystemError):
    """Falha ao acessar armazenamento (LanceDB, SQLite)."""

# ─────────────────────────────────────────────────────────────────────────────
# Utilitários
# ─────────────────────────────────────────────────────────────────────────────

def _norm(x: np.ndarray, eps: float = 1e-8) -> np.ndarray:
    n = np.linalg.norm(x)
    return x / (n if n >= eps else eps)

def retry_on_error(max_retries: int = 3, delay: float = 0.1, exceptions: tuple = (Exception,)):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    is_last = attempt == max_retries - 1
                    msg = str(exc).lower()
                    transient = any(k in msg for k in ("locked", "busy", "timeout", "concurrent", "conflict"))
                    if is_last or not transient: raise
                    wait = delay * (2 ** attempt) + random.uniform(0.0, 0.05)
                    time.sleep(wait)
            return None
        return wrapper
    return decorator

@contextmanager
def _timer(name: str):
    t0 = time.perf_counter()
    try: yield
    finally: logger.debug(f"[timer] {name}: {(time.perf_counter()-t0)*1000:.1f}ms")

# ─────────────────────────────────────────────────────────────────────────────
# VAD map — go_emotions → [valence, arousal, dominance]
# ─────────────────────────────────────────────────────────────────────────────

_VAD: Dict[str, List[float]] = {
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
}
_VAD_NEUTRAL = np.zeros(3, dtype=np.float32)

# ─────────────────────────────────────────────────────────────────────────────
# EmotionResult + EmotionDetector
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EmotionResult:
    dominant: str = "neutral"
    score: float = 0.0
    vad: np.ndarray = field(default_factory=lambda: _VAD_NEUTRAL.copy())
    all_emotions: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def neutral(cls) -> "EmotionResult":
        return cls(dominant="neutral", score=0.0, vad=_VAD_NEUTRAL.copy(), all_emotions={"neutral": 1.0})

    def vad_list(self) -> List[float]:
        return self.vad.tolist()

class EmotionDetector:
    _inst: Optional["EmotionDetector"] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._inst is None:
                o = super().__new__(cls)
                o._pipe = None
                o._ready = False
                o._load()
                cls._inst = o
        return cls._inst

    def _load(self):
        try:
            from transformers import pipeline
            logger.info(f"Carregando emotion model: {config.EMOTION_MODEL}")
            self._pipe = pipeline("text-classification", model=config.EMOTION_MODEL, top_k=None, truncation=True, max_length=128, device=-1)
            self._ready = True
        except Exception as exc:
            logger.warning(f"EmotionDetector indisponível ({exc}). Fallback neutro.")

    def detect(self, text: str) -> EmotionResult:
        if not self._ready or not text.strip(): return EmotionResult.neutral()
        try:
            raw = self._pipe(text[:512])
            items = raw[0] if isinstance(raw[0], list) else raw
            em = {r["label"].lower(): float(r["score"]) for r in items}
            dom = max(em, key=em.get)
            base = np.array(_VAD.get(dom, [0.0, 0.0, 0.0]), dtype=np.float32)
            return EmotionResult(dominant=dom, score=em[dom], vad=base * em[dom], all_emotions=em)
        except: return EmotionResult.neutral()

# ─────────────────────────────────────────────────────────────────────────────
# Embedder
# ─────────────────────────────────────────────────────────────────────────────

class Embedder:
    _inst: Optional["Embedder"] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._inst is None:
                o = super().__new__(cls)
                o._model = None
                o._dim = None
                o._load()
                cls._inst = o
        return cls._inst

    def _load(self):
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Carregando embedding: {config.EMBEDDING_MODEL}")
            self._model = SentenceTransformer(config.EMBEDDING_MODEL)
            self._dim = int(self._model.encode("x").shape[0])
        except Exception as exc:
            raise EmbeddingError(f"Falha ao carregar {config.EMBEDDING_MODEL}: {exc}")

    @property
    def dim(self) -> int: return self._dim

    def encode(self, text: str) -> np.ndarray:
        if not text.strip(): return np.zeros(self._dim, dtype=np.float32)
        return self._model.encode(text, normalize_embeddings=True).astype(np.float32)

    def encode_batch(self, texts: List[str]) -> List[np.ndarray]:
        if not texts: return []
        return [v.astype(np.float32) for v in self._model.encode(texts, normalize_embeddings=True)]

# ─────────────────────────────────────────────────────────────────────────────
# DensityMemoryState
# ─────────────────────────────────────────────────────────────────────────────

class DensityMemoryState:
    def __init__(self, dim: int, low_rank: int = 50, decay_lambda: float = 0.001, max_vectors: int = 1000, prune_threshold: float = 0.01, prune_min_age_sec: int = 86400):
        self.dim = dim
        self.rho = np.zeros((dim, dim), dtype=np.float32)
        self._vecs, self._wts, self._times = [], [], []
        self.low_rank, self.decay_lambda, self.max_vectors = low_rank, decay_lambda, max_vectors
        self.prune_threshold, self.prune_min_age_sec = prune_threshold, prune_min_age_sec

    def add_vector(self, vec: np.ndarray, weight: float = 1.0):
        self._vecs.append(_norm(vec))
        self._wts.append(weight)
        self._times.append(time.time())
        if len(self._vecs) > self.max_vectors: self._prune()
        self._rebuild()

    def decay(self):
        now = time.time()
        self._wts = [w * float(np.exp(-self.decay_lambda * max(0.0, now - t))) for w, t in zip(self._wts, self._times)]
        self._rebuild()

    def apply_feedback(self, vec: np.ndarray, eta: float = 0.1):
        v = _norm(vec)
        self.rho = (1.0 - abs(eta)) * self.rho + abs(eta) * np.outer(v, v)
        if eta > 0: self.add_vector(vec, weight=abs(eta))

    def score(self, query: np.ndarray) -> float:
        q = _norm(query)
        return float(q @ self.rho @ q)

    def _prune(self):
        now = time.time()
        cutoff = now - self.prune_min_age_sec
        keep = [i for i, (w, t) in enumerate(zip(self._wts, self._times)) if w >= self.prune_threshold or t > cutoff]
        if len(keep) > self.max_vectors:
            keep = [i for _, i in sorted([(self._times[i], i) for i in keep], reverse=True)[:self.max_vectors]]
        self._vecs = [self._vecs[i] for i in keep]
        self._wts = [self._wts[i] for i in keep]
        self._times = [self._times[i] for i in keep]

    def _rebuild(self):
        total = sum(self._wts)
        if total == 0:
            self.rho = np.zeros((self.dim, self.dim), dtype=np.float32)
            return
        rho = np.zeros((self.dim, self.dim), dtype=np.float32)
        for v, w in zip(self._vecs, self._wts): rho += (w / total) * np.outer(v, v)
        self.rho = rho.astype(np.float32)
        if 0 < self.low_rank < self.dim: self._svd()

    def _svd(self):
        try:
            U, S, Vt = np.linalg.svd(self.rho, full_matrices=False)
            r = min(self.low_rank, len(S))
            self.rho = ((U[:, :r] * S[:r]) @ Vt[:r, :]).astype(np.float32)
        except: pass

    def to_dict(self) -> Dict:
        return {"dim": self.dim, "low_rank": self.low_rank, "decay_lambda": self.decay_lambda, "max_vectors": self.max_vectors, "prune_threshold": self.prune_threshold, "prune_min_age_sec": self.prune_min_age_sec, "vectors": [v.tolist() for v in self._vecs], "weights": self._wts, "timestamps": self._times}

    @classmethod
    def from_dict(cls, d: Dict) -> "DensityMemoryState":
        vecs = d.get("vectors", [])
        obj = cls(dim=d.get("dim", len(vecs[0]) if vecs else 1), low_rank=d.get("low_rank", 50), decay_lambda=d.get("decay_lambda", 0.001), max_vectors=d.get("max_vectors", 1000), prune_threshold=d.get("prune_threshold", 0.01), prune_min_age_sec=d.get("prune_min_age_sec", 86400))
        obj._vecs = [np.array(v, dtype=np.float32) for v in vecs]
        obj._wts, obj._times = d.get("weights", []), d.get("timestamps", [])
        obj._rebuild()
        return obj

# ─────────────────────────────────────────────────────────────────────────────
# LanceDB Store
# ─────────────────────────────────────────────────────────────────────────────

class LanceStore:
    _tbl_lock = threading.Lock()

    def __init__(self, embedder: Embedder):
        import lancedb
        import pyarrow as pa
        self._pa = pa
        self._db = lancedb.connect(config.LANCEDB_PATH)
        self._embedder = embedder
        self._table = self._init()

    def _init(self):
        dim, name = self._embedder.dim, "memories"
        with self._tbl_lock:
            if name not in self._db.table_names():
                schema = self._pa.schema([
                    self._pa.field("id", self._pa.string()),
                    self._pa.field("user_id", self._pa.string()),
                    self._pa.field("channel_id", self._pa.string()),
                    self._pa.field("user_msg", self._pa.string()),
                    self._pa.field("bot_msg", self._pa.string()),
                    self._pa.field("text", self._pa.string()),
                    self._pa.field("timestamp", self._pa.float64()),
                    self._pa.field("metadata", self._pa.string()),
                    self._pa.field("vector", self._pa.list_(self._pa.float32(), dim)),
                    self._pa.field("emotion", self._pa.string()),
                    self._pa.field("emotion_vad", self._pa.list_(self._pa.float32(), 3)),
                ])
                tbl = self._db.create_table(name, schema=schema)
            else: tbl = self._db.open_table(name)
        return tbl

    @retry_on_error()
    def add(self, user_msg: str, bot_msg: str, user_id: int, channel_id: int, vector: np.ndarray, emotion: EmotionResult, metadata: Optional[Dict] = None):
        row = [{
            "id": str(uuid.uuid4()), "user_id": str(user_id), "channel_id": str(channel_id),
            "user_msg": user_msg, "bot_msg": bot_msg, "text": f"Usuário: {user_msg}\nAstéria: {bot_msg}",
            "timestamp": time.time(), "metadata": json.dumps(metadata or {}),
            "vector": vector.tolist(), "emotion": emotion.dominant, "emotion_vad": emotion.vad_list()
        }]
        self._table.add(row)

    @retry_on_error()
    def search(self, q_vec: np.ndarray, user_id=None, channel_id=None, limit: int = 5) -> List[Dict]:
        flt = ["user_id != '__density__'"]
        if user_id: flt.append(f"user_id = '{str(user_id)}'")
        if channel_id: flt.append(f"channel_id = '{str(channel_id)}'")
        try:
            res = self._table.search(q_vec.tolist()).where(" AND ".join(flt), prefilter=True).limit(limit).to_list()
            for r in res:
                r["metadata"] = json.loads(r["metadata"]) if r.get("metadata") else {}
                r["emotion_vad"] = np.array(r["emotion_vad"], dtype=np.float32) if r.get("emotion_vad") else _VAD_NEUTRAL
                r["vector"] = np.array(r["vector"], dtype=np.float32) if r.get("vector") else None
            return res
        except: return []

    @retry_on_error()
    def upsert_density(self, channel_id: str, state_dict: Dict):
        self._table.delete(f"user_id = '__density__' AND channel_id = '{channel_id}'")
        self._table.add([{
            "id": f"density_{channel_id}", "user_id": "__density__", "channel_id": str(channel_id),
            "user_msg": "", "bot_msg": "", "text": "[density]", "timestamp": time.time(),
            "metadata": json.dumps(state_dict), "vector": [0.0] * self._embedder.dim,
            "emotion": "neutral", "emotion_vad": [0.0, 0.0, 0.0]
        }])

    @retry_on_error()
    def load_density(self, channel_id: str) -> Optional[Dict]:
        try:
            res = self._table.search([0.0] * self._embedder.dim).where(f"user_id = '__density__' AND channel_id = '{channel_id}'", prefilter=True).limit(1).to_list()
            if res: return json.loads(res[0]["metadata"])
        except: pass
        return None

    @retry_on_error()
    def delete_old(self, cutoff: float):
        self._table.delete(f"timestamp < {cutoff} AND user_id != '__density__'")

    def delete_channel_memories(self, channel_id: str):
        self._table.delete(f"channel_id = '{channel_id}'")

# ─────────────────────────────────────────────────────────────────────────────
# SQLite-vec Cache
# ─────────────────────────────────────────────────────────────────────────────

class VecCache:
    _init_lock = threading.Lock()

    def __init__(self, embedder: Embedder):
        import sqlite_vec
        self._sv = sqlite_vec
        self._emb = embedder
        self._local = threading.local()
        self._enabled = False
        self._init()

    def _init(self):
        try:
            conn = self._conn()
            with self._init_lock:
                conn.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_cache USING vec0(embedding float[{self._emb.dim}])")
                conn.execute("CREATE TABLE IF NOT EXISTS cache_meta (id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT, result TEXT, expires_at REAL)")
                conn.commit()
            self._enabled = True
        except: logger.warning("VecCache desabilitado.")

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "c") or self._local.c is None:
            c = sqlite3.connect(config.CACHE_DB_PATH, check_same_thread=False)
            c.enable_load_extension(True)
            self._sv.load(c)
            c.enable_load_extension(False)
            self._local.c = c
        return self._local.c

    @retry_on_error(max_retries=2, delay=0.05, exceptions=(sqlite3.OperationalError,))
    def get(self, vec: np.ndarray) -> Optional[List[Dict]]:
        if not self._enabled: return None
        try:
            row = self._conn().execute("SELECT m.result FROM vec_cache v JOIN cache_meta m ON v.rowid=m.id WHERE v.distance < ? AND m.expires_at > ? ORDER BY v.distance LIMIT 1", (1.0 - config.CACHE_SIMILARITY_THRESHOLD, time.time())).fetchone()
            return json.loads(row[0]) if row else None
        except: return None

    @retry_on_error(max_retries=2, delay=0.05, exceptions=(sqlite3.OperationalError,))
    def set(self, vec: np.ndarray, results: List[Dict], query: str = ""):
        if not self._enabled: return
        c = self._conn()
        vs = "[" + ",".join(f"{x:.6f}" for x in vec.tolist()) + "]"
        exp = time.time() + config.CACHE_TTL_SECONDS
        try:
            c.execute("BEGIN")
            cur = c.execute("INSERT INTO cache_meta (query,result,expires_at) VALUES(?,?,?)", (query, json.dumps(results), exp))
            c.execute("INSERT INTO vec_cache (rowid,embedding) VALUES(?,?)", (cur.lastrowid, vs))
            c.commit()
            if random.random() < config.CACHE_PRUNE_PROBABILITY: self._prune(c)
        except: c.rollback()

    def _prune(self, c: sqlite3.Connection):
        try:
            ids = [r[0] for r in c.execute("SELECT id FROM cache_meta WHERE expires_at<=?", (time.time(),)).fetchall()]
            if not ids: return
            ph = ",".join("?" for _ in ids)
            c.execute("BEGIN")
            c.execute(f"DELETE FROM cache_meta WHERE id IN ({ph})", ids)
            c.execute(f"DELETE FROM vec_cache WHERE rowid IN ({ph})", ids)
            c.commit()
        except: pass

    def close(self):
        if hasattr(self._local, "c") and self._local.c:
            try: self._local.c.close()
            except: pass
            self._local.c = None

# ─────────────────────────────────────────────────────────────────────────────
# Mem0 Client (opcional)
# ─────────────────────────────────────────────────────────────────────────────

class Mem0Client:
    def __init__(self):
        self._enabled = False
        if config.USE_MEM0: self._init()

    def _init(self):
        try:
            from mem0 import Memory
            self._client = Memory.from_config({"vector_store": {"provider": config.MEM0_VECTOR_STORE, "config": {"collection_name": config.MEM0_COLLECTION, "persist_directory": config.MEM0_PERSIST_DIR}}})
            self._enabled = True
        except: pass

    def add(self, messages: List[Dict], user_id: str, metadata=None):
        if self._enabled:
            try: self._client.add(messages, user_id=user_id, metadata=metadata)
            except: pass

    def search(self, query: str, user_id=None, limit: int = 5) -> List[Dict]:
        if not self._enabled: return []
        try:
            res = self._client.search(query, user_id=user_id, limit=limit)
            return res[:limit] if isinstance(res, list) else []
        except: return []

# ─────────────────────────────────────────────────────────────────────────────
# Performance Tracker
# ─────────────────────────────────────────────────────────────────────────────

class PerfTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self._buf = {}
        self.hits, self.misses = 0, 0

    def record(self, op: str, ms: float):
        if not config.ENABLE_PERF_LOGGING: return
        with self._lock:
            b = self._buf.setdefault(op, [])
            b.append(ms)
            if len(b) > 200: b.pop(0)

    def stats(self) -> Dict:
        out = {"cache": {"hits": self.hits, "misses": self.misses, "rate": f"{self.hits/(self.hits+self.misses)*100:.1f}%" if (self.hits+self.misses) else "0%"}}
        with self._lock:
            for op, vals in self._buf.items():
                if not vals: continue
                a = np.array(vals)
                out[op] = {"n": len(vals), "avg": round(float(np.mean(a)), 1), "p95": round(float(np.percentile(a, 95)), 1)}
        return out

# ─────────────────────────────────────────────────────────────────────────────
# MemoryService
# ─────────────────────────────────────────────────────────────────────────────

class MemoryService:
    def __init__(self):
        self._emb = Embedder()
        self._emo = EmotionDetector()
        self._store = LanceStore(self._emb)
        self._cache = VecCache(self._emb)
        self._mem0 = Mem0Client()
        self._perf = PerfTracker()
        self._full_dim = self._emb.dim + 3
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mem-search")
        self._density, self._d_lock, self._d_count = {}, threading.Lock(), {}
        self._l1, self._l1_lock = {}, threading.Lock()
        self._closed = False
        self._start_cleanup()

    def add_interaction(self, user_msg: str, bot_msg: str, user_id: int, channel_id: int, metadata: Dict = None):
        t0 = time.perf_counter()
        if not user_msg.strip() or not bot_msg.strip(): return
        emotion = self._emo.detect(user_msg)
        sem_vec = self._emb.encode(f"Usuário: {user_msg}\nAstéria: {bot_msg}")
        full_vec = _norm(np.concatenate([sem_vec, emotion.vad]))
        if config.USE_DENSITY_RERANK:
            state = self._get_density(str(channel_id))
            if state:
                state.add_vector(full_vec)
                cid = str(channel_id)
                self._d_count[cid] = self._d_count.get(cid, 0) + 1
                if self._d_count[cid] % config.DENSITY_PERSIST_INTERVAL == 0:
                    threading.Thread(target=self._store.upsert_density, args=(cid, state.to_dict()), daemon=True).start()
        self._store.add(user_msg, bot_msg, user_id, channel_id, sem_vec, emotion, metadata)
        self._mem0.add([{"role": "user", "content": user_msg}, {"role": "assistant", "content": bot_msg}], user_id=str(user_id), metadata={"channel": channel_id, "emotion": emotion.dominant, **(metadata or {})})
        self._l1_push(str(channel_id), {"user": user_msg, "bot": bot_msg, "emo": emotion.dominant})
        self._perf.record("add", (time.perf_counter()-t0)*1000)

    def get_context(self, query: str, user_id: int = None, channel_id: int = None, limit: int = 5) -> str:
        t0 = time.perf_counter()
        cid = str(channel_id) if channel_id else ""
        if not query.strip(): return self._fmt_l1(cid)
        q_emo = self._emo.detect(query)
        q_sem = self._emb.encode(query)
        q_full = _norm(np.concatenate([q_sem, q_emo.vad]))
        cached = self._cache.get(q_sem)
        if cached: self._perf.hits += 1; mems = cached
        else:
            self._perf.misses += 1
            mems = self._search(query, q_sem, user_id, channel_id, limit)
            mems = self._rerank(mems, q_full, cid)
            self._cache.set(q_sem, mems, query)
        ctx = self._format(mems, limit, q_emo, cid)
        self._perf.record("get", (time.perf_counter()-t0)*1000)
        return ctx

    def clear_channel_memory(self, channel_id):
        cid = str(channel_id)
        with self._d_lock:
            if cid in self._density: del self._density[cid]
        with self._l1_lock:
            if cid in self._l1: del self._l1[cid]
        self._store.delete_channel_memories(cid)

    # Métodos internos simplificados para caber no arquivo
    def _get_density(self, cid: str) -> Optional[DensityMemoryState]:
        if cid in self._density: return self._density[cid]
        with self._d_lock:
            if cid in self._density: return self._density[cid]
            if not config.USE_DENSITY_RERANK: return None
            saved = self._store.load_density(cid)
            s = DensityMemoryState.from_dict(saved) if saved else DensityMemoryState(self._full_dim, config.DENSITY_LOW_RANK, config.DENSITY_DECAY_LAMBDA, config.DENSITY_MAX_VECTORS, config.DENSITY_PRUNE_THRESHOLD, config.DENSITY_PRUNE_MIN_AGE_SEC)
            self._density[cid] = s
            return s

    def _search(self, query, q_sem, user_id, channel_id, limit) -> List[Dict]:
        fut_l = self._executor.submit(self._store.search, q_sem, user_id, channel_id, limit)
        fut_m = self._executor.submit(self._mem0.search, query, str(user_id) if user_id else None, limit)
        try: l = fut_l.result(timeout=5)
        except: l = []
        try: m = fut_m.result(timeout=5)
        except: m = []
        return self._rrf(l, m, limit)

    def _rrf(self, l, m, limit, k=60) -> List[Dict]:
        scores, raws = {}, {}
        for rank, r in enumerate(l):
            t = r.get("text", "")
            if not t: continue
            scores[t] = scores.get(t, 0.0) + 1.0/(k+rank+1)
            raws[t] = {"text": t, "vector": r.get("vector"), "emotion_vad": r.get("emotion_vad", _VAD_NEUTRAL), "emotion": r.get("emotion")}
        for rank, r in enumerate(m):
            t = r.get("memory") or r.get("text", "")
            if not t: continue
            scores[t] = scores.get(t, 0.0) + 1.0/(k+rank+1)
            if t not in raws: raws[t] = {"text": t, "vector": None, "emotion_vad": _VAD_NEUTRAL, "emotion": "neutral"}
        merged = []
        for t in sorted(scores, key=scores.__getitem__, reverse=True)[:limit]:
            e = raws[t].copy(); e["rrf"] = scores[t]; merged.append(e)
        return merged

    def _rerank(self, mems, q_full, cid) -> List[Dict]:
        state = self._get_density(cid)
        if state: state.decay()
        for m in mems:
            if state and m.get("vector") is not None:
                fv = _norm(np.concatenate([m["vector"], m["emotion_vad"]]))
                m["score"] = 0.5*m["rrf"] + 0.5*state.score(fv)
            else: m["score"] = m["rrf"]
        mems.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        return mems

    def _format(self, mems, limit, q_emo, cid) -> str:
        parts = []
        if q_emo.dominant != "neutral" and q_emo.score > 0.35: parts.append(f"[Emoção detectada: {q_emo.dominant}]")
        if mems:
            parts.append("[Memórias relevantes:]")
            for m in mems[:limit]: parts.append(f"- {m['text']}")
        l1 = self._get_l1(cid)
        if l1:
            parts.append("[Conversa recente:]")
            for e in l1[-5:]: parts += [f"Usuário: {e['user']}", f"Astéria: {e['bot']}"]
        return "\n".join(parts)

    def _fmt_l1(self, cid: str) -> str:
        l1 = self._get_l1(cid)
        if not l1: return ""
        lines = ["[Conversa recente:]"]
        for e in l1: lines += [f"Usuário: {e['user']}", f"Astéria: {e['bot']}"]
        return "\n".join(lines)

    def _l1_push(self, cid, entry):
        with self._l1_lock:
            if cid not in self._l1: self._l1[cid] = deque(maxlen=config.L1_MAXLEN)
            self._l1[cid].append(entry)

    def _get_l1(self, cid) -> List[Dict]:
        with self._l1_lock: return list(self._l1.get(cid, []))

    def _start_cleanup(self):
        def loop():
            while not self._closed:
                time.sleep(3600)
                if config.MEMORY_RETENTION_DAYS:
                    cutoff = time.time() - config.MEMORY_RETENTION_DAYS * 86400
                    try: self._store.delete_old(cutoff)
                    except: pass
        threading.Thread(target=loop, daemon=True).start()

    def close(self):
        self._closed = True
        for cid, state in self._density.items():
            if state: self._store.upsert_density(cid, state.to_dict())
        self._executor.shutdown(wait=False)
        self._cache.close()

# Alias para facilitar migração
MemorySystem = MemoryService
