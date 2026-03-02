import nextcord
from nextcord.ext import commands
from config import OWNER_IDS
import logging

logger = logging.getLogger(__name__)


def is_mod():
    async def predicate(ctx):
        return ctx.author.guild_permissions.manage_messages
    return commands.check(predicate)


class Moderation(commands.Cog):
    """Comandos de moderação."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="clear", aliases=["limpar"])
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def clear(self, ctx, amount: int = 10):
        """Apaga N mensagens do canal. Ex: !clear 10"""
        if amount < 1 or amount > 100:
            return await ctx.send("❌ Quantidade deve ser entre 1 e 100.", delete_after=5)
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"🗑️ {len(deleted) - 1} mensagens deletadas.", delete_after=5)

    @commands.command(name="kick")
    @commands.has_permissions(kick_members=True)
    @commands.guild_only()
    async def kick(self, ctx, member: nextcord.Member, *, reason: str = "Sem motivo"):
        """Expulsa um membro. Ex: !kick @membro motivo"""
        await member.kick(reason=reason)
        await ctx.send(f"👢 **{member.name}** foi expulso. Motivo: {reason}")

    @commands.command(name="ban")
    @commands.has_permissions(ban_members=True)
    @commands.guild_only()
    async def ban(self, ctx, member: nextcord.Member, *, reason: str = "Sem motivo"):
        """Bane um membro. Ex: !ban @membro motivo"""
        await member.ban(reason=reason)
        await ctx.send(f"🔨 **{member.name}** foi banido. Motivo: {reason}")

    @commands.command(name="unban")
    @commands.has_permissions(ban_members=True)
    @commands.guild_only()
    async def unban(self, ctx, *, user_tag: str):
        """Remove ban. Ex: !unban Usuario#1234"""
        banned = [entry async for entry in ctx.guild.bans()]
        for ban_entry in banned:
            if str(ban_entry.user) == user_tag:
                await ctx.guild.unban(ban_entry.user)
                return await ctx.send(f"✅ **{user_tag}** desbanido.")
        await ctx.send(f"❌ Usuário **{user_tag}** não encontrado nos banidos.")

    @commands.command(name="mute")
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def mute(self, ctx, member: nextcord.Member, *, reason: str = "Sem motivo"):
        """Silencia um membro com timeout de 10 min. Ex: !mute @membro"""
        import datetime
        await member.timeout(datetime.timedelta(minutes=10), reason=reason)
        await ctx.send(f"🔇 **{member.name}** silenciado por 10 minutos. Motivo: {reason}")

    # ── Error handlers ──────────────────────────────────────────────────────────
    @clear.error
    @kick.error
    @ban.error
    @unban.error
    @mute.error
    async def mod_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Você não tem permissão para isso.", delete_after=5)
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ Membro não encontrado.", delete_after=5)
        elif isinstance(error, commands.BadArgument):
            await ctx.send("❌ Argumento inválido.", delete_after=5)
        else:
            logger.error(f"Erro em moderação: {error}", exc_info=True)
            await ctx.send("❌ Ocorreu um erro interno.", delete_after=5)


def setup(bot):
    bot.add_cog(Moderation(bot))
