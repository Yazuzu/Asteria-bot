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
    @commands.cooldown(1, 5, commands.BucketType.user)  # 1 uso a cada 5s por usuário
    async def asteria_cmd(self, ctx, *, mensagem: str):
        """Fala diretamente com a Astéria. Ex: !asteria oi"""

        # 1. Ignorar bots (segurança extra)
        if ctx.author.bot:
            return

        # 2. Validar tamanho da mensagem
        if len(mensagem) > MAX_MESSAGE_LENGTH:
            await ctx.reply(f"❌ Mensagem muito longa! Limite de {MAX_MESSAGE_LENGTH} caracteres.")
            return

        # 3. Obter memória do canal
        mem = self.bot.memory_manager.get(ctx.channel.id)

        # 4. Detectar se é roleplay
        is_rp = "*" in mensagem or any(w in mensagem.lower() for w in RP_WORDS)
        template = RP_TEMPLATE if is_rp else CASUAL_TEMPLATE
        max_tokens = RP_MAX_TOKENS if is_rp else CASUAL_MAX_TOKENS

        # 5. Montar prompt
        prompt = template.format(
            system=ASTERIA_SYSTEM,
            memory=mem.get_context(),
            mensagem=mensagem
        )

        # 6. Log da requisição (modo debug)
        logger.debug(f"Prompt para {ctx.author} (ID: {ctx.author.id}): {prompt[:200]}...")

        # 7. Indicar digitação e chamar o LLM
        async with ctx.typing():
            try:
                response = await generate(prompt, max_tokens=max_tokens)
            except Exception as e:
                logger.exception("Erro ao gerar resposta")
                await ctx.reply("❌ Erro interno ao processar sua mensagem. Tente novamente mais tarde.")
                return

        # 8. Validar resposta
        if not response or response.isspace():
            await ctx.reply("🤖 O modelo não retornou nenhuma resposta. Talvez esteja ocupado.")
            return

        # 9. Responder e salvar memória (respondendo UMA vez só)
        await ctx.reply(response)
        mem.add(mensagem, response)

    @asteria_cmd.error
    async def asteria_error(self, ctx, error):
        """Tratamento de erros específicos do comando."""
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ Me diga algo. Ex: `!asteria oi Astéria`")
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(f"⏳ Calma aí! Espere {error.retry_after:.1f}s para falar de novo.")
        else:
            logger.error(f"Erro inesperado no comando asteria: {error}", exc_info=True)
            await ctx.reply("❌ Ocorreu um erro inesperado. Verifique os logs do bot.")

    @commands.command(name="limpar_memoria", aliases=["clearmem", "resetar"])
    async def limpar_memoria(self, ctx):
        """Limpa o histórico de conversa do canal atual."""
        self.bot.memory_manager.clear(ctx.channel.id)
        await ctx.send("🧹 Memória do canal apagada.")

    @commands.command(name="historico", aliases=["memory"])
    async def historico(self, ctx):
        """Mostra o histórico de conversa do canal."""
        mem = self.bot.memory_manager.get(ctx.channel.id)
        context = mem.get_context()
        if not context:
            return await ctx.send("📭 Nenhum histórico no momento.")
        # Limitar tamanho do embed
        if len(context) > 3900:
            context = context[:3900] + "..."
        embed = nextcord.Embed(
            title="📋 Histórico do Canal",
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