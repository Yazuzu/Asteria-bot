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

        is_rp = "*" in mensagem or any(w in mensagem.lower() for w in RP_WORDS)
        
        async with ctx.typing():
            try:
                # O AsteriaConversation agora orquestra tudo
                response = await self.bot.asteria.process_message(
                    mensagem, 
                    user_id=ctx.author.id, 
                    channel_id=ctx.channel.id,
                    is_rp=is_rp
                )

                if response:
                    # Fail-safe para limpar prefixos de turno
                    for prefix in ["Astéria:", "Asteria:", "User:", "Usuário:"]:
                        if response.startswith(prefix): response = response[len(prefix):].strip()
                            
                    await ctx.reply(response)
                    
                    # Atualiza legado
                    self.bot.memory_manager.get(ctx.channel.id).add(mensagem, response)
                else:
                    await ctx.reply("🤖 Sem resposta do modelo.")
            except Exception:
                logger.exception("Erro no asteria_cmd")
                await ctx.reply("❌ Erro interno.")

    @commands.command(name="limpar_memoria", aliases=["clearmem", "resetar"])
    async def limpar_memoria(self, ctx):
        """Limpa todo o histórico (Legado + LanceDB + Densidade) do canal."""
        self.bot.memory_manager.clear(ctx.channel.id)
        self.bot.memory_service.clear_channel_memory(ctx.channel.id)
        await ctx.send("🧹 Memória absoluta e irreversível do canal apagada.")

    @commands.command(name="historico", aliases=["memory"])
    async def historico(self, ctx):
        """Mostra o histórico de conversa do canal (Contexto Atual)."""
        context = self.bot.memory_service.get_context(
            "resumo", user_id=ctx.author.id, channel_id=ctx.channel.id
        )
        if not context or context.isspace():
            return await ctx.send("📭 Nenhum histórico no momento.")

        if len(context) > 3900: context = context[:3900] + "..."
            
        embed = nextcord.Embed(
            title="📋 Histórico / Contexto Recuperado",
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