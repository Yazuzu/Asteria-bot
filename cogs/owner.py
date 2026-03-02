import nextcord
from nextcord.ext import commands
from config import OWNER_IDS
import logging
import io
import traceback
import textwrap
import contextlib
import asyncio

logger = logging.getLogger(__name__)


def is_owner():
    async def predicate(ctx):
        return ctx.author.id in OWNER_IDS
    return commands.check(predicate)





class Owner(commands.Cog):
    """Comandos exclusivos do owner."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="reload")
    @is_owner()
    async def reload(self, ctx, cog: str):
        """Recarrega um cog em runtime. Ex: !reload fun"""
        try:
            self.bot.reload_extension(f"cogs.{cog}")
            await ctx.send(f"♻️ Cog `{cog}` recarregado com sucesso.")
        except Exception as e:
            await ctx.send(f"❌ Erro ao recarregar `{cog}`: `{e}`")

    @commands.command(name="load")
    @is_owner()
    async def load(self, ctx, cog: str):
        """Carrega um cog. Ex: !load utility"""
        try:
            self.bot.load_extension(f"cogs.{cog}")
            await ctx.send(f"✅ Cog `{cog}` carregado.")
        except Exception as e:
            await ctx.send(f"❌ Erro: `{e}`")

    @commands.command(name="unload")
    @is_owner()
    async def unload(self, ctx, cog: str):
        """Descarrega um cog. Ex: !unload fun"""
        try:
            self.bot.unload_extension(f"cogs.{cog}")
            await ctx.send(f"🔌 Cog `{cog}` descarregado.")
        except Exception as e:
            await ctx.send(f"❌ Erro: `{e}`")

    @commands.command(name="status")
    @is_owner()
    async def status(self, ctx, *, texto: str):
        """Muda o status do bot. Ex: !status em modo silencioso"""
        await self.bot.change_presence(activity=nextcord.Game(name=texto))
        await ctx.send(f"✅ Status alterado para: **{texto}**")

    @commands.command(name="eval", aliases=["exec"])
    @is_owner()
    async def eval_code(self, ctx, *, code: str):
        """Executa código Python (OWNER ONLY). Ex: !eval 1+1"""
        env = {"bot": self.bot, "ctx": ctx, "nextcord": nextcord}
        code = code.strip("` \n").lstrip("python\n")
        stdout = io.StringIO()
        try:
            exec_code = f"async def _exec():\n{textwrap.indent(code, '    ')}"
            exec(exec_code, env)
            with contextlib.redirect_stdout(stdout):
                result = await env["_exec"]()
            output = stdout.getvalue() or (str(result) if result is not None else "OK")
        except Exception:
            output = traceback.format_exc()
        await ctx.send(f"```py\n{output[:1900]}\n```")



    @commands.command(name="shutdown", aliases=["desligar"])
    @is_owner()
    async def shutdown(self, ctx):
        """Desliga o bot (OWNER ONLY)."""
        await ctx.send("👋 Até logo...")
        await self.bot.close()

    @reload.error
    @load.error
    @unload.error
    @status.error
    @eval_code.error
    @shutdown.error
    async def owner_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("🔒 Apenas o owner pode usar esse comando.", delete_after=5)


def setup(bot):
    bot.add_cog(Owner(bot))
