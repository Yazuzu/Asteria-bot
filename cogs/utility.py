import nextcord
from nextcord.ext import commands
import logging
import platform

logger = logging.getLogger(__name__)


class Utility(commands.Cog):
    """Utilitários gerais."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ping")
    async def ping(self, ctx):
        """Latência do bot em ms."""
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"🏓 **Pong!** `{latency}ms`")

    @commands.command(name="info", aliases=["serverinfo"])
    @commands.guild_only()
    async def info(self, ctx):
        """Informações do servidor."""
        g = ctx.guild
        embed = nextcord.Embed(
            title=g.name,
            description=g.description or "Sem descrição",
            color=0xB388FF,
        )
        embed.set_thumbnail(url=g.icon.url if g.icon else None)
        embed.add_field(name="👑 Dono", value=g.owner.mention, inline=True)
        embed.add_field(name="👥 Membros", value=g.member_count, inline=True)
        embed.add_field(name="💬 Canais", value=len(g.channels), inline=True)
        embed.add_field(name="🎭 Cargos", value=len(g.roles), inline=True)
        embed.add_field(name="🌍 Região", value=str(g.preferred_locale), inline=True)
        embed.add_field(name="📅 Criado", value=g.created_at.strftime("%d/%m/%Y"), inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="userinfo", aliases=["perfil"])
    @commands.guild_only()
    async def userinfo(self, ctx, member: nextcord.Member = None):
        """Info de um usuário. Ex: !userinfo @membro"""
        member = member or ctx.author
        embed = nextcord.Embed(
            title=str(member),
            color=member.color,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="🆔 ID", value=member.id, inline=True)
        embed.add_field(name="📛 Nick", value=member.display_name, inline=True)
        embed.add_field(name="🤖 Bot?", value="Sim" if member.bot else "Não", inline=True)
        embed.add_field(
            name="📅 Entrou",
            value=member.joined_at.strftime("%d/%m/%Y") if member.joined_at else "Desconhecido",
            inline=True,
        )
        embed.add_field(
            name="📅 Conta criada",
            value=member.created_at.strftime("%d/%m/%Y"),
            inline=True,
        )
        top_role = member.top_role.mention if member.top_role.name != "@everyone" else "Nenhum"
        embed.add_field(name="🎭 Cargo", value=top_role, inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="ajuda", aliases=["comandos"])
    async def ajuda(self, ctx):
        """Lista de comandos disponíveis."""
        embed = nextcord.Embed(
            title="📖 Comandos da Astéria",
            color=0xB388FF,
        )
        embed.add_field(
            name="🔧 Utilitários",
            value="`!ping` `!info` `!userinfo` `!ajuda`",
            inline=False,
        )
        embed.add_field(
            name="🎮 Diversão",
            value="`!roll <N>` `!coinflip` `!escolha a|b|c` `!8ball <pergunta>` `!rps <pedra/papel/tesoura>`",
            inline=False,
        )
        embed.add_field(
            name="🛡️ Moderação",
            value="`!clear <N>` `!kick @user` `!ban @user` `!mute @user`",
            inline=False,
        )
        embed.add_field(
            name="💬 Astéria",
            value="`!asteria <msg>` `!limpar_memoria`\nOu simplesmente fale normalmente — ela está ouvindo.",
            inline=False,
        )
        embed.set_footer(text="Use os comandos com ! ou fale diretamente comigo.")
        await ctx.send(embed=embed)

    @commands.command(name="avatar")
    async def avatar(self, ctx, member: nextcord.Member = None):
        """Mostra o avatar de um usuário."""
        member = member or ctx.author
        embed = nextcord.Embed(title=f"Avatar de {member.display_name}", color=0xB388FF)
        embed.set_image(url=member.display_avatar.url)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Utility(bot))
