"""
cogs/logs.py
-------------
Logs básicos del servidor: manda un embed a un canal configurado cuando
pasa algo relevante (mensajes borrados/editados, miembros que entran o
salen, bans/unbans, kicks y cambios de roles).

Configúralo con ,logs setup #canal.
"""

import asyncio

import discord
from discord.ext import commands

from database import db
from utils.embeds import base_embed, success_embed, error_embed

MAX_FIELD_LEN = 1000


def _truncate(text: str | None) -> str:
    text = text or "*(vacío)*"
    if len(text) > MAX_FIELD_LEN:
        return text[:MAX_FIELD_LEN] + "…"
    return text


class Logs(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        cfg = await db.get_guild_config(guild.id)
        if not cfg["log_channel_id"]:
            return None
        channel = guild.get_channel(cfg["log_channel_id"])
        return channel if isinstance(channel, discord.TextChannel) else None

    async def _send(self, guild: discord.Guild, embed: discord.Embed):
        channel = await self._log_channel(guild)
        if channel is None:
            return
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    @commands.group(name="logs", invoke_without_command=True, help="Comandos de logs: setup")
    async def logs(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @logs.command(name="setup", aliases=["config"], help="Configura el canal donde se enviarán los logs del servidor. Uso: ,logs setup #canal")
    @commands.has_permissions(manage_guild=True)
    async def logs_setup(self, ctx: commands.Context, canal: discord.TextChannel):
        await db.set_guild_field(ctx.guild.id, "log_channel_id", canal.id)
        await ctx.send(embed=success_embed(f"Los logs del servidor se enviarán a {canal.mention}."))

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

    # ---------------- MENSAJES ----------------

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or (message.author and message.author.bot):
            return
        embed = base_embed(title="🗑️ Mensaje eliminado")
        embed.add_field(name="Autor", value=f"{message.author.mention} ({message.author})", inline=False)
        embed.add_field(name="Canal", value=message.channel.mention, inline=False)
        embed.add_field(name="Contenido", value=_truncate(message.content), inline=False)
        await self._send(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot or before.content == after.content:
            return
        embed = base_embed(title="📝 Mensaje editado")
        embed.add_field(name="Autor", value=f"{before.author.mention} ({before.author})", inline=False)
        embed.add_field(name="Canal", value=before.channel.mention, inline=False)
        embed.add_field(name="Antes", value=_truncate(before.content), inline=False)
        embed.add_field(name="Después", value=_truncate(after.content), inline=False)
        if before.jump_url:
            embed.url = before.jump_url
        await self._send(before.guild, embed)

    # ---------------- JOINS / LEAVES / KICKS ----------------

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = base_embed(title="📥 Miembro se unió")
        embed.add_field(name="Usuario", value=f"{member.mention} ({member})", inline=False)
        embed.add_field(
            name="Cuenta creada",
            value=discord.utils.format_dt(member.created_at, style="R"),
            inline=False,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await self._send(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # Intenta distinguir si fue un kick revisando el registro de auditoría.
        # Si el bot no tiene permiso de "Ver registro de auditoría", simplemente
        # se registra como una salida normal.
        kicked_by = None
        reason = None
        try:
            await asyncio.sleep(1)  # da tiempo a que la entrada del audit log se genere
            async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.kick):
                if (
                    entry.target
                    and entry.target.id == member.id
                    and (discord.utils.utcnow() - entry.created_at).total_seconds() < 15
                ):
                    kicked_by = entry.user
                    reason = entry.reason
                    break
        except (discord.Forbidden, discord.HTTPException):
            pass

        if kicked_by:
            embed = base_embed(title="👢 Miembro expulsado (kick)")
            embed.add_field(name="Usuario", value=f"{member.mention} ({member})", inline=False)
            embed.add_field(name="Moderador", value=str(kicked_by), inline=False)
            embed.add_field(name="Motivo", value=reason or "Sin motivo", inline=False)
        else:
            embed = base_embed(title="📤 Miembro se fue")
            embed.add_field(name="Usuario", value=f"{member.mention} ({member})", inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        await self._send(member.guild, embed)

    # ---------------- BANS ----------------

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        embed = base_embed(title="🔨 Usuario baneado")
        embed.add_field(name="Usuario", value=f"{user.mention} ({user})", inline=False)
        await self._send(guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        embed = base_embed(title="✅ Usuario desbaneado")
        embed.add_field(name="Usuario", value=str(user), inline=False)
        await self._send(guild, embed)

    # ---------------- CAMBIOS DE ROLES ----------------

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.roles == after.roles:
            return
        added = [r for r in after.roles if r not in before.roles]
        removed = [r for r in before.roles if r not in after.roles]
        if not added and not removed:
            return
        embed = base_embed(title="🎭 Roles actualizados")
        embed.add_field(name="Usuario", value=f"{after.mention} ({after})", inline=False)
        if added:
            embed.add_field(name="Roles añadidos", value=", ".join(r.mention for r in added), inline=False)
        if removed:
            embed.add_field(name="Roles quitados", value=", ".join(r.mention for r in removed), inline=False)
        await self._send(after.guild, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Logs(bot))
