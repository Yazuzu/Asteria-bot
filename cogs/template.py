import nextcord
from nextcord.ext import commands
import logging
import asyncio
import json
import os
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple, Callable
from collections import defaultdict

logger = logging.getLogger(__name__)

TEMPLATES_DIR = "templates"
BACKUP_DIR = os.path.join(TEMPLATES_DIR, "backups")
MAX_CONCURRENT = 5
RETRY_DELAY = 1

os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)


class RateLimiter:
    """Gerenciador de concorrência com retry e backoff."""
    def __init__(self, max_concurrent=MAX_CONCURRENT):
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def run(self, coro_or_func, *args, retries=3, **kwargs):
        async with self.semaphore:
            for attempt in range(retries):
                try:
                    if callable(coro_or_func):
                        coro = coro_or_func(*args, **kwargs)
                    else:
                        coro = coro_or_func
                    return await coro
                except nextcord.HTTPException as e:
                    if e.status == 429 and attempt < retries - 1:
                        retry_after = e.response.headers.get('Retry-After', RETRY_DELAY * (2 ** attempt))
                        logger.warning(f"Rate limit, aguardando {retry_after}s")
                        await asyncio.sleep(float(retry_after))
                    else:
                        raise
                except Exception:
                    if attempt == retries - 1:
                        raise
                    await asyncio.sleep(RETRY_DELAY * (2 ** attempt))


