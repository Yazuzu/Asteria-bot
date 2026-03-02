#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
persona_react_engine.py — PersonaReAct: Two-Call Strategy para Consistência

VERSÃO FINAL — Implementação Completa
"""

import json
import logging
import time
import asyncio
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Tuple
from collections import deque

logger = logging.getLogger("PersonaReAct")

# =============================================================================
# ENUMS & DATA CLASSES
# =============================================================================

class AsteriaState(Enum):
    """Estados de personalidade."""
    AGGRESSIVE = "aggressive"      # 70-80%
    CURIOUS = "curious"            # 10-15%
    IMPULSIVE = "impulsive"        # 5-15%


@dataclass
class PersonaReActAnalysis:
    """Resultado da Fase 1 (Análise)."""
    thinking: str
    tone: str
    interlocutor_state: str
    strategy: str
    key_points: list
    escalation_suggested: int


@dataclass
class PersonaReActMetrics:
    """Métricas de execução."""
    timestamp: float
    user_id: int
    phase_analysis_ms: float
    phase_response_ms: float
    total_ms: float
    analysis_success: bool
    response_success: bool
    tone: Optional[str] = None
    escalation: Optional[int] = None
    error: Optional[str] = None


# =============================================================================
# METRICS TRACKER
# =============================================================================

class MetricsTracker:
    """Rastreia métricas com janela deslizante."""
    
    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self.metrics = deque(maxlen=window_size)
        self.lock = threading.Lock()
    
    def record(self, metric: PersonaReActMetrics):
        """Registra métrica."""
        with self.lock:
            self.metrics.append(metric)
    
    def get_stats(self) -> Dict:
        """Retorna stats."""
        with self.lock:
            if not self.metrics:
                return {}
            
            metrics_list = list(self.metrics)
            total_count = len(metrics_list)
            success_count = sum(1 for m in metrics_list if m.response_success)
            
            latencies = [m.total_ms for m in metrics_list if m.response_success]
            tones = [m.tone for m in metrics_list if m.tone]
            tone_dist = {}
            for tone in tones:
                tone_dist[tone] = tone_dist.get(tone, 0) + 1
            
            escalations = [m.escalation for m in metrics_list if m.escalation]
            
            return {
                "total": total_count,
                "success_rate": (success_count / total_count * 100) if total_count > 0 else 0,
                "latency_avg_ms": sum(latencies) / len(latencies) if latencies else 0,
                "latency_max_ms": max(latencies) if latencies else 0,
                "tone_distribution": tone_dist,
                "escalation_avg": sum(escalations) / len(escalations) if escalations else 0,
            }
    
    def print_stats(self):
        """Printa stats."""
        stats = self.get_stats()
        if not stats:
            logger.info("Sem métricas ainda")
            return
        
        logger.info("=" * 60)
        logger.info(f"PERSONA-REACT METRICS ({stats['total']} interações)")
        logger.info(f"Success Rate: {stats['success_rate']:.1f}%")
        logger.info(f"Latência: {stats['latency_avg_ms']:.1f}ms (max: {stats['latency_max_ms']:.1f})")
        logger.info(f"Tones: {stats['tone_distribution']}")
        logger.info(f"Escalation Avg: {stats['escalation_avg']:.1f}/10")
        logger.info("=" * 60)


# =============================================================================
# PERSONA REACT ENGINE
# =============================================================================

class PersonaReActEngine:
    """Engine PersonaReAct: Análise (T=0.3) + Resposta (T=0.9)"""
    
    def __init__(self, llm_generator_func, config: Optional[Dict] = None):
        """Inicializa engine."""
        self.generate = llm_generator_func
        
        # Configurações
        self.config = {
            "analysis_temperature": 0.3,
            "response_temperature": 0.9,
            "analysis_max_tokens": 150,
            "response_max_tokens": 80,
            "analysis_timeout_sec": 120,
            "response_timeout_sec": 120,
            "enable_metrics": True,
            **(config or {})
        }
        
        # Métricas
        self.metrics_tracker = MetricsTracker(window_size=100)
        
        logger.info("✨ PersonaReAct Engine inicializado")
    
    async def analyze_and_respond(
        self,
        user_message: str,
        conversation_context: str,
        system_prompt: str,
        is_rp: bool = False,
        user_id: int = 0,
    ) -> Tuple[str, Optional[PersonaReActAnalysis], PersonaReActMetrics]:
        """Executa pipeline PersonaReAct completo."""
        
        start_total = time.perf_counter()
        metric = PersonaReActMetrics(
            timestamp=time.time(),
            user_id=user_id,
            phase_analysis_ms=0,
            phase_response_ms=0,
            total_ms=0,
            analysis_success=False,
            response_success=False,
        )
        
        try:
            # FASE 1: Análise (T=0.3)
            start_analysis = time.perf_counter()
            analysis = await self._phase_analysis(
                user_message=user_message,
                context=conversation_context,
                system_prompt=system_prompt,
            )
            elapsed_analysis = (time.perf_counter() - start_analysis) * 1000
            metric.phase_analysis_ms = elapsed_analysis
            metric.analysis_success = analysis is not None
            
            if not analysis:
                logger.warning(f"Análise falhou, usando fallback")
                analysis = PersonaReActAnalysis(
                    thinking="fallback",
                    tone="aggressive",
                    interlocutor_state="unknown",
                    strategy="default",
                    key_points=[],
                    escalation_suggested=5,
                )
            else:
                metric.tone = analysis.tone
                metric.escalation = analysis.escalation_suggested
            
            # FASE 2: Resposta (T=0.9)
            start_response = time.perf_counter()
            response = await self._phase_response(
                user_message=user_message,
                context=conversation_context,
                system_prompt=system_prompt,
                analysis=analysis,
                is_rp=is_rp,
            )
            elapsed_response = (time.perf_counter() - start_response) * 1000
            metric.phase_response_ms = elapsed_response
            metric.response_success = bool(response)
            
            elapsed_total = (time.perf_counter() - start_total) * 1000
            metric.total_ms = elapsed_total
            
            if self.config["enable_metrics"]:
                self.metrics_tracker.record(metric)
                logger.info(
                    f"PersonaReAct: user={user_id} | tone={analysis.tone} | "
                    f"escalation={analysis.escalation_suggested}/10 | {elapsed_total:.0f}ms"
                )
            
            return response or "[Sem resposta]", analysis, metric
        
        except Exception as e:
            logger.exception(f"Erro em PersonaReAct: {e}")
            metric.error = str(e)
            return "[Erro ao gerar resposta]", None, metric
    
    async def _phase_analysis(
        self,
        user_message: str,
        context: str,
        system_prompt: str,
    ) -> Optional[PersonaReActAnalysis]:
        """FASE 1: Análise (T=0.3)."""
        
        analysis_prompt = f"""{system_prompt}

