#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""llm_client_react.py — LLM Client com suporte a PersonaReAct"""

import aiohttp
import asyncio
import logging
from typing import Tuple, Optional, Dict

from config import KOBOLD_URL, TEMPERATURE, REPETITION_PENALTY

logger = logging.getLogger("llm")

DEFAULT_STOP = ["<|eot_id|>", "<|start_header_id|>"]


async def generate(
    prompt: str,
    max_tokens: int = 150,
    temperature: Optional[float] = None,
) -> str:
    """Geração básica (compatível)."""
    
    if temperature is None:
        temperature = TEMPERATURE
    
    payload = {
        "prompt": prompt,
        "max_length": max_tokens,
        "temperature": temperature,
        "top_p": 0.95,
        "top_k": 40,
        "repeat_penalty": REPETITION_PENALTY,
        "stop": DEFAULT_STOP,
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(KOBOLD_URL, json=payload, timeout=aiohttp.ClientTimeout(total=90)) as resp:
                if resp.status != 200:
                    logger.error(f"HTTP {resp.status}")
                    return "[Erro ao falar com modelo]"
                data = await resp.json()
                if "results" in data and len(data["results"]) > 0:
                    return data["results"][0]["text"].strip()
                return "[Erro: formato inválido]"
    except Exception as e:
        logger.error(f"Erro: {e}")
        return "[Erro]"


async def generate_with_react(
    user_message: str,
    conversation_context: str,
    system_prompt: str,
    is_rp: bool = False,
    user_id: int = 0,
) -> Tuple[str, Optional[Dict]]:
    """PersonaReAct: Análise (T=0.3) + Resposta (T=0.9)."""
    
    # FASE 1: Análise
    analysis_prompt = f"""{system_prompt}

[ANÁLISE INTERNA]
Contexto: {conversation_context}
Mensagem: "{user_message}"

JSON: {{"tone": "aggressive|curious|vulnerable", "strategy": "...", "escalation": 5}}"""
    
    analysis_text = await generate(analysis_prompt, max_tokens=150, temperature=0.3)
    
    # Parse
    import json
    analysis = None
    try:
        # Tenta limpar o JSON se vier com markdown
        clean_text = analysis_text.strip()
        if "```" in clean_text:
            clean_text = clean_text.split("```")[1].replace("json", "").strip()
        analysis = json.loads(clean_text)
    except:
        analysis = {"tone": "aggressive", "escalation": 5}
    
    # FASE 2: Resposta
    hints = f"[tone: {analysis.get('tone')} | escalation: {analysis.get('escalation')}/10]"
    response_prompt = f"""{system_prompt}

{hints}

{conversation_context}

Usuário: {user_message}
Astéria:"""
    
    response = await generate(
        response_prompt,
        max_tokens=300 if is_rp else 80,
        temperature=0.9
    )
    
    logger.info(f"PersonaReAct: user={user_id} | tone={analysis.get('tone')} | escalation={analysis.get('escalation')}/10")
    
    return response, analysis
