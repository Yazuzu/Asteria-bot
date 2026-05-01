#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
memory.py — Sistema de memória local (básico, para fallback)
MANTÉM COMPATIBILIDADE COM LEGACY CODE
"""

from collections import deque
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger("asteria.memory")


class ChannelMemory:
    """Memória simples de conversação por canal."""

    def __init__(self, channel_id: int, memory_dir: Path = Path("data/memory")):
        """
        Inicializa memória de canal.

        Args:
            channel_id: ID do canal Discord
            memory_dir: Diretório para persistência
        """
        self.channel_id = str(channel_id)
        self.memory_dir = memory_dir
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        self.file = self.memory_dir / f"{self.channel_id}.json"
        self.messages: deque = deque(maxlen=6)
        self.load()

    def add(self, user_msg: str, bot_msg: str, metadata: Optional[Dict] = None) -> None:
        """
        Adiciona interação à memória.

        Args:
            user_msg: Mensagem do usuário
            bot_msg: Resposta do bot
            metadata: Metadados adicionais (opcional)
        """
        try:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "user": user_msg,
                "bot": bot_msg,
                "metadata": metadata or {},
            }
            self.messages.append(entry)
            self.save()
        except Exception as e:
            logger.error(f"Erro ao adicionar memória: {e}")

    def get_context(self) -> str:
        """
        Retorna contexto formatado para prompt.

        Returns:
            str: Contexto formatado
        """
        if not self.messages:
            return ""

        context_lines = []
        for m in self.messages:
            context_lines.append(f"Usuário: {m['user']}")
            context_lines.append(f"Astéria: {m['bot']}")

        return "\n".join(context_lines) + "\n"

    def clear(self) -> None:
        """Limpa toda a memória do canal."""
        try:
            self.messages.clear()
            if self.file.exists():
                self.file.unlink()
            logger.info(f"Memória do canal {self.channel_id} limpa")
        except Exception as e:
            logger.error(f"Erro ao limpar memória: {e}")

    def save(self) -> None:
        """Persiste memória em JSON."""
        try:
            with open(self.file, "w", encoding="utf-8") as f:
                json.dump(list(self.messages), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Erro ao salvar memória: {e}")

    def load(self) -> None:
        """Carrega memória de JSON."""
        if not self.file.exists():
            return

        try:
            with open(self.file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Manter apenas últimas 6
                self.messages.extend(data[-6:] if isinstance(data, list) else [])
            logger.debug(f"Memória carregada: {len(self.messages)} mensagens")
        except Exception as e:
            logger.error(f"Erro ao carregar memória: {e}")


class MemoryManager:
    """Gerenciador de memórias por canal."""

    def __init__(self, memory_dir: Path = Path("data/memory")):
        """
        Inicializa manager de memória.

        Args:
            memory_dir: Diretório para persistência
        """
        self.memory_dir = memory_dir
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.memories: Dict[int, ChannelMemory] = {}
        logger.info(f"MemoryManager inicializado: {memory_dir}")

    def get(self, channel_id: int) -> ChannelMemory:
        """
        Obtém memória de um canal (cria se não existe).

        Args:
            channel_id: ID do canal

        Returns:
            ChannelMemory: Objeto de memória
        """
        if channel_id not in self.memories:
            self.memories[channel_id] = ChannelMemory(channel_id, self.memory_dir)
        return self.memories[channel_id]

    def clear(self, channel_id: int) -> None:
        """
        Limpa memória de um canal.

        Args:
            channel_id: ID do canal
        """
        mem = self.get(channel_id)
        mem.clear()

    def get_all_contexts(self) -> Dict[int, str]:
        """
        Retorna todos os contextos.

        Returns:
            Dict[int, str]: {channel_id: contexto}
        """
        return {cid: mem.get_context() for cid, mem in self.memories.items()}
