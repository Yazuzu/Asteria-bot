import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_IDS = [int(i) for i in os.getenv("OWNER_IDS", "").split(",") if i.strip()]

KOBOLD_URL = os.getenv("KOBOLD_URL", "http://localhost:5001/api/v1/generate")

# Limites de geração
CASUAL_MAX_TOKENS = 80
RP_MAX_TOKENS = 300
TEMPERATURE = 0.70
REPETITION_PENALTY = 1.15

# Memória
MAX_MEMORY_MESSAGES = 6
MEMORY_DIR = Path("data/memory")
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

# Logs
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Parâmetros de geração
TOP_P = 0.95
TOP_K = 40
MAX_CONTEXT_LENGTH = 4096
STOP_TOKENS = [
    "<|eot_id|>", "<|start_header_id|>", 
    "\nUsuário:", "\nUser:", "\nAstéria:", "\nAsteria:",
    "Usuário:", "User:", "Astéria:", "Asteria:",
    "###"
]

# PersonaReAct
USE_PERSONA_REACT = True

# MemoryService v2.3 (Advanced)
LANCEDB_PATH = "data/lancedb"
EMOTION_MODEL = "bhavesh-thakkar01/go-emotion-distilbert" # "j-hartmann/emotion-english-distilroberta-base"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
CACHE_DB_PATH = "data/vec_cache.db"
CACHE_SIMILARITY_THRESHOLD = 0.98
CACHE_TTL_SECONDS = 3600
CACHE_PRUNE_PROBABILITY = 0.05

# Density Matrix Settings
USE_DENSITY_RERANK = True
DENSITY_LOW_RANK = 50
DENSITY_DECAY_LAMBDA = 0.0001
DENSITY_MAX_VECTORS = 1000
DENSITY_PRUNE_THRESHOLD = 0.01
DENSITY_PRUNE_MIN_AGE_SEC = 86400
DENSITY_PERSIST_INTERVAL = 5
DENSITY_LEARNING_RATE = 0.15

# L1 Cache & Retention
L1_MAXLEN = 10
MEMORY_RETENTION_DAYS = 30
ENABLE_PERF_LOGGING = True

# Mem0 (Opcional)
USE_MEM0 = False
MEM0_VECTOR_STORE = "lancedb"
MEM0_COLLECTION = "mem0_asteria"
MEM0_PERSIST_DIR = "data/mem0"