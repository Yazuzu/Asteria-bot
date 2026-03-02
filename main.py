import nextcord
from nextcord.ext import commands
import logging
import logging.handlers
import asyncio
from config import DISCORD_TOKEN, OWNER_IDS
from memory import MemoryManager
from llm_client import generate
from prompts import ASTERIA_SYSTEM, CASUAL_TEMPLATE, RP_TEMPLATE

# ── Logging ────────────────────────────────────────────────────────────────────
handler = logging.handlers.RotatingFileHandler(
    "logs/asteria.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[handler, logging.StreamHandler()],
)
logger = logging.getLogger("Astéria")

# ── Bot setup ──────────────────────────────────────────────────────────────────
intents = nextcord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.memory_manager = MemoryManager()

# ── Events ─────────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    logger.info(f"✨ Logado como {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(activity=nextcord.Game(name="!ajuda | Astéria"))

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Detecta se é menção, DM ou reply ao bot
    is_mentioned = bot.user in message.mentions
    is_dm = isinstance(message.channel, nextcord.DMChannel)
    is_reply_to_bot = (
        message.reference
        and message.reference.cached_message
        and message.reference.cached_message.author == bot.user
    )

    # Processa comandos !prefix SEMPRE
    await bot.process_commands(message)

    # Só chama Astéria se NÃO for um comando com ! ou se for mencionado/dm/reply
    if not message.content.startswith("!") or is_mentioned or is_dm or is_reply_to_bot:
        # Evita processar se for um comando reconhecido com !
        ctx = await bot.get_context(message)
        if ctx.command:
            return  # já foi processado acima
        await handle_asteria_message(message)

# ── LLM handler ────────────────────────────────────────────────────────────────
async def handle_asteria_message(message):
    mem = bot.memory_manager.get(message.channel.id)
    user_msg = message.clean_content.strip()

    if not user_msg:
        return

    # Detecção simples de RP
    is_rp = "*" in user_msg or any(
        word in user_msg.lower()
        for word in ["ação", "faz", "olha", "beija", "abraça", "toca", "segura"]
    )

    template = RP_TEMPLATE if is_rp else CASUAL_TEMPLATE
    max_tokens = 300 if is_rp else 80

    # Obtém o histórico e limita a um tamanho razoável (últimas 6 trocas)
    full_history = mem.get_context()
    history_lines = full_history.splitlines()
    if len(history_lines) > 12:  # 6 trocas (cada troca tem 2 linhas)
        history_lines = history_lines[-12:]
    limited_history = "\n".join(history_lines) + ("\n" if history_lines else "")

    # Monta o prompt com as chaves corretas
    prompt = template.format(
        system=ASTERIA_SYSTEM,
        memory=limited_history,
        mensagem=user_msg,          # chave 'mensagem' (como definido no template)
    )

    # Log do prompt para depuração
    logger.info(f"🔍 Prompt enviado ao LLM (primeiros 500 caracteres): {prompt[:500]}...")

    try:
        async with message.channel.typing():
            response = await generate(prompt, max_tokens=max_tokens)

        if response:
            # Remove possíveis tokens residuais
            response = response.split("<|")[0].strip()
            await message.channel.send(response)
            # Adiciona ao histórico (sem passar o channel_id)
            mem.add(user_msg, response)
        else:
            await message.channel.send("[Sem resposta do modelo]")
    except Exception:
        logger.exception("Erro na geração de resposta")
        await message.channel.send("[Erro interno. Tente novamente.]")

# ── Cog loader ─────────────────────────────────────────────────────────────────
async def load_cogs():
    for cog in ["moderation", "fun", "utility", "owner", "asteria", "template"]:
        try:
            bot.load_extension(f"cogs.{cog}")
            logger.info(f"✅ Cog carregado: {cog}")
        except Exception as e:
            logger.error(f"❌ Falha ao carregar {cog}: {e}", exc_info=True)

# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(load_cogs())
    bot.run(DISCORD_TOKEN)