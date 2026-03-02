import nextcord
from nextcord.ext import commands
from llm_client import generate
from prompts import ASTERIA_SYSTEM, CASUAL_TEMPLATE, RP_TEMPLATE
from config import CASUAL_MAX_TOKENS, RP_MAX_TOKENS
import logging

logger = logging.getLogger(__name__)

# Palavras para detecção de RP (pode ser expandido)
RP_WORDS = ["ação", "faz", "olha", "beija", "abraça", "toca", "segura", "sorri", "passa", "morde", "empurra", "sussurra"]

# Limite de caracteres da mensagem do usuário para evitar abuso
MAX_MESSAGE_LENGTH = 500

class Asteria(commands.Cog):
    """Cog de conversa com Astéria via comandos explícitos."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="asteria", aliases=["a"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def asteria_cmd(self, ctx, *, mensagem: str):
        """Fala diretamente com a Astéria. Ex: !asteria oi"""
        if ctx.author.bot: return

        if len(mensagem) > MAX_MESSAGE_LENGTH:
            await ctx.reply(f"❌ Mensagem muito longa!")
            return

        # Contexto do novo sistema
        context = self.bot.memory_system.get_context(
            mensagem, user_id=ctx.author.id, channel_id=ctx.channel.id
        )

        is_rp = "*" in mensagem or any(w in mensagem.lower() for w in RP_WORDS)
        
        async with ctx.typing():
            try:
                is_short = len(mensagem) < 15
                use_react = getattr(self.bot, "use_persona_react", True) and not is_short

                if use_react:
                    response, analysis, _ = await self.bot.persona_engine.analyze_and_respond(
                        user_message=mensagem,
                        conversation_context=context,
                        system_prompt=ASTERIA_SYSTEM,
                        is_rp=is_rp,
                        user_id=ctx.author.id
                    )
                else:
                    hints = "[tone: aggressive | escalation: 5/10]" if is_short else ""
                    prompt = CASUAL_TEMPLATE.format(
                        system=f"{ASTERIA_SYSTEM}\n\n{hints}",
                        memory=context,
                        mensagem=mensagem
                    )
                    response = await generate(prompt, max_tokens=RP_MAX_TOKENS if is_rp else CASUAL_MAX_TOKENS)

                if response:
                    response = response.split("<|")[0].strip()
                    await ctx.reply(response)
                    
                    # Salva em ambos os sistemas para compatibilidade
                    self.bot.memory_manager.get(ctx.channel.id).add(mensagem, response)
                    self.bot.memory_system.add_interaction(
                        mensagem, response, 
                        user_id=ctx.author.id, 
                        channel_id=ctx.channel.id
                    )
                else:
                    await ctx.reply("🤖 Sem resposta do modelo.")
            except Exception:
                logger.exception("Erro no asteria_cmd")
                await ctx.reply("❌ Erro interno.")

    @commands.command(name="limpar_memoria", aliases=["clearmem", "resetar"])
    async def limpar_memoria(self, ctx):
        """Limpa o histórico de conversa de ambos os sistemas."""
        # Limpa legado
        self.bot.memory_manager.clear(ctx.channel.id)
        
        # Limpa novo sistema (apenas o estado de densidade e curto prazo do canal)
        cid = str(ctx.channel.id)
        if cid in self.bot.memory_system.density_states:
            del self.bot.memory_system.density_states[cid]
        if cid in self.bot.memory_system.short_term:
            del self.bot.memory_system.short_term[cid]
            
        await ctx.send("🧹 Memória completa do canal (Legada + Avançada) apagada.")

    @commands.command(name="historico", aliases=["memory"])
    async def historico(self, ctx):
        """Mostra o histórico de conversa do canal (Novo Sistema)."""
        context = self.bot.memory_system.get_context(
            "resumo", user_id=ctx.author.id, channel_id=ctx.channel.id
        )
        if not context or context.isspace():
            return await ctx.send("📭 Nenhum histórico no momento.")

        if len(context) > 3900:
            context = context[:3900] + "..."
            
        embed = nextcord.Embed(
            title="📋 Histórico Avançado (Contexto)",
            description=f"```{context}```",
            color=0xB388FF,
        )
        await ctx.send(embed=embed)

    @commands.command(name="astping")
    async def astping(self, ctx):
        """Verifica se o modelo LLM está respondendo (ping no Kobold)."""
        async with ctx.typing():
            try:
                # Prompt simples de teste
                test_prompt = ASTERIA_SYSTEM + "\n\nUsuário: Oi, tudo bem?\nAstéria:"
                response = await generate(test_prompt, max_tokens=20)
                if response:
                    await ctx.reply(f"🏓 **Pong!** Modelo respondeu: `{response[:50]}...`")
                else:
                    await ctx.reply("⚠️ Modelo respondeu com vazio.")
            except Exception as e:
                logger.exception("Erro no astping")
                await ctx.reply("❌ Falha ao contactar o modelo LLM.")

def setup(bot):
    bot.add_cog(Asteria(bot))