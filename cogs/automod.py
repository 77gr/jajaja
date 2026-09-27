"""
cogs/automod.py
----------------
Automoderación ligera: borra mensajes con demasiadas menciones (posible
raid/spam), detecta invitaciones de otros servidores de Discord y bloquea
palabras de una lista negra configurable por servidor.

Uso:
    ,automod setup            -> activa automod con la configuración por defecto
    ,automod enable            -> activa automod
    ,automod disable           -> desactiva automod
    ,automod config            -> muestra la configuración actual
    ,automod config <max_menciones>  -> cambia el límite de menciones
    ,automod whitelist add <dominio>
    ,automod whitelist remove <dominio>
    ,automod whitelist list
    ,automod blacklist add <palabra>
    ,automod blacklist remove <palabra>
    ,automod blacklist list
"""

import re

import discord
from discord.ext import commands

from database import db
from utils.checks import is_staff
from utils.embeds import base_embed, error_embed, success_embed

INVITE_REGEX = re.compile(r"(discord\.gg|discord(?:app)?\.com/invite)/([\w-]+)", re.IGNORECASE)
DEFAULT_MAX_MENTIONS = 6


class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        if isinstance(message.author, discord.Member) and is_staff(message.author):
            return

        cfg = await db.get_automod_config(message.guild.id)
        if not cfg["enabled"]:
            return

        # Demasiadas menciones en un solo mensaje -> probable spam/raid.
        max_mentions = cfg["max_mentions"] or DEFAULT_MAX_MENTIONS
        if len(message.mentions) > max_mentions:
            try:
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention}, ese mensaje mencionaba a demasiadas personas y fue eliminado.",
                    delete_after=6,
                )
            except discord.HTTPException:
                pass
            return

        # Invitaciones a otros servidores (respetando la whitelist de dominios).
        if cfg["block_invites"]:
            match = INVITE_REGEX.search(message.content)
            if match:
                whitelist = await db.get_automod_whitelist(message.guild.id)
                if not any(domain in message.content.lower() for domain in whitelist):
                    try:
                        await message.delete()
                        await message.channel.send(
                            f"{message.author.mention}, no se permiten invitaciones a otros servidores aquí.",
                            delete_after=6,
                        )
                    except discord.HTTPException:
                        pass
                    return

        # Palabras de la lista negra.
        blacklist = await db.get_automod_blacklist(message.guild.id)
        if blacklist:
            content_lower = message.content.lower()
            words = set(re.findall(r"[\wáéíóúñ]+", content_lower))
            if blacklist & words:
                try:
                    await message.delete()
                    await message.channel.send(
                        f"{message.author.mention}, ese mensaje contenía una palabra no permitida y fue eliminado.",
                        delete_after=6,
                    )
                except discord.HTTPException:
                    pass

    @commands.group(
        name="automod",
        invoke_without_command=True,
        help="Gestiona la automoderación del servidor: setup/enable/disable/config/whitelist/blacklist",
    )
    async def automod(self, ctx: commands.Context):
        await self._show_config(ctx)

    @automod.command(name="setup", help="[Admin] Activa automod con la configuración por defecto")
    @commands.has_permissions(manage_guild=True)
    async def automod_setup(self, ctx: commands.Context):
        await db.set_automod_field(ctx.guild.id, "enabled", 1)
        await db.set_automod_field(ctx.guild.id, "block_invites", 1)
        await db.set_automod_field(ctx.guild.id, "max_mentions", DEFAULT_MAX_MENTIONS)
        await ctx.send(embed=success_embed("Automod configurado y activado con los valores por defecto."))
        await self._show_config(ctx)

    @automod.command(name="enable", help="[Admin] Activa la automoderación")
    @commands.has_permissions(manage_guild=True)
    async def automod_enable(self, ctx: commands.Context):
        await db.set_automod_field(ctx.guild.id, "enabled", 1)
        await ctx.send(embed=success_embed("Automod **activado**."))

    @automod.command(name="disable", help="[Admin] Desactiva la automoderación")
    @commands.has_permissions(manage_guild=True)
    async def automod_disable(self, ctx: commands.Context):
        await db.set_automod_field(ctx.guild.id, "enabled", 0)
        await ctx.send(embed=success_embed("Automod **desactivado**."))

    @automod.command(
        name="config",
        help="[Admin] Muestra o cambia la configuración. Uso: ,automod config [max_menciones] [invites:on|off]",
    )
    @commands.has_permissions(manage_guild=True)
    async def automod_config(
        self, ctx: commands.Context, max_menciones: int | None = None, invites: str | None = None
    ):
        if max_menciones is not None:
            if max_menciones < 1:
                await ctx.send(embed=error_embed("El límite de menciones debe ser al menos 1."))
                return
            await db.set_automod_field(ctx.guild.id, "max_mentions", max_menciones)
        if invites is not None:
            invites = invites.lower()
            if invites not in ("on", "off"):
                await ctx.send(embed=error_embed("El parámetro `invites` debe ser `on` u `off`."))
                return
            await db.set_automod_field(ctx.guild.id, "block_invites", 1 if invites == "on" else 0)
        await self._show_config(ctx)

    @automod.group(name="whitelist", invoke_without_command=True, help="Gestiona los dominios permitidos de invitación")
    async def whitelist(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @whitelist.command(name="add", help="[Admin] Agrega un dominio a la whitelist. Uso: ,automod whitelist add youtube.com")
    @commands.has_permissions(manage_guild=True)
    async def whitelist_add(self, ctx: commands.Context, dominio: str):
        await db.add_automod_whitelist(ctx.guild.id, dominio)
        await ctx.send(embed=success_embed(f"`{dominio.lower()}` agregado a la whitelist."))

    @whitelist.command(name="remove", help="[Admin] Quita un dominio de la whitelist")
    @commands.has_permissions(manage_guild=True)
    async def whitelist_remove(self, ctx: commands.Context, dominio: str):
        ok = await db.remove_automod_whitelist(ctx.guild.id, dominio)
        if ok:
            await ctx.send(embed=success_embed(f"`{dominio.lower()}` eliminado de la whitelist."))
        else:
            await ctx.send(embed=error_embed("Ese dominio no estaba en la whitelist."))

    @whitelist.command(name="list", help="Muestra los dominios en la whitelist")
    async def whitelist_list(self, ctx: commands.Context):
        domains = await db.get_automod_whitelist(ctx.guild.id)
        if not domains:
            await ctx.send(embed=error_embed("No hay dominios en la whitelist."))
            return
        embed = base_embed(title="✅ Whitelist de dominios", description="\n".join(f"`{d}`" for d in sorted(domains)))
        await ctx.send(embed=embed)

    @automod.group(name="blacklist", invoke_without_command=True, help="Gestiona las palabras prohibidas")
    async def blacklist(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @blacklist.command(name="add", help="[Admin] Agrega una palabra a la blacklist. Uso: ,automod blacklist add ejemplo")
    @commands.has_permissions(manage_guild=True)
    async def blacklist_add(self, ctx: commands.Context, palabra: str):
        await db.add_automod_blacklist(ctx.guild.id, palabra)
        await ctx.send(embed=success_embed(f"`{palabra.lower()}` agregada a la blacklist."))

    @blacklist.command(name="remove", help="[Admin] Quita una palabra de la blacklist")
    @commands.has_permissions(manage_guild=True)
    async def blacklist_remove(self, ctx: commands.Context, palabra: str):
        ok = await db.remove_automod_blacklist(ctx.guild.id, palabra)
        if ok:
            await ctx.send(embed=success_embed(f"`{palabra.lower()}` eliminada de la blacklist."))
        else:
            await ctx.send(embed=error_embed("Esa palabra no estaba en la blacklist."))

    @blacklist.command(name="list", help="Muestra las palabras en la blacklist")
    async def blacklist_list(self, ctx: commands.Context):
        words = await db.get_automod_blacklist(ctx.guild.id)
        if not words:
            await ctx.send(embed=error_embed("No hay palabras en la blacklist."))
            return
        embed = base_embed(title="🚫 Blacklist de palabras", description="\n".join(f"`{w}`" for w in sorted(words)))
        await ctx.send(embed=embed)

    async def _show_config(self, ctx: commands.Context):
        cfg = await db.get_automod_config(ctx.guild.id)
        embed = base_embed(title="🛡️ Configuración de automod")
        embed.add_field(name="Activo", value="✅" if cfg["enabled"] else "❌")
        embed.add_field(name="Bloquear invitaciones", value="✅" if cfg["block_invites"] else "❌")
        embed.add_field(name="Máx. menciones", value=str(cfg["max_mentions"]))
        await ctx.send(embed=embed)

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=error_embed("Necesitas permiso de `Administrar servidor` para usar esto."))
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=error_embed(f"Falta el argumento `{error.param.name}`."))
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send(embed=error_embed("Uno de los datos que diste no es válido."))
            return


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