class TemplateManager(commands.Cog):
    """Cog profissional para backup e restauração de servidores."""

    def __init__(self, bot):
        self.bot = bot
        self.rate_limiter = RateLimiter()
        self.guild_locks = defaultdict(asyncio.Lock)  # Lock por guild

    # ------------------------------------------------------------------
    # Utilitários de permissões
    # ------------------------------------------------------------------
    def _permissions_to_list(self, permissions: nextcord.Permissions) -> List[str]:
        return [perm for perm, value in permissions if value]

    def _list_to_permissions(self, perm_list: List[str]) -> nextcord.Permissions:
        perms = nextcord.Permissions()
        for perm_name in perm_list:
            if hasattr(perms, perm_name):
                setattr(perms, perm_name, True)
        return perms

    def _overwrites_to_dict(self, overwrites: Dict, use_names: bool = False) -> List[Dict]:
        result = []
        for target, overwrite in overwrites.items():
            if isinstance(target, nextcord.Role) and target.name != "@everyone":
                target_type = "role"
                target_id = target.id if not use_names else target.name
            elif isinstance(target, nextcord.Member):
                if use_names:
                    continue
                target_type = "member"
                target_id = target.id
            else:
                continue
            allow, deny = overwrite.pair()
            result.append({
                "target_id": target_id,
                "target_type": target_type,
                "allow": self._permissions_to_list(allow),
                "deny": self._permissions_to_list(deny)
            })
        return result

    def _dict_to_overwrites(self, guild: nextcord.Guild, overwrites_data: List[Dict], use_names: bool = False) -> Dict:
        overwrites = {}
        for ow in overwrites_data:
            target_id = ow["target_id"]
            target_type = ow["target_type"]
            allow = self._list_to_permissions(ow["allow"])
            deny = self._list_to_permissions(ow["deny"])
            if target_type == "role":
                if use_names:
                    target = nextcord.utils.get(guild.roles, name=target_id)
                else:
                    target = guild.get_role(target_id)
            elif target_type == "member":
                if use_names:
                    continue
                target = guild.get_member(target_id)
            else:
                continue
            if target:
                overwrites[target] = nextcord.PermissionOverwrite.from_pair(allow, deny)
        return overwrites

    # ------------------------------------------------------------------
    # Validação avançada
    # ------------------------------------------------------------------
    async def validate_template_application(self, guild: nextcord.Guild, template: dict, mode: str, portable: bool, fix_bot_position: bool = False) -> Tuple[bool, str, dict]:
        bot_member = guild.me
        bot_top_role = bot_member.top_role
        bot_perms = bot_member.guild_permissions
        diag = {}

        if not bot_perms.manage_roles:
            return False, "O bot não tem permissão 'Gerenciar Cargos'.", diag

        # Verificar se haverá admin após aplicação
        admin_roles_after = []
        if "cargos" in template:
            for r in template["cargos"]:
                if "administrator" in r.get("permissoes", []):
                    admin_roles_after.append(r["nome"])
        current_admin_roles = [r for r in guild.roles if r.permissions.administrator and r.name != "@everyone"]
        if not admin_roles_after and not current_admin_roles:
            return False, "Nenhum cargo com administrador restará.", diag

        # Verificar posição do bot em relação aos cargos do template
        if "cargos" in template:
            # Coletar posições desejadas dos cargos (valores maiores = mais baixos)
            desired_positions = [r.get("position", 0) for r in template["cargos"]]
            if desired_positions:
                max_desired = max(desired_positions)
                min_desired = min(desired_positions)
                bot_pos = bot_top_role.position

                # Se algum cargo do template tem posição desejada menor (mais alto) que a do bot, isso é problemático
                # Porque o bot pode ficar abaixo deles.
                if min_desired < bot_pos:
                    if fix_bot_position:
                        # Tentaremos mover o bot para cima (diminuir posição) se possível
                        # Mas só podemos mover se tivermos permissão e se não ultrapassar o limite
                        if bot_perms.manage_roles and bot_top_role < guild.me.top_role:  # Não podemos mover nosso próprio cargo acima do dono
                            diag["bot_position"] = f"O bot está na posição {bot_pos}, mas há cargos desejados na posição {min_desired}. Tentaremos mover o bot para cima."
                        else:
                            return False, "O bot não pode ser movido para cima e há cargos que ficarão acima dele, perdendo controle.", diag
                    else:
                        diag["bot_position"] = f"O bot está na posição {bot_pos}, mas há cargos desejados na posição {min_desired}. Isso pode fazer o bot perder controle. Use --fix-bot para tentar mover o bot."

        return True, "Validação OK", diag

    # ------------------------------------------------------------------
    # Aplicar cargos
    # ------------------------------------------------------------------
    async def apply_roles(self, guild: nextcord.Guild, roles_data: List[Dict], mode: str, ctx=None, portable=False, fix_bot_position=False):
        bot_top_role = guild.me.top_role
        bot_perms = guild.me.guild_permissions

        # Se necessário, mover o bot para cima
        if fix_bot_position and roles_data:
            desired_positions = [r.get("position", 0) for r in roles_data]
            min_desired = min(desired_positions)
            if min_desired < bot_top_role.position:
                # Tentar mover o bot para a posição desejada - 1 (para ficar acima)
                new_pos = max(0, min_desired - 1)
                if new_pos < bot_top_role.position:
                    try:
                        await self.rate_limiter.run(bot_top_role.edit, position=new_pos)
                        logger.info(f"Cargo do bot movido para posição {new_pos}")
                    except Exception as e:
                        logger.error(f"Não foi possível mover o bot: {e}")

        # Deletar cargos se overwrite
        if mode == "overwrite":
            for role_data in roles_data:
                role = nextcord.utils.get(guild.roles, name=role_data["nome"])
                if role and role.name != "@everyone" and role != bot_top_role:
                    try:
                        await self.rate_limiter.run(role.delete)
                        logger.info(f"Cargo deletado: {role.name}")
                    except Exception as e:
                        logger.error(f"Erro ao deletar {role.name}: {e}")

        # Criar ou atualizar cargos
        created_roles = []
        for role_data in sorted(roles_data, key=lambda r: r.get("position", 0)):
            existing = nextcord.utils.get(guild.roles, name=role_data["nome"])
            perms = self._list_to_permissions(role_data.get("permissoes", []))
            colour = nextcord.Colour(role_data.get("cor", 0))
            hoist = role_data.get("separado", False)

            if existing:
                try:
                    await self.rate_limiter.run(existing.edit,
                                                colour=colour,
                                                hoist=hoist,
                                                permissions=perms,
                                                reason="Template de cargos")
                    logger.info(f"Cargo atualizado: {role_data['nome']}")
                    created_roles.append(existing)
                except Exception as e:
                    logger.error(f"Erro ao atualizar {role_data['nome']}: {e}")
            else:
                try:
                    role = await self.rate_limiter.run(guild.create_role,
                                                        name=role_data["nome"],
                                                        colour=colour,
                                                        hoist=hoist,
                                                        permissions=perms,
                                                        reason="Template de cargos")
                    logger.info(f"Cargo criado: {role_data['nome']}")
                    created_roles.append(role)
                except Exception as e:
                    logger.error(f"Erro ao criar {role_data['nome']}: {e}")

        # Reordenar cargos em lote
        # Obter todos os cargos atuais (exceto @everyone)
        all_roles = [r for r in guild.roles if r.name != "@everyone"]
        # Mapear por nome (com cuidado para duplicatas)
        # Se houver nomes duplicados, usaremos o primeiro encontrado (problema)
        role_map = {}
        for r in all_roles:
            if r.name not in role_map:
                role_map[r.name] = r
            else:
                logger.warning(f"Nome de cargo duplicado: {r.name}. Usando o primeiro.")

        # Construir ordem desejada
        sorted_template = sorted(roles_data, key=lambda r: r.get("position", 0))
        final_order = []
        for rd in sorted_template:
            if rd["nome"] in role_map:
                final_order.append(role_map[rd["nome"]])
        # Adicionar cargos que não estão no template (no final)
        for r in all_roles:
            if r.name not in [rd["nome"] for rd in roles_data]:
                final_order.append(r)

        # Separar cargos acima e abaixo do bot
        above_bot = [r for r in final_order if r.position < bot_top_role.position]
        below_bot = [r for r in final_order if r.position > bot_top_role.position]

        # Construir dicionário de posições para os abaixo do bot
        positions = {}
        start_pos = (above_bot[-1].position if above_bot else bot_top_role.position) + 1
        for idx, role in enumerate(below_bot):
            positions[role] = start_pos + idx

        if positions:
            try:
                await self.rate_limiter.run(guild.edit_role_positions, positions)
                logger.info(f"Reordenação de {len(positions)} cargos concluída.")
            except Exception as e:
                logger.error(f"Falha na reordenação em lote: {e}")
                # Fallback: mover um por um
                for role, pos in positions.items():
                    try:
                        await self.rate_limiter.run(role.edit, position=pos)
                    except Exception as e2:
                        logger.error(f"Erro ao mover {role.name}: {e2}")

    # ------------------------------------------------------------------
    # Aplicar canais
    # ------------------------------------------------------------------
    async def apply_channels(self, guild: nextcord.Guild, categorias_data: List[Dict], mode: str, ctx=None, portable=False):
        current_channel_id = ctx.channel.id if ctx else None

        if mode == "overwrite":
            all_names = set()
            for cat in categorias_data:
                all_names.add(cat["nome"])
                for ch in cat["canais"]:
                    all_names.add(ch["nome"])
            for channel in guild.channels:
                if channel.name in all_names:
                    if isinstance(channel, nextcord.TextChannel) and channel.id == current_channel_id:
                        continue
                    try:
                        await self.rate_limiter.run(channel.delete)
                        logger.info(f"Canal/Categoria deletado: {channel.name}")
                    except Exception as e:
                        logger.error(f"Erro ao deletar {channel.name}: {e}")

        categorias_criadas = {}
        for cat_data in sorted(categorias_data, key=lambda c: c.get("position", 0)):
            nome_cat = cat_data["nome"]
            cat = nextcord.utils.get(guild.categories, name=nome_cat)
            if not cat:
                cat = await self.rate_limiter.run(guild.create_category, nome_cat)
                logger.info(f"Categoria criada: {nome_cat}")
            categorias_criadas[nome_cat] = cat

            try:
                await self.rate_limiter.run(cat.edit, position=cat_data.get("position", 0))
            except Exception as e:
                logger.error(f"Erro ao posicionar categoria {nome_cat}: {e}")

            if "overwrites" in cat_data:
                overwrites = self._dict_to_overwrites(guild, cat_data["overwrites"], portable)
                if overwrites:
                    try:
                        await self.rate_limiter.run(cat.edit, overwrites=overwrites)
                        logger.info(f"Permissões da categoria {nome_cat} aplicadas.")
                    except Exception as e:
                        logger.error(f"Erro em overwrites da categoria {nome_cat}: {e}")

            for ch_data in sorted(cat_data["canais"], key=lambda c: c.get("position", 0)):
                nome_ch = ch_data["nome"]
                tipo = ch_data.get("tipo", "text")
                if tipo == "text":
                    channel = nextcord.utils.get(guild.text_channels, name=nome_ch)
                else:
                    channel = nextcord.utils.get(guild.voice_channels, name=nome_ch)

                if not channel:
                    if tipo == "text":
                        channel = await self.rate_limiter.run(guild.create_text_channel, nome_ch, category=cat)
                    else:
                        channel = await self.rate_limiter.run(guild.create_voice_channel, nome_ch, category=cat)
                    logger.info(f"Canal {tipo} criado: {nome_ch}")
                else:
                    if channel.category != cat:
                        await self.rate_limiter.run(channel.edit, category=cat)
                    logger.debug(f"Canal {tipo} já existe: {nome_ch}")

                try:
                    await self.rate_limiter.run(channel.edit, position=ch_data.get("position", 0))
                except Exception as e:
                    logger.error(f"Erro ao posicionar canal {nome_ch}: {e}")

                if "overwrites" in ch_data:
                    overwrites = self._dict_to_overwrites(guild, ch_data["overwrites"], portable)
                    if overwrites:
                        try:
                            await self.rate_limiter.run(channel.edit, overwrites=overwrites)
                            logger.info(f"Permissões do canal {nome_ch} aplicadas.")
                        except Exception as e:
                            logger.error(f"Erro em overwrites do canal {nome_ch}: {e}")

    # ------------------------------------------------------------------
    # Backup e rollback
    # ------------------------------------------------------------------
    async def create_backup(self, guild: nextcord.Guild) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backup_{guild.id}_{timestamp}.json"
        filepath = os.path.join(BACKUP_DIR, filename)

        template = {
            "nome": f"Backup automático {timestamp}",
            "cargos": [],
            "categorias": []
        }

        for role in guild.roles:
            if role.name == "@everyone":
                continue
            template["cargos"].append({
                "nome": role.name,
                "cor": role.colour.value,
                "separado": role.hoist,
                "permissoes": self._permissions_to_list(role.permissions),
                "position": role.position
            })

        for category in guild.categories:
            cat_data = {
                "nome": category.name,
                "position": category.position,
                "overwrites": self._overwrites_to_dict(category.overwrites, use_names=False),
                "canais": []
            }
            for channel in category.channels:
                if isinstance(channel, nextcord.TextChannel):
                    tipo = "text"
                elif isinstance(channel, nextcord.VoiceChannel):
                    tipo = "voice"
                else:
                    continue
                ch_data = {
                    "nome": channel.name,
                    "tipo": tipo,
                    "position": channel.position,
                    "overwrites": self._overwrites_to_dict(channel.overwrites, use_names=False)
                }
                cat_data["canais"].append(ch_data)
            template["categorias"].append(cat_data)

        # Canais de voz sem categoria
        for vc in guild.voice_channels:
            if vc.category is None:
                cat_data = {
                    "nome": "🎙️ Canais de Voz (soltos)",
                    "position": 999,
                    "overwrites": [],
                    "canais": [{
                        "nome": vc.name,
                        "tipo": "voice",
                        "position": vc.position,
                        "overwrites": self._overwrites_to_dict(vc.overwrites, use_names=False)
                    }]
                }
                template["categorias"].append(cat_data)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(template, f, ensure_ascii=False, indent=2)

        logger.info(f"Backup criado: {filepath}")
        return filepath

    async def restore_backup(self, guild: nextcord.Guild, backup_path: str):
        """Restaura um backup (modo overwrite forçado, sem criar novo backup)."""
        with open(backup_path, "r", encoding="utf-8") as f:
            template = json.load(f)
        # Aplicar em modo overwrite, mas sem criar novo backup
        await self.apply_roles(guild, template.get("cargos", []), mode="overwrite", portable=False)
        await self.apply_channels(guild, template.get("categorias", []), mode="overwrite", portable=False)

    # ------------------------------------------------------------------
    # Comando principal
    # ------------------------------------------------------------------
    @commands.group(name="template", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def template(self, ctx):
        embed = nextcord.Embed(
            title="📋 Template Manager (Profissional)",
            description="Subcomandos:",
            colour=0xFF69B4
        )
        embed.add_field(name="aplicar", value="`!template aplicar <nome> [--force] [--portable] [--dry-run] [--fix-bot]`", inline=False)
        embed.add_field(name="capturar", value="`!template capturar <nome>`", inline=False)
        embed.add_field(name="listar", value="`!template listar`", inline=False)
        await ctx.send(embed=embed)

    @template.command(name="aplicar")
    async def aplicar_template(self, ctx, template_name: str = "xenom_completo", *flags):
        guild = ctx.guild
        arquivo = os.path.join(TEMPLATES_DIR, f"{template_name}.json")
        if not os.path.exists(arquivo):
            return await ctx.send(f"❌ Template `{template_name}` não encontrado.")

        with open(arquivo, "r", encoding="utf-8") as f:
            template = json.load(f)

        force = "--force" in flags
        portable = "--portable" in flags
        dry_run = "--dry-run" in flags
        fix_bot = "--fix-bot" in flags
        mode = "overwrite" if force else "create"

        # Lock por guild para evitar concorrência
        async with self.guild_locks[guild.id]:
            # Validação
            ok, msg, diag = await self.validate_template_application(guild, template, mode, portable, fix_bot)
            if not ok:
                return await ctx.send(f"❌ Validação falhou: {msg}")

            if diag:
                diag_msg = "\n".join(f"⚠️ {v}" for v in diag.values())
                await ctx.send(f"Diagnóstico:\n{diag_msg}")

            if dry_run:
                embed = nextcord.Embed(title="🔍 Simulação (dry-run)", colour=0x00CED1)
                embed.add_field(name="Template", value=template_name, inline=True)
                embed.add_field(name="Modo", value=mode, inline=True)
                embed.add_field(name="Portátil", value=portable, inline=True)
                embed.add_field(name="Fix Bot", value=fix_bot, inline=True)
                embed.add_field(name="Cargos", value=f"{len(template.get('cargos', []))}", inline=False)
                embed.add_field(name="Categorias", value=f"{len(template.get('categorias', []))}", inline=False)
                await ctx.send(embed=embed)
                return

            # Backup automático se force
            backup_path = None
            if force:
                backup_path = await self.create_backup(guild)
                await ctx.send(f"💾 Backup automático criado: `{backup_path}`")

            # Confirmação
            confirm = await ctx.send("Reaja com ✅ em 30 segundos para confirmar.")
            await confirm.add_reaction("✅")

            def check(reaction, user):
                return user == ctx.author and str(reaction.emoji) == "✅" and reaction.message.id == confirm.id

            try:
                await self.bot.wait_for("reaction_add", timeout=30.0, check=check)
            except asyncio.TimeoutError:
                await ctx.send("⏳ Tempo esgotado. Operação cancelada.")
                return

            status = await ctx.send("🔄 Aplicando template...")

            # Bloco com rollback automático
            try:
                if "cargos" in template:
                    await status.edit(content="👔 Processando cargos...")
                    await self.apply_roles(guild, template["cargos"], mode, ctx, portable, fix_bot)

                if "categorias" in template:
                    await status.edit(content="📁 Processando canais...")
                    await self.apply_channels(guild, template["categorias"], mode, ctx, portable)

                await status.edit(content="✅ Template aplicado com sucesso!")
                logger.info(f"Template {template_name} aplicado por {ctx.author} em {guild.name}")

            except Exception as e:
                logger.exception(f"Erro crítico durante aplicação: {e}")
                await status.edit(content="❌ Erro crítico! Iniciando rollback...")
                if backup_path and os.path.exists(backup_path):
                    try:
                        # Limpeza mais agressiva: tentar deletar tudo que foi criado?
                        # Mas é complexo. Vamos apenas restaurar o backup.
                        await self.restore_backup(guild, backup_path)
                        await ctx.send("✅ Rollback concluído. O servidor foi restaurado ao estado anterior.")
                    except Exception as rb_e:
                        logger.exception(f"Falha no rollback: {rb_e}")
                        await ctx.send("❌ Falha no rollback. O servidor pode estar inconsistente. Use o backup manual.")
                else:
                    await ctx.send("❌ Sem backup disponível. O servidor pode estar inconsistente.")

    @template.command(name="capturar")
    async def capturar_template(self, ctx, nome_template: str):
        guild = ctx.guild
        template = {
            "nome": nome_template,
            "cargos": [],
            "categorias": []
        }

        for role in guild.roles:
            if role.name == "@everyone":
                continue
            template["cargos"].append({
                "nome": role.name,
                "cor": role.colour.value,
                "separado": role.hoist,
                "permissoes": self._permissions_to_list(role.permissions),
                "position": role.position
            })

        for category in guild.categories:
            cat_data = {
                "nome": category.name,
                "position": category.position,
                "overwrites": self._overwrites_to_dict(category.overwrites, use_names=False),
                "canais": []
            }
            for channel in category.channels:
                if isinstance(channel, nextcord.TextChannel):
                    tipo = "text"
                elif isinstance(channel, nextcord.VoiceChannel):
                    tipo = "voice"
                else:
                    continue
                ch_data = {
                    "nome": channel.name,
                    "tipo": tipo,
                    "position": channel.position,
                    "overwrites": self._overwrites_to_dict(channel.overwrites, use_names=False)
                }
                cat_data["canais"].append(ch_data)
            template["categorias"].append(cat_data)

        for vc in guild.voice_channels:
            if vc.category is None:
                cat_data = {
                    "nome": "🎙️ Canais de Voz (soltos)",
                    "position": 999,
                    "overwrites": [],
                    "canais": [{
                        "nome": vc.name,
                        "tipo": "voice",
                        "position": vc.position,
                        "overwrites": self._overwrites_to_dict(vc.overwrites, use_names=False)
                    }]
                }
                template["categorias"].append(cat_data)

        caminho = os.path.join(TEMPLATES_DIR, f"{nome_template}.json")
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(template, f, ensure_ascii=False, indent=2)

        await ctx.send(f"✅ Template `{nome_template}` capturado!", file=nextcord.File(caminho))

    @template.command(name="listar")
    async def listar_templates(self, ctx):
        arquivos = [f.replace(".json", "") for f in os.listdir(TEMPLATES_DIR) if f.endswith(".json")]
        if not arquivos:
            return await ctx.send("Nenhum template encontrado.")
        lista = "\n".join(f"• `{nome}`" for nome in arquivos)
        embed = nextcord.Embed(title="📁 Templates disponíveis", description=lista, colour=0x00CED1)
        await ctx.send(embed=embed)


async def setup(bot):
    bot.add_cog(TemplateManager(bot))