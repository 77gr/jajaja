"""
cogs/moderation.py
-------------------
Comandos clásicos de moderación: kick, ban, unban, timeout, warn/warnings
y un sistema simple de "jail" (aislar a alguien con un rol que le quita
acceso a los demás canales).

Todos los comandos usan el prefijo del bot (por defecto ","), ej:
    ,ban @usuario spam
    ,kick @usuario
    ,warn @usuario spam en el chat
"""

import datetime

import discord
from discord.ext import commands

from database import db
from utils.embeds import error_embed, success_embed, base_embed


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="kick", help="Expulsa a un miembro del servidor")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, usuario: discord.Member, *, razon: str = "Sin motivo"):
        await usuario.kick(reason=f"{ctx.author}: {razon}")
        await ctx.send(embed=success_embed(f"👢 {usuario.mention} fue expulsado.\n**Motivo:** {razon}"))

    @commands.command(name="ban", help="Banea a un miembro del servidor")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, usuario: discord.Member, *, razon: str = "Sin motivo"):
        await usuario.ban(reason=f"{ctx.author}: {razon}")
        await ctx.send(embed=success_embed(f"🔨 {usuario.mention} fue baneado.\n**Motivo:** {razon}"))

    @commands.command(name="unban", help="Quita el baneo a un usuario por su ID")
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, user_id: str):
        try:
            user = await self.bot.fetch_user(int(user_id))
            await ctx.guild.unban(user)
            await ctx.send(embed=success_embed(f"✅ {user} fue desbaneado."))
        except (ValueError, discord.NotFound):
            await ctx.send(embed=error_embed("No encontré a nadie baneado con ese ID."))

    @commands.command(name="timeout", help="Silencia temporalmente a un miembro. Uso: ,timeout @usuario <minutos> [razón]")
    @commands.has_permissions(moderate_members=True)
    async def timeout(
        self,
        ctx: commands.Context,
        usuario: discord.Member,
        minutos: commands.Range[int, 1, 40320],
        *,
        razon: str = "Sin motivo",
    ):
        duration = datetime.timedelta(minutes=minutos)
        await usuario.timeout(duration, reason=f"{ctx.author}: {razon}")
        await ctx.send(
            embed=success_embed(f"🔇 {usuario.mention} fue silenciado por **{minutos} min**.\n**Motivo:** {razon}")
        )

    @commands.command(name="warn", help="Registra una advertencia para un miembro")
    @commands.has_permissions(moderate_members=True)
    async def warn(self, ctx: commands.Context, usuario: discord.Member, *, razon: str):
        await db.add_warning(ctx.guild.id, usuario.id, ctx.author.id, razon)
        total = len(await db.get_warnings(ctx.guild.id, usuario.id))
        await ctx.send(embed=success_embed(f"⚠️ {usuario.mention} fue advertido (total: **{total}**).\n**Motivo:** {razon}"))

    @commands.command(name="warnings", help="Muestra las advertencias de un miembro")
    async def warnings(self, ctx: commands.Context, usuario: discord.Member):
        rows = await db.get_warnings(ctx.guild.id, usuario.id)
        if not rows:
            await ctx.send(f"{usuario.mention} no tiene advertencias.")
            return
        lines = [f"`#{i}` {r['reason']}" for i, r in enumerate(rows, start=1)]
        embed = base_embed(title=f"⚠️ Advertencias de {usuario.display_name}", description="\n".join(lines))
        await ctx.send(embed=embed)

    @commands.command(name="jail", help="Aísla a un miembro quitándole acceso al resto del servidor")
    @commands.has_permissions(moderate_members=True)
    async def jail(self, ctx: commands.Context, usuario: discord.Member, *, razon: str = "Sin motivo"):
        config_row = await db.get_guild_config(ctx.guild.id)
        role_id = config_row["jail_role_id"]
        if not role_id:
            await ctx.send(embed=error_embed(f"Primero configura el rol de jail con `{ctx.prefix}config jail-role`."))
            return
        role = ctx.guild.get_role(role_id)
        if role is None:
            await ctx.send(embed=error_embed("El rol configurado ya no existe."))
            return
        await usuario.add_roles(role, reason=f"{ctx.author}: {razon}")
        await ctx.send(embed=success_embed(f"🔒 {usuario.mention} fue enviado a jail.\n**Motivo:** {razon}"))

    @commands.command(name="unjail", help="Saca a un miembro de jail")
    @commands.has_permissions(moderate_members=True)
    async def unjail(self, ctx: commands.Context, usuario: discord.Member):
        config_row = await db.get_guild_config(ctx.guild.id)
        role_id = config_row["jail_role_id"]
        role = ctx.guild.get_role(role_id) if role_id else None
        if role and role in usuario.roles:
            await usuario.remove_roles(role, reason=f"Unjail por {ctx.author}")
        await ctx.send(embed=success_embed(f"🔓 {usuario.mention} salió de jail."))

    @commands.command(name="clear", help="Elimina varios mensajes recientes de este canal. Uso: ,clear <cantidad> [@usuario]")
    @commands.has_permissions(manage_messages=True)
    async def clear(
        self,
        ctx: commands.Context,
        cantidad: commands.Range[int, 1, 100],
        usuario: discord.Member | None = None,
    ):
        check = (lambda m: m.author.id == usuario.id) if usuario else None
        deleted = await ctx.channel.purge(limit=cantidad, check=check, before=ctx.message)
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        await ctx.send(embed=success_embed(f"🧹 Se eliminaron **{len(deleted)}** mensajes."), delete_after=5)

    @commands.command(name="slowmode", help="Configura el modo lento de este canal (0-21600 segundos)")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx: commands.Context, segundos: commands.Range[int, 0, 21600]):
        await ctx.channel.edit(slowmode_delay=segundos)
        if segundos == 0:
            await ctx.send(embed=success_embed("🐇 Modo lento desactivado en este canal."))
        else:
            await ctx.send(embed=success_embed(f"🐌 Modo lento configurado a **{segundos}s** en este canal."))

    @commands.command(name="lock", help="Bloquea este canal para que @everyone no pueda escribir")
    @commands.has_permissions(manage_channels=True)
    async def lock(
        self,
        ctx: commands.Context,
        canal: discord.TextChannel | None = None,
        *,
        razon: str = "Sin motivo",
    ):
        target = canal or ctx.channel
        everyone = ctx.guild.default_role
        overwrite = target.overwrites_for(everyone)
        overwrite.send_messages = False
        await target.set_permissions(everyone, overwrite=overwrite, reason=f"{ctx.author}: {razon}")
        await ctx.send(embed=success_embed(f"🔒 {target.mention} fue bloqueado.\n**Motivo:** {razon}"))

    @commands.command(name="unlock", help="Desbloquea este canal para que @everyone pueda volver a escribir")
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx: commands.Context, canal: discord.TextChannel | None = None):
        target = canal or ctx.channel
        everyone = ctx.guild.default_role
        overwrite = target.overwrites_for(everyone)
        overwrite.send_messages = None
        await target.set_permissions(everyone, overwrite=overwrite, reason=f"Unlock por {ctx.author}")
        await ctx.send(embed=success_embed(f"🔓 {target.mention} fue desbloqueado."))

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=error_embed("Necesitas permiso suficiente para usar esto."))
            return
        if isinstance(error, commands.MemberNotFound):
            await ctx.send(embed=error_embed("No encontré a ese usuario en el servidor."))
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=error_embed(f"Falta el argumento `{error.param.name}`."))
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send(embed=error_embed("Uno de los datos que diste no es válido."))
            return


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
