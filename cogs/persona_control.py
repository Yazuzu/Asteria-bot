#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cogs/persona_control.py — Controle PersonaReAct em runtime"""

import nextcord
from nextcord.ext import commands
from config import OWNER_IDS
import logging

logger = logging.getLogger(__name__)


def is_owner():
    """Decorator para verificar se é owner."""
    async def predicate(ctx):
        return ctx.author.id in OWNER_IDS
    return commands.check(predicate)


class PersonaControl(commands.Cog):
    """Controle de PersonaReAct em runtime."""

    def __init__(self, bot):
        self.bot = bot
        # Garante que o atributo existe no bot
        if not hasattr(self.bot, "use_persona_react"):
            self.bot.use_persona_react = True

    @commands.command(name="persona_toggle", aliases=["pt"])
    @is_owner()
    async def persona_toggle(self, ctx):
        """Alterna PersonaReAct on/off."""
        self.bot.use_persona_react = not self.bot.use_persona_react
        status = "✅ ATIVADO" if self.bot.use_persona_react else "❌ DESABILITADO"
        
        embed = nextcord.Embed(
            title="🎭 PersonaReAct",
            description=f"O sistema de análise em duas etapas está {status}.",
            color=0x00FF00 if self.bot.use_persona_react else 0xFF0000,
        )
        await ctx.send(embed=embed)
        logger.info(f"PersonaReAct toggled: {self.bot.use_persona_react}")

    @commands.command(name="persona_test")
    @is_owner()
    async def persona_test(self, ctx, *, mensagem: str):
        """Testa PersonaReAct com uma mensagem direta."""
        from llm_client_react import generate_with_react
        from prompts import ASTERIA_SYSTEM
        
        async with ctx.typing():
            try:
                # Simulando contexto vazio para o teste
                response, analysis = await generate_with_react(
                    user_message=mensagem,
                    conversation_context="[Histórico de teste vazio]",
                    system_prompt=ASTERIA_SYSTEM,
                    is_rp="*" in mensagem,
                    user_id=ctx.author.id,
                )
            except Exception as e:
                logger.exception("Erro no persona_test")
                await ctx.reply(f"❌ Erro: {e}")
                return
        
        embed = nextcord.Embed(title="🎭 Teste PersonaReAct", color=0xB388FF)
        embed.add_field(name="Sua Mensagem", value=f"```{mensagem}```", inline=False)
        embed.add_field(name="Resposta da Astéria", value=f"```{response}```", inline=False)
        
        if analysis:
            embed.add_field(
                name="📊 Análise Interna",
                value=f"```Tone: {analysis.get('tone')}\nEscalation: {analysis.get('escalation')}/10\nStrategy: {analysis.get('strategy', 'N/A')}```",
                inline=False
            )
        
        await ctx.send(embed=embed)

    @commands.command(name="persona_status")
    @is_owner()
    async def persona_status(self, ctx):
        """Mostra status atual do motor de personalidade."""
        status = "✅ Ativo" if getattr(self.bot, "use_persona_react", True) else "❌ Inativo"
        
        embed = nextcord.Embed(
            title="🎭 Status PersonaReAct",
            description=f"O sistema está atualmente {status}.",
            color=0xB388FF,
        )
        
        mode_desc = "PersonaReAct (Análise de Perfil + Resposta Estratégica)" if getattr(self.bot, "use_persona_react", True) else "Modo Direto (Simples)"
        embed.add_field(name="Modo de Operação", value=mode_desc, inline=False)
        
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(PersonaControl(bot))