[ANÁLISE INTERNA - INVISÍVEL para usuário]
Contexto: {context}
Mensagem: "{user_message}"

Responda APENAS com JSON:
{{"tone": "aggressive|curious|vulnerable", "interlocutor_state": "tilted|stoic|devotee|competitive|philosophical|disinterested", "strategy": "...", "key_points": [], "escalation_suggested": 5}}

JSON:"""
        
        try:
            analysis_text = await asyncio.wait_for(
                self.generate(
                    prompt=analysis_prompt,
                    max_tokens=self.config["analysis_max_tokens"],
                    temperature=self.config["analysis_temperature"],
                ),
                timeout=self.config["analysis_timeout_sec"]
            )
            
            if not analysis_text:
                return None
            
            # Parse JSON
            analysis_json = self._safe_json_parse(analysis_text)
            if not analysis_json:
                return None
            
            return PersonaReActAnalysis(
                thinking=analysis_json.get("thinking", ""),
                tone=analysis_json.get("tone", "aggressive"),
                interlocutor_state=analysis_json.get("interlocutor_state", "unknown"),
                strategy=analysis_json.get("strategy", ""),
                key_points=analysis_json.get("key_points", []),
                escalation_suggested=min(10, max(1, int(analysis_json.get("escalation_suggested", 5)))),
            )
        
        except asyncio.TimeoutError:
            logger.error("Timeout na análise")
            return None
        except Exception as e:
            logger.error(f"Erro na análise: {e}")
            return None
    
    async def _phase_response(
        self,
        user_message: str,
        context: str,
        system_prompt: str,
        analysis: PersonaReActAnalysis,
        is_rp: bool = False,
    ) -> Optional[str]:
        """FASE 2: Resposta (T=0.9)."""
        
        max_tokens = 300 if is_rp else self.config["response_max_tokens"]
        hints = f"[tone: {analysis.tone} | escalation: {analysis.escalation_suggested}/10]"
        
        response_prompt = f"""{system_prompt}

{hints}

{context}

Usuário: {user_message}
Astéria:"""
        
        try:
            response = await asyncio.wait_for(
                self.generate(
                    prompt=response_prompt,
                    max_tokens=max_tokens,
                    temperature=self.config["response_temperature"],
                ),
                timeout=self.config["response_timeout_sec"]
            )
            return response
        
        except asyncio.TimeoutError:
            logger.error("Timeout na resposta")
            return None
        except Exception as e:
            logger.error(f"Erro na resposta: {e}")
            return None
    
    @staticmethod
    def _safe_json_parse(text: str) -> Optional[Dict]:
        """Parse JSON seguro."""
        try:
            text = text.strip()
            if text.startswith("```"):
                parts = text.split("```")
                if len(parts) >= 2:
                    text = parts[1].lstrip("json").strip()
            return json.loads(text)
        except:
            return None
    
    def get_metrics_stats(self) -> Dict:
        """Retorna stats de métricas."""
        return self.metrics_tracker.get_stats()
    
    def print_metrics_summary(self):
        """Printa resumo de métricas."""
        self.metrics_tracker.print_stats()
