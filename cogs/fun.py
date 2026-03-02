import random
import logging
from typing import Optional

import nextcord
from nextcord.ext import commands

logger = logging.getLogger(__name__)

# === WORKAROUND PARA O BUG DO COOLDOWN (se ainda necessário) ===
def user_cooldown_key(ctx):
    """Callable que substitui BucketType.user."""
    return ctx.author.id


class Fun(commands.Cog):
    """Comandos de diversão (agora mais robustos)."""

    def __init__(self, bot):
        self.bot = bot
        # Cache de GIFs usando URLs públicas confiáveis (Tenor, Giphy)
        self.gif_cache = {
            "hug": [
                "https://tenor.com/view/hug-cuddle-love-sweet-gif-12993733",
                "https://tenor.com/view/bear-hug-love-cute-gif-12005309",
            ],
            "kiss": [
                "https://tenor.com/view/kiss-love-couple-romantic-gif-14856629",
                "https://tenor.com/view/kiss-love-smooch-couple-romantic-gif-12651221",
            ],
            "slap": [
                "https://tenor.com/view/slap-hit-gif-12517677",
                "https://tenor.com/view/slap-fight-angry-gif-17213691",
            ],
            "pat": [
                "https://tenor.com/view/head-pat-cute-pat-gif-16977699",
                "https://tenor.com/view/pat-head-cat-gif-17210693",
            ],
        }

    # ==================== COMANDOS REFATORADOS ====================

    @commands.command(name="roll", aliases=["dado"])
    @commands.cooldown(1, 4, user_cooldown_key)
    async def roll(self, ctx, sides: int = 6):
        """
        Rola um dado de N lados (2 a 1000).
        Uso: `!roll 20`
        """
        result = random.randint(1, sides)
        embed = nextcord.Embed(
            title="🎲 Rolagem",
            description=f"**d{sides}** → **{result}**",
            color=0x00FF00,
        )
        await ctx.send(embed=embed)

    @commands.command(name="coinflip", aliases=["moeda", "flip"])
    @commands.cooldown(1, 3, user_cooldown_key)
    async def coinflip(self, ctx):
        """Joga uma moeda (cara ou coroa)."""
        result = random.choice(["🟡 **Cara**", "⚫ **Coroa**"])
        await ctx.send(f"🪙 {result}!")

    @commands.command(name="escolha", aliases=["choose"])
    @commands.cooldown(1, 5, user_cooldown_key)
    async def escolha(self, ctx, *, opcoes: str):
        """
        Escolhe aleatoriamente entre opções separadas por |.
        Ex: `!escolha pizza | lasanha | temaki`
        """
        items = [o.strip() for o in opcoes.split("|") if o.strip()]
        if len(items) < 2:
            return await ctx.send("❌ **Pelo menos 2 opções** separadas por `|`.")
        chosen = random.choice(items)
        await ctx.send(f"🎯 Eu escolho: **{chosen}**")

    @commands.command(name="8ball", aliases=["bola8"])
    @commands.cooldown(1, 6, user_cooldown_key)
    async def eight_ball(self, ctx, *, pergunta: str = None):
        """Pergunta à bola 8 mágica."""
        if not pergunta:
            return await ctx.send("❌ Me faça uma pergunta!")
        respostas = [
            "Sim, com certeza.",
            "Provavelmente sim.",
            "Não conte com isso.",
            "Minhas fontes dizem não.",
            "Pergunte novamente mais tarde.",
        ]
        await ctx.send(f"🎱 **{pergunta}**\n→ **{random.choice(respostas)}**")

    @commands.command(name="rps", aliases=["jokenpo", "ppt"])
    @commands.cooldown(1, 4, user_cooldown_key)
    async def rps(self, ctx, escolha: str = None):
        """
        Pedra, papel ou tesoura.
        Uso: `!rps pedra`
        """
        if not escolha:
            return await ctx.send("❌ Use: `!rps pedra | papel | tesoura`")

        opcoes = {
            "pedra": "🪨",
            "papel": "📄",
            "tesoura": "✂️",
            "rock": "🪨",
            "paper": "📄",
            "scissors": "✂️",
        }
        user = escolha.lower()
        if user not in opcoes:
            return await ctx.send("❌ Escolha: **pedra**, **papel** ou **tesoura**.")

        bot_choice = random.choice(["pedra", "papel", "tesoura"])
        wins = {"pedra": "tesoura", "papel": "pedra", "tesoura": "papel"}

        if user == bot_choice:
            resultado = "Empate 🤝"
        elif wins[user] == bot_choice:
            resultado = "Você ganhou! 🏆"
        else:
            resultado = "Você perdeu! 💀"

        await ctx.send(
            f"Você: {opcoes[user]} | Eu: {opcoes[bot_choice]}\n**{resultado}**"
        )

    # ==================== NOVOS COMANDOS REFORÇADOS ====================

    @commands.command(name="hug", aliases=["abraço"])
    @commands.cooldown(1, 8, user_cooldown_key)
    async def hug(self, ctx, member: nextcord.Member = None):
        """Abrace alguém (mencione o membro)."""
        if not member or member == ctx.author:
            return await ctx.send("❌ Mencione **outra pessoa** para abraçar!")
        gif = random.choice(self.gif_cache["hug"])
        embed = nextcord.Embed(
            description=f"{ctx.author.mention} deu um abraço apertado em {member.mention} ❤️",
            color=0xFF69B4,
        )
        embed.set_image(url=gif)
        await ctx.send(embed=embed)

    @commands.command(name="kiss", aliases=["beijo"])
    @commands.cooldown(1, 10, user_cooldown_key)
    async def kiss(self, ctx, member: nextcord.Member = None):
        """Beije alguém (mencione)."""
        if not member:
            return await ctx.send("❌ Mencione alguém para beijar!")
        gif = random.choice(self.gif_cache["kiss"])
        embed = nextcord.Embed(
            description=f"{ctx.author.mention} deu um beijo em {member.mention} 💋",
            color=0xFF1493,
        )
        embed.set_image(url=gif)
        await ctx.send(embed=embed)

    @commands.command(name="ship")
    @commands.cooldown(1, 7, user_cooldown_key)
    async def ship(self, ctx, user1: nextcord.Member, user2: Optional[nextcord.Member] = None):
        """
        Calcula a compatibilidade entre dois membros.
        Se apenas um for mencionado, shippa com você mesmo.
        """
        if user2 is None:
            user2 = ctx.author

        percent = random.randint(0, 100)
        # Gera um nome combinando partes dos dois nomes
        name1 = user1.display_name[:4]
        name2 = user2.display_name[-4:]
        ship_name = (name1 + name2).capitalize()
        hearts = "❤️" * (percent // 20) + "🖤" * (5 - (percent // 20))

        embed = nextcord.Embed(
            title=f"💘 {ship_name}",
            description=f"Compatibilidade: **{percent}%**\n{hearts}",
            color=0xFF0000 if percent < 30 else 0xFFFF00 if percent < 70 else 0x00FF00,
        )
        await ctx.send(embed=embed)

    @commands.command(name="roast")
    @commands.cooldown(1, 12, user_cooldown_key)
    async def roast(self, ctx, member: Optional[nextcord.Member] = None):
        """Queima alguém (ou você mesmo) com uma piada ácida."""
        target = member or ctx.author
        roasts = [
            "Você é tão lento que o Discord te marca como 'digitando' há 3 anos.",
            "Seu cabelo parece que perdeu uma briga com um liquidificador.",
            "Seu QI é menor que o número de mensagens que você já apagou.",
        ]
        await ctx.send(f"{target.mention}, {random.choice(roasts)}")

    @commands.command(name="mock")
    @commands.cooldown(1, 5, user_cooldown_key)
    async def mock(self, ctx, *, text: str):
        """Transforma o texto em zoeira alternando maiúsculas/minúsculas."""
        mocked = "".join(c.upper() if i % 2 else c.lower() for i, c in enumerate(text))
        await ctx.send(mocked)

    @commands.command(name="dadjoke")
    @commands.cooldown(1, 8, user_cooldown_key)
    async def dadjoke(self, ctx):
        """Conta uma piada de tiozão."""
        jokes = [
            "Por que o livro de matemática estava triste? Porque tinha muitos problemas.",
            "Qual é o peixe mais esperto? O atum (a-tum).",
            "O que o pato disse para a pata? Vem quá!",
        ]
        await ctx.send(f"😂 {random.choice(jokes)}")

    # Exemplo de comando extra (avatar)
    @commands.command(name="avatar")
    @commands.cooldown(1, 5, user_cooldown_key)
    async def avatar(self, ctx, member: Optional[nextcord.Member] = None):
        """Mostra o avatar de um membro."""
        target = member or ctx.author
        embed = nextcord.Embed(
            title=f"Avatar de {target.display_name}",
            color=target.color,
        )
        embed.set_image(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    # ==================== TRATAMENTO DE ERROS GLOBAL ====================

    async def cog_command_error(self, ctx, error):
        """Captura erros específicos e responde de forma amigável."""
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(
                f"⏳ Calma aí, {ctx.author.mention}! Espera **{error.retry_after:.1f}s**.",
                delete_after=5,
            )
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(
                f"❌ Argumento faltando. Use `!help {ctx.command.name}` para ver como usar.",
                delete_after=10,
            )
        elif isinstance(error, commands.BadArgument):
            # Captura erros de conversão (ex: membro inválido)
            await ctx.send(
                "❌ Argumento inválido. Verifique se o membro existe e foi mencionado corretamente.",
                delete_after=10,
            )
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(
                f"❌ Membro `{error.argument}` não encontrado.",
                delete_after=10,
            )
        elif isinstance(error, nextcord.Forbidden):
            await ctx.send(
                "❌ Não tenho permissão para enviar mensagens neste canal.",
                delete_after=10,
            )
        else:
            # Erro inesperado: loga e relança para o handler global
            logger.error(f"Erro inesperado no cog Fun (comando {ctx.command}): {error}")
            raise error  # Permite que o bot trace o erro e possivelmente notifique o dev


def setup(bot):
    bot.add_cog(Fun(bot))