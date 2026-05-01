#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py — Entry point do Asteria-bot
REFATORADO COM LÓGICA LIMPA E SEM RACE CONDITIONS
"""

import nextcord
from nextcord.ext import commands
import logging
import logging.handlers
import asyncio
from typing import Optional

from config import DISCORD_TOKEN, OWNER_IDS, LOGS_DIR, ENABLE_PERF_LOGGING
from memory import MemoryManager
from llm_client import generate, LLMClientError
from prompts import ASTERIA_SYSTEM, CASUAL_TEMPLATE, RP_TEMPLATE
from memory_system import MemoryService
from persona_react_engine import PersonaReActEngine
from asteria_conversation import AsteriaConversation
from config import USE_PERSONA_REACT

# ──────────────────────────────────────────────────────────────────────────────
# LOGGING SETUP
# ──────────────────────────────────────────────────────────────────────────────

handler = logging.handlers.RotatingFileHandler(
    LOGS_DIR / "asteria.log",
    maxBytes=5_000_000,
    backupCount=3,
    encoding="utf-8",
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[handler, logging.StreamHandler()],
)
logger = logging.getLogger("asteria.main")

# ──────────────────────────────────────────────────────────────────────────────
# BOT SETUP
# ──────────────────────────────────────────────────────────────────────────────

intents = nextcord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Injetar dependências
bot.memory_manager = MemoryManager()
bot.memory_service = MemoryService()
bot.persona_engine = PersonaReActEngine(generate)
bot.asteria = AsteriaConversation(bot.memory_service, bot.persona_engine)
bot.use_persona_react = USE_PERSONA_REACT

# ──────────────────────────────────────────────────────────────────────────────
# EVENTS
# ──────────────────────────────────────────────────────────────────────────────


@bot.event
async def on_ready() -> None:
    """Evento de ready do bot."""
    logger.info(f"✨ Logado como {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(activity=nextcord.Game(name="!ajuda | Astéria"))


@bot.event
async def on_message(message: nextcord.Message) -> None:
    """
    Handler de mensagens.
    LÓGICA REFATORADA: Processa comandos OU conversa, não ambos.
    """
    # Ignorar mensagens do próprio bot
    if message.author.bot:
        return

    # Detectar contextos especiais
    is_mentioned = bot.user in message.mentions
    is_dm = isinstance(message.channel, nextcord.DMChannel)
    is_reply_to_bot = (
        message.reference
        and message.reference.cached_message
        and message.reference.cached_message.author == bot.user
    )
    is_command = message.content.startswith("!")

    logger.debug(
        f"Mensagem de {message.author}: "
        f"cmd={is_command}, mention={is_mentioned}, dm={is_dm}, reply={is_reply_to_bot}"
    )

    # LÓGICA CLARA:
    # 1. Se é comando com !, processa comando (e retorna)
    # 2. Se não é comando OU é menção/dm/reply, processa com Astéria

    if is_command:
        # Processa APENAS o comando, não chama Astéria
        await bot.process_commands(message)
        return

    # Para mensagens normais, verifica se deve ativar Astéria
    should_respond = is_mentioned or is_dm or is_reply_to_bot

    if should_respond or is_dm:
        await handle_asteria_message(message)


# ──────────────────────────────────────────────────────────────────────────────
# LLM HANDLER
# ──────────────────────────────────────────────────────────────────────────────


async def handle_asteria_message(message: nextcord.Message) -> None:
    """
    Handler principal para conversa com Astéria.

    Args:
        message: Mensagem do Discord
    """
    user_msg = message.clean_content.strip()

    # Validação
    if not user_msg:
        logger.debug(f"Mensagem vazia de {message.author}")
        return

    # Detectar RP simples
    is_rp = "*" in user_msg or any(
        w in user_msg.lower()
        for w in ["ação", "faz", "olha", "beija", "abraça", "toca", "segura"]
    )

    try:
        async with message.channel.typing():
            logger.info(
                f"Processing: {message.author} ({message.author.id}) "
                f"in {message.channel.name} [RP={is_rp}]"
            )

            # Chamar pipeline de conversação (orquestra tudo)
            response = await bot.asteria.process_message(
                user_msg,
                user_id=message.author.id,
                channel_id=message.channel.id,
                is_rp=is_rp,
            )

            # Enviar resposta
            if response:
                # Limpar response de possíveis artefatos
                response = response.strip()
                if len(response) > 2000:
                    # Discord limit de 2000 chars
                    response = response[:1997] + "..."

                await message.reply(response, mention_author=False)
                logger.info(f"✓ Resposta enviada ({len(response)} chars)")
            else:
                logger.warning(f"Resposta vazia para {message.author}")
                await message.reply(
                    "[Astéria ficou processando... tente novamente]",
                    mention_author=False,
                )

    except LLMClientError as e:
        logger.error(f"Erro de LLM: {e}")
        await message.reply(
            f"❌ Erro ao conectar com o modelo: {str(e)[:100]}",
            mention_author=False,
        )

    except asyncio.TimeoutError:
        logger.error(f"Timeout ao processar mensagem de {message.author}")
        await message.reply(
            "⏱️ Demorou demais... tente novamente em alguns segundos.",
            mention_author=False,
        )

    except Exception as e:
        logger.exception(f"Erro inesperado ao processar mensagem")
        await message.reply(
            f"💥 Erro interno: {str(e)[:50]}... (verifique logs)",
            mention_author=False,
        )


# ──────────────────────────────────────────────────────────────────────────────
# COG LOADER
# ──────────────────────────────────────────────────────────────────────────────


async def load_cogs() -> None:
    """Carrega cogs dinamicamente."""
    from pathlib import Path

    cogs_dir = Path("cogs")
    if not cogs_dir.exists():
        logger.warning("Diretório 'cogs' não encontrado")
        return

    for cog_file in cogs_dir.glob("*.py"):
        if cog_file.name.startswith("_"):
            continue

        cog_name = cog_file.stem
        try:
            bot.load_extension(f"cogs.{cog_name}")
            logger.info(f"✓ Cog carregado: {cog_name}")
        except Exception as e:
            logger.error(f"✗ Erro ao carregar cog {cog_name}: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────


async def main() -> None:
    """Ponto de entrada async."""
    logger.info("🚀 Iniciando Asteria-bot...")
    logger.info(f"   - Owner IDs: {OWNER_IDS}")
    logger.info(f"   - PersonaReAct: {USE_PERSONA_REACT}")
    logger.info(f"   - Perf Logging: {ENABLE_PERF_LOGGING}")

    async with bot:
        await load_cogs()
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n⏹️  Bot interrompido pelo usuário")
    except Exception as e:
        logger.exception(f"Erro fatal ao iniciar bot: {e}")
        exit(1)
