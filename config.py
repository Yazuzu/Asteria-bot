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
TEMPERATURE = 0.85
REPETITION_PENALTY = 1.15

# Memória
MAX_MEMORY_MESSAGES = 6
MEMORY_DIR = Path("data/memory")
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

# Logs
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Parâmetros de geração (adicione ao final do arquivo)
TOP_P = 0.95
TOP_K = 40
MAX_CONTEXT_LENGTH = 4096
STOP_TOKENS = ["<|eot_id|>", "<|start_header_id|>"]