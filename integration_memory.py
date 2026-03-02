#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""integration_memory.py — Adaptador de compatibilidade para memória"""

from memory import ChannelMemory as LegacyChannelMemory
import logging

logger = logging.getLogger(__name__)


class MemoryManagerAdapter:
    """Adaptador que mantém compatibilidade com a estrutura de memória existente."""
    
    def __init__(self):
        # O sistema antigo usa ChannelMemory instanciado por canal no main.py
        # Este adaptador pode ser usado para facilitar a transição se necessário.
        pass
    
    @staticmethod
    def get_legacy_memory():
        """Retorna uma instância da memória legada."""
        return LegacyChannelMemory()
