#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
llm_client.py — Cliente para KoboldCPP com tratamento de erros robusto
REFATORADO COM VALIDAÇÕES E FALLBACKS
"""

import aiohttp
import asyncio
import logging
from typing import Optional
from config import (
    KOBOLD_URL,
    TEMPERATURE,
    REPETITION_PENALTY,
    TOP_P,
    TOP_K,
    MAX_CONTEXT_LENGTH,
    STOP_TOKENS,
)

logger = logging.getLogger("asteria.llm")


class LLMClientError(Exception):
    """Erro base do cliente LLM."""
    pass


class LLMConnectionError(LLMClientError):
    """Erro de conexão com KoboldCPP."""
    pass


class LLMTimeoutError(LLMClientError):
    """Timeout na geração."""
    pass


class LLMResponseError(LLMClientError):
    """Erro na resposta do servidor."""
    pass


async def generate(
    prompt: str,
    max_tokens: int = 150,
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    top_k: Optional[int] = None,
    repeat_penalty: Optional[float] = None,
) -> str:
    """
    Envia o prompt para o KoboldCPP e retorna a resposta gerada.

    Args:
        prompt: Prompt a enviar
        max_tokens: Limite de tokens na resposta
        temperature: Criatividade (0-2)
        top_p: Nucleus sampling (0-1)
        top_k: Top-k sampling
        repeat_penalty: Penalidade de repetição

    Returns:
        str: Resposta gerada ou mensagem de erro

    Raises:
        LLMClientError: Se falhar na geração
    """
    # Use config defaults se não fornecido
    _temperature = temperature if temperature is not None else TEMPERATURE
    _top_p = top_p if top_p is not None else TOP_P
    _top_k = top_k if top_k is not None else TOP_K
    _repeat_penalty = repeat_penalty if repeat_penalty is not None else REPETITION_PENALTY

    # Validação de entrada
    if not prompt or not isinstance(prompt, str):
        logger.error(f"Prompt inválido: {type(prompt)}")
        return "[Erro: prompt inválido]"

    if max_tokens <= 0 or max_tokens > 2048:
        logger.warning(f"max_tokens fora do range: {max_tokens}, ajustando para 150")
        max_tokens = 150

    payload = {
        "prompt": prompt,
        "max_context_length": MAX_CONTEXT_LENGTH,
        "max_length": max_tokens,
        "temperature": _temperature,
        "top_p": _top_p,
        "top_k": _top_k,
        "repeat_penalty": _repeat_penalty,
        "stop": STOP_TOKENS,
    }

    try:
        logger.debug(f"Enviando request para {KOBOLD_URL}")

        async with aiohttp.ClientSession() as session:
            async with session.post(
                KOBOLD_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=360),
            ) as resp:
                # Verificar status HTTP
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"LLM HTTP {resp.status}: {text[:200]}")
                    raise LLMResponseError(f"HTTP {resp.status}: {text}")

                # Parsear JSON
                try:
                    data = await resp.json()
                except aiohttp.ContentTypeError as e:
                    logger.error(f"Resposta não-JSON do KoboldCPP: {e}")
                    raise LLMResponseError(f"Resposta inválida: {e}")

                # Verificar estrutura
                if "results" not in data or not data["results"]:
                    logger.error(f"Resposta inesperada: {data}")
                    raise LLMResponseError(f"Sem 'results' na resposta")

                result = data["results"][0].get("text", "").strip()

                if not result:
                    logger.warning("Resposta vazia do modelo")
                    return "[Astéria ficou sem palavras...]"

                logger.debug(f"Resposta gerada: {len(result)} chars")
                return result

    except asyncio.TimeoutError:
        logger.error("Timeout na requisição ao KoboldCPP (360s)")
        raise LLMTimeoutError("Tempo limite excedido")

    except aiohttp.ClientConnectorError as e:
        logger.error(f"Erro de conexão: {e}")
        raise LLMConnectionError(f"Impossível conectar a {KOBOLD_URL}: {e}")

    except aiohttp.ClientError as e:
        logger.error(f"Erro do cliente: {e}")
        raise LLMClientError(f"Erro na requisição: {e}")

    except Exception as e:
        logger.exception(f"Erro inesperado no LLM")
        raise LLMClientError(f"Erro inesperado: {e}")
