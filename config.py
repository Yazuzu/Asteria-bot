#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
config.py — Configuração centralizada do Asteria-bot
VALIDAÇÃO E DEFAULTS IMPLEMENTADOS
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# ──────────────────────────────────────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger("asteria.config")

# ──────────────────────────────────────────────────────────────────────────────
# ENVIRONMENT SETUP
# ──────────────────────────────────────────────────────────────────────────────

env_path = Path(".env")
if not env_path.exists():
    logger.warning(
        f"⚠️  Arquivo .env não encontrado em {env_path.absolute()}\n"
        f"   Copie .env.example para .env e configure as variáveis."
    )

load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
# DISCORD CONFIGURATION (CRÍTICO)
# ──────────────────────────────────────────────────────────────────────────────

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    logger.error("❌ DISCORD_TOKEN não configurado em .env")
    sys.exit(1)

try:
    OWNER_IDS = [
        int(i.strip())
        for i in os.getenv("OWNER_IDS", "").split(",")
        if i.strip()
    ]
    if not OWNER_IDS:
        logger.warning(
            "⚠️  OWNER_IDS vazio. Alguns comandos restritos não funcionarão."
        )
except ValueError as e:
    logger.error(f"❌ OWNER_IDS inválido (deve ser números separados por vírgula): {e}")
    sys.exit(1)

# ──────────────────────────────────────────────────────────────────────────────
# LLM CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────

KOBOLD_URL = os.getenv("KOBOLD_URL", "http://localhost:5001/api/v1/generate")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.70"))
REPETITION_PENALTY = float(os.getenv("REPETITION_PENALTY", "1.15"))
TOP_P = float(os.getenv("TOP_P", "0.95"))
TOP_K = int(os.getenv("TOP_K", "40"))
MAX_CONTEXT_LENGTH = int(os.getenv("MAX_CONTEXT_LENGTH", "4096"))

# Token limits
CASUAL_MAX_TOKENS = int(os.getenv("CASUAL_MAX_TOKENS", "80"))
RP_MAX_TOKENS = int(os.getenv("RP_MAX_TOKENS", "300"))

# Stop tokens para Llama 3
STOP_TOKENS = [
    "<|eot_id|>",
    "<|start_header_id|>",
    "\nUsuário:",
    "\nUser:",
    "\nAstéria:",
    "\nAsteria:",
    "Usuário:",
    "User:",
    "Astéria:",
    "Asteria:",
    "###",
]

# ──────────────────────────────────────────────────────────────────────────────
# MEMORY CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────

MAX_MEMORY_MESSAGES = int(os.getenv("MAX_MEMORY_MESSAGES", "6"))
MEMORY_RETENTION_DAYS = int(os.getenv("MEMORY_RETENTION_DAYS", "30"))

# Memory directories
MEMORY_DIR = Path("data/memory")
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(parents=True, exist_ok=True)

LANCEDB_PATH = "data/lancedb"
CACHE_DB_PATH = "data/vec_cache.db"
CACHE_SIMILARITY_THRESHOLD = float(os.getenv("CACHE_SIMILARITY_THRESHOLD", "0.98"))
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))
CACHE_PRUNE_PROBABILITY = float(os.getenv("CACHE_PRUNE_PROBABILITY", "0.05"))

# ──────────────────────────────────────────────────────────────────────────────
# AI MODELS (Hugging Face)
# ──────────────────────────────────────────────────────────────────────────────

EMOTION_MODEL = os.getenv(
    "EMOTION_MODEL", "bhavesh-thakkar01/go-emotion-distilbert"
)
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)

# ──────────────────────────────────────────────────────────────────────────────
# FEATURE FLAGS
# ──────────────────────────────────────────────────────────────────────────────

USE_PERSONA_REACT = os.getenv("USE_PERSONA_REACT", "True").lower() == "true"
USE_DENSITY_RERANK = os.getenv("USE_DENSITY_RERANK", "True").lower() == "true"
ENABLE_PERF_LOGGING = os.getenv("ENABLE_PERF_LOGGING", "True").lower() == "true"
USE_MEM0 = os.getenv("USE_MEM0", "False").lower() == "true"

# ──────────────────────────────────────────────────────────────────────────────
# DENSITY MATRIX SETTINGS
# ──────────────────────────────────────────────────────────────────────────────

DENSITY_LOW_RANK = int(os.getenv("DENSITY_LOW_RANK", "50"))
DENSITY_DECAY_LAMBDA = float(os.getenv("DENSITY_DECAY_LAMBDA", "0.0001"))
DENSITY_MAX_VECTORS = int(os.getenv("DENSITY_MAX_VECTORS", "1000"))
DENSITY_PRUNE_THRESHOLD = float(os.getenv("DENSITY_PRUNE_THRESHOLD", "0.01"))
DENSITY_PRUNE_MIN_AGE_SEC = int(os.getenv("DENSITY_PRUNE_MIN_AGE_SEC", "86400"))
DENSITY_PERSIST_INTERVAL = int(os.getenv("DENSITY_PERSIST_INTERVAL", "5"))
DENSITY_LEARNING_RATE = float(os.getenv("DENSITY_LEARNING_RATE", "0.15"))

# ──────────────────────────────────────────────────────────────────────────────
# L1 CACHE & RETENTION
# ──────────────────────────────────────────────────────────────────────────────

L1_MAXLEN = int(os.getenv("L1_MAXLEN", "10"))

# ──────────────────────────────────────────────────────────────────────────────
# MEM0 CONFIGURATION (Opcional)
# ──────────────────────────────────────────────────────────────────────────────

MEM0_VECTOR_STORE = "lancedb"
MEM0_COLLECTION = "mem0_asteria"
MEM0_PERSIST_DIR = "data/mem0"

# ──────────────────────────────────────────────────────────────────────────────
# LOGGING FINAL
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("✅ Configuração carregada com sucesso")
    logger.info(f"   - DISCORD_TOKEN: {'✓' if DISCORD_TOKEN else '✗'}")
    logger.info(f"   - OWNER_IDS: {len(OWNER_IDS)} admin(s)")
    logger.info(f"   - LLM URL: {KOBOLD_URL}")
    logger.info(f"   - Features: PersonaReAct={USE_PERSONA_REACT}, Density={USE_DENSITY_RERANK}")
