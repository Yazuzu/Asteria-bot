#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
personality_system.py — Sistema leve de personalidade (pattern matching)
REFATORADO COM TYPE HINTS COMPLETOS E ERRO HANDLING
"""

import logging
from enum import Enum
from typing import Dict, Tuple, Optional

logger = logging.getLogger("asteria.personality")


class InterlocutorProfile(Enum):
    """Perfis detectados por pattern matching (não ML)."""

    TILTED_EASY = "tilted"
    STOIC_IMMUNE = "stoic"
    DEVOTEE = "devotee"
    COMPETITIVE = "competitive"
    PHILOSOPHICAL = "philosophical"
    DISINTERESTED = "disinterested"
    UNKNOWN = "unknown"


class PersonalityMatcher:
    """Detecta perfil do interlocutor com pattern matching leve (~20ms)."""

    def __init__(self) -> None:
        """Inicializa matcher com padrões."""
        self.patterns: Dict[InterlocutorProfile, Dict] = {
            InterlocutorProfile.TILTED_EASY: {
                "keywords": ["errado", "burro", "estúpido", "péssimo"],
                "caps_threshold": 0.3,
                "exclamation_threshold": 2,
            },
            InterlocutorProfile.STOIC_IMMUNE: {
                "keywords": ["hm", "ok", "sim", "não"],
                "max_length": 30,
                "emoji_count": 0,
            },
            InterlocutorProfile.DEVOTEE: {
                "keywords": ["adorei", "melhor", "perfeito", "incrível"],
                "emoji_count_min": 1,
            },
            InterlocutorProfile.COMPETITIVE: {
                "keywords": ["aposto", "bora", "desafio", "consegue"],
                "exclamation_threshold": 1,
            },
            InterlocutorProfile.PHILOSOPHICAL: {
                "keywords": ["por quê", "será", "questão", "sentido"],
                "min_length": 50,
            },
            InterlocutorProfile.DISINTERESTED: {
                "keywords": ["tá", "blz", "ok"],
                "max_length": 20,
            },
        }

    def detect(self, message: str) -> Tuple[InterlocutorProfile, float]:
        """Detecta perfil com análise leve.

        Args:
            message: Mensagem do usuário

        Returns:
            Tuple[InterlocutorProfile, float]: Perfil detectado e confiança (0-1)
        """
        try:
            if not message or not isinstance(message, str):
                logger.warning(f"Mensagem inválida para detecção: {type(message)}")
                return InterlocutorProfile.UNKNOWN, 0.0

            msg_lower = message.lower().strip()
            msg_len = len(msg_lower)
            if msg_len == 0:
                return InterlocutorProfile.UNKNOWN, 0.0

            # Cálculos de features
            caps_ratio = sum(1 for c in message if c.isupper()) / max(msg_len, 1)
            exclamations = message.count("!")
            emojis = sum(1 for c in message if ord(c) > 127)

            scores: Dict[InterlocutorProfile, float] = {}

            for profile, pattern in self.patterns.items():
                score = 0.0
                checks = 0

                # Keyword matching
                if "keywords" in pattern:
                    keyword_matches = sum(
                        1 for kw in pattern["keywords"] if kw in msg_lower
                    )
                    score += keyword_matches * 0.2
                    checks += 1

                # Caps ratio
                if "caps_threshold" in pattern:
                    if caps_ratio >= pattern["caps_threshold"]:
                        score += 0.3
                    checks += 1

                # Message length
                if "min_length" in pattern and msg_len >= pattern["min_length"]:
                    score += 0.15
                    checks += 1
                elif "max_length" in pattern and msg_len <= pattern["max_length"]:
                    score += 0.15
                    checks += 1

                # Exclamations
                if "exclamation_threshold" in pattern:
                    if exclamations >= pattern["exclamation_threshold"]:
                        score += 0.15
                    checks += 1

                # Emoji count
                if "emoji_count_min" in pattern and emojis >= pattern["emoji_count_min"]:
                    score += 0.15
                    checks += 1
                elif "emoji_count" in pattern and emojis == pattern["emoji_count"]:
                    score += 0.15
                    checks += 1

                if checks > 0:
                    scores[profile] = score / checks
                else:
                    scores[profile] = 0.0

            # Get best match
            best_profile = max(scores, key=scores.get) if scores else InterlocutorProfile.UNKNOWN
            confidence = scores.get(best_profile, 0.0)

            # Fallback to UNKNOWN if confidence too low
            if confidence < 0.3:
                best_profile = InterlocutorProfile.UNKNOWN
                confidence = 0.0

            logger.debug(
                f"Profile detected: {best_profile.value} (confidence: {confidence:.2f})"
            )
            return best_profile, confidence

        except Exception as e:
            logger.error(f"Erro na detecção de perfil: {e}")
            return InterlocutorProfile.UNKNOWN, 0.0
