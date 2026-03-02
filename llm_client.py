# llm_client.py
import aiohttp
import asyncio
import logging
from config import (
    KOBOLD_URL,
    TEMPERATURE,
    REPETITION_PENALTY,
    # Opcionais – se não existirem no config, usamos valores padrão abaixo
)

logger = logging.getLogger("llm")

# Valores padrão para parâmetros não definidos no config
DEFAULT_TOP_P = 0.95
DEFAULT_TOP_K = 40
DEFAULT_MAX_CONTEXT = 4096
DEFAULT_STOP = ["<|eot_id|>", "<|start_header_id|>"]

async def generate(prompt: str, max_tokens: int = 150, temperature: float = None) -> str:
    """
    Envia o prompt para o KoboldCPP e retorna a resposta gerada.
    max_tokens: limite de tokens na resposta (deve vir do main.py: 80 ou 300).
    """
    # Tenta importar valores do config, se existirem; senão, usa defaults
    try:
        from config import TOP_P, TOP_K, MAX_CONTEXT_LENGTH, STOP_TOKENS
        top_p = TOP_P
        top_k = TOP_K
        max_context = MAX_CONTEXT_LENGTH
        stop = STOP_TOKENS
    except ImportError:
        top_p = DEFAULT_TOP_P
        top_k = DEFAULT_TOP_K
        max_context = DEFAULT_MAX_CONTEXT
        stop = DEFAULT_STOP
    except AttributeError:
        # Caso as variáveis não estejam definidas no config
        top_p = DEFAULT_TOP_P
        top_k = DEFAULT_TOP_K
        max_context = DEFAULT_MAX_CONTEXT
        stop = DEFAULT_STOP

    payload = {
        "prompt": prompt,
        "max_context_length": max_context,
        "max_length": max_tokens,
        "temperature": temperature if temperature is not None else TEMPERATURE,
        "top_p": top_p,
        "top_k": top_k,
        "repeat_penalty": REPETITION_PENALTY,      # vindo do config (nome correto!)
        "stop": stop,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                KOBOLD_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=360)
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"LLM HTTP {resp.status}: {text}")
                    return "[Erro ao falar com o modelo]"
                data = await resp.json()
                if "results" in data and len(data["results"]) > 0:
                    return data["results"][0]["text"].strip()
                else:
                    logger.error(f"Resposta inesperada do KoboldCPP: {data}")
                    return "[Erro: formato de resposta inválido]"
    except asyncio.TimeoutError:
        logger.error("Timeout na requisição ao KoboldCPP")
        return "[Erro: tempo limite excedido]"
    except Exception as e:
        logger.exception("Erro no LLM")
        return "[Erro interno]"