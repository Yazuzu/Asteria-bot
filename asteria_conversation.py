# asteria_conversation.py
import logging
import numpy as np
import random
from typing import Optional, Tuple

from memory_system import MemoryService, EmotionResult
from personality_system import PersonalityMatcher, InterlocutorProfile
from persona_react_engine import PersonaReActEngine
from prompts import ASTERIA_SYSTEM

logger = logging.getLogger("asteria.conversation")

class AsteriaConversation:
    """
    Integra memória, personalidade e geração para uma Astéria coerente.
    Gerencia estado de personalidade e usa confiança das memórias para evitar alucinação.
    """

    def __init__(self, memory: MemoryService, persona_react: PersonaReActEngine):
        self.memory = memory
        self.react = persona_react
        self.personality = PersonalityMatcher()

        # Estados da personalidade
        self.current_state = "aggressive"
        self.vuln_cooldown = 0

        # Limiar de confiança (ajustável)
        self.confidence_threshold = 0.5

    async def process_message(self, user_msg: str, user_id: int, channel_id: int, is_rp: bool = False) -> str:
        """
        Processa uma mensagem do usuário e retorna a resposta da Astéria.
        """
        # 1. Obter contexto e confiança das memórias
        context, confidence = await self._get_context_with_confidence(
            user_msg, user_id, channel_id
        )

        # 2. Detectar perfil do interlocutor (via matcher leve)
        profile, profile_conf = self.personality.detect(user_msg)

        # 3. Detectar emoção
        emotion = self.memory._emo.detect(user_msg)

        # 4. Atualizar estado da personalidade
        self._update_state()

        # 5. Obter estratégia baseada no perfil e emoção
        strategy = self._get_strategy(profile, emotion)

        # 6. Construir system prompt com hints e anti-alucinação se necessário
        if confidence < self.confidence_threshold:
            system_prompt = self._build_low_confidence_prompt(strategy, emotion)
        else:
            system_prompt = self._build_normal_prompt(strategy, emotion)

        # 7. Gerar resposta via PersonaReAct
        response, analysis, _ = await self.react.analyze_and_respond(
            user_message=user_msg,
            conversation_context=context,
            system_prompt=system_prompt,
            is_rp=is_rp,
            user_id=user_id,
        )

        # 8. Armazenar a interação
        self.memory.add_interaction(
            user_msg=user_msg,
            bot_msg=response,
            user_id=user_id,
            channel_id=channel_id,
            metadata={
                "profile": profile.value,
                "personality_state": self.current_state,
                "strategy_tone": strategy.get("tone"),
                "confidence": round(confidence, 3)
            }
        )

        return response

    async def _get_context_with_confidence(
        self, query: str, user_id: int, channel_id: int
    ) -> Tuple[str, float]:
        """
        Retorna o contexto formatado e a confiança média das memórias.
        """
        q_emo = self.memory._emo.detect(query)
        q_sem = self.memory._emb.encode(query)
        
        # Composição do vetor para reranking
        q_full = np.concatenate([q_sem, q_emo.vad])
        q_norm = np.linalg.norm(q_full)
        q_full = q_full / (q_norm if q_norm > 1e-8 else 1e-8)

        # Busca LanceDB + Mem0
        mems = self.memory._search(query, q_sem, user_id, channel_id, limit=5)
        
        # Reranking com matriz densidade
        mems = self.memory._rerank(mems, q_full, str(channel_id))

        if not mems:
            return "", 0.0

        # Confiança baseada nos scores de rerank (RRF + Density)
        scores = [m.get("score", 0.0) for m in mems]
        confidence = sum(scores) / len(scores)

        # Formatação
        context = self.memory._format(mems, 5, q_emo, str(channel_id))
        return context, confidence

    def _update_state(self):
        self.vuln_cooldown = max(0, self.vuln_cooldown - 1)
        if random.random() < 0.2 and self.vuln_cooldown == 0:
            self.current_state = "impulsive"
            self.vuln_cooldown = 3
        else:
            if self.current_state == "aggressive":
                if random.random() < 0.15: self.current_state = "curious"
            else:
                self.current_state = "aggressive"

    def _get_strategy(self, profile: InterlocutorProfile, emotion: EmotionResult) -> dict:
        strategies = {
            InterlocutorProfile.TILTED_EASY:    {"tone": "aggressive", "escalation": 9},
            InterlocutorProfile.STOIC_IMMUNE:   {"tone": "curious",    "escalation": 6},
            InterlocutorProfile.DEVOTEE:        {"tone": "challenging","escalation": 7},
            InterlocutorProfile.COMPETITIVE:    {"tone": "battle",     "escalation": 8},
            InterlocutorProfile.PHILOSOPHICAL:  {"tone": "ironic_smart","escalation": 5},
            InterlocutorProfile.DISINTERESTED:  {"tone": "impatient",  "escalation": 6},
            InterlocutorProfile.UNKNOWN:        {"tone": "aggressive", "escalation": 5},
        }
        base = strategies.get(profile, {"tone": "aggressive", "escalation": 5})
        
        # Ajustes emocionais
        if emotion.dominant == "anger": base["escalation"] = min(10, base["escalation"] + 2)
        elif emotion.dominant == "joy": base["escalation"] = max(1, base["escalation"] - 1)
        
        return base

    def _build_normal_prompt(self, strategy: dict, emotion: EmotionResult) -> str:
        hints = f"\n\n[HINTS INTERNOS]\n- Estado: {self.current_state}\n- Tom: {strategy['tone']}\n- Escalação: {strategy['escalation']}/10\n- Emoção: {emotion.dominant}\n"
        return ASTERIA_SYSTEM + hints

    def _build_low_confidence_prompt(self, strategy: dict, emotion: EmotionResult) -> str:
        hints = f"\n\n[HINTS INTERNOS - BAIXA CONFIANÇA]\n- Estado: {self.current_state}\n- Tom: {strategy['tone']}\n- Escalação: {strategy['escalation']}/10\n- **AVISO: Pouca memória. Se não souber um fato, admita e provoque (Ex: 'Não sei disso, mas aposto que você também não!'). Nunca invente fatos.**\n"
        return ASTERIA_SYSTEM + hints
