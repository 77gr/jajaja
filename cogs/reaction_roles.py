"""
cogs/reaction_roles.py
-----------------------
Roles por reacción: ,reactionrole add vincula un emoji de un mensaje con
un rol. Cuando alguien reacciona con ese emoji, recibe el rol; si quita la
reacción, se lo quita.

FASE 2: se agregan ,reactionrole remove y ,reactionrole list, y una
comprobación de jerarquía/permisos antes de crear el vínculo (para que no
se guarde una configuración que el bot nunca podrá aplicar).

Uso:
    ,reactionrole add <message_id> <emoji> <@rol>
    ,reactionrole remove <message_id> <emoji>
    ,reactionrole list
"""

import discord
from discord.ext import commands

from database import db
from utils.embeds import base_embed, error_embed, success_embed


class ReactionRoles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _check_hierarchy(self, guild: discord.Guild, rol: discord.Role) -> str | None:
        """Devuelve un mensaje de error si el bot no podrá asignar ese rol, o None si todo bien."""
        me = guild.me
        if not me.guild_permissions.manage_roles:
            return "No tengo el permiso `Gestionar roles` en este servidor."
        if rol.is_default():
            return "No puedo usar `@everyone` como rol de reacción."
        if rol.managed:
            return f"{rol.mention} es un rol gestionado por una integración/bot y no se puede asignar manualmente."
        if rol >= me.top_role:
            return (
                f"Mi rol más alto está por debajo de {rol.mention}. "
                "Sube mi rol en `Configuración del servidor > Roles` para poder asignarlo."
            )
        return None

    @commands.group(name="reactionrole", aliases=["rr"], invoke_without_command=True, help="Gestiona roles por reacción")
    async def reactionrole(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @reactionrole.command(name="add", help="Vincula un emoji de un mensaje con un rol. Uso: ,reactionrole add <message_id> <emoji> <@rol>")
    @commands.has_permissions(manage_roles=True)
    async def reaction_role_add(
        self, ctx: commands.Context, message_id: str, emoji: str, rol: discord.Role
    ):
        problema = self._check_hierarchy(ctx.guild, rol)
        if problema:
            await ctx.send(embed=error_embed(problema))
            return

        try:
            message = await ctx.channel.fetch_message(int(message_id))
        except (ValueError, discord.NotFound):
            await ctx.send(embed=error_embed("No encontré ese mensaje en este canal."))
            return

        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            await ctx.send(embed=error_embed("Ese emoji no es válido o no puedo usarlo (¿es de otro servidor?)."))
            return

        await db.add_reaction_role(ctx.guild.id, message.id, emoji, rol.id)
        await ctx.send(embed=success_embed(f"Listo: reaccionar con {emoji} dará el rol {rol.mention}."))

    @reactionrole.command(name="remove", help="Quita un vínculo de rol por reacción. Uso: ,reactionrole remove <message_id> <emoji>")
    @commands.has_permissions(manage_roles=True)
    async def reaction_role_remove(self, ctx: commands.Context, message_id: str, emoji: str):
        try:
            msg_id = int(message_id)
        except ValueError:
            await ctx.send(embed=error_embed("ID inválido."))
            return

        ok = await db.remove_reaction_role(msg_id, emoji)
        if not ok:
            await ctx.send(embed=error_embed("No encontré ese vínculo de rol por reacción."))
            return

        await ctx.send(embed=success_embed(f"Se quitó el vínculo de {emoji} en ese mensaje."))

    @reactionrole.command(name="list", help="Lista los roles por reacción configurados")
    async def reaction_role_list(self, ctx: commands.Context):
        rows = await db.get_reaction_roles(ctx.guild.id)
        if not rows:
            await ctx.send(embed=error_embed("No hay roles por reacción configurados en este servidor."))
            return

        lines = []
        for row in rows:
            lines.append(f"Mensaje `{row['message_id']}` — {row['emoji']} → <@&{row['role_id']}>")

        embed = base_embed(title="🎭 Roles por reacción", description="\n".join(lines))
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.member is None or payload.member.bot:
            return
        row = await db.get_reaction_role(payload.message_id, str(payload.emoji))
        if row is None:
            return
        role = payload.member.guild.get_role(row["role_id"])
        if role:
            try:
                await payload.member.add_roles(role, reason="Reaction role")
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        row = await db.get_reaction_role(payload.message_id, str(payload.emoji))
        if row is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        member = guild.get_member(payload.user_id)
        role = guild.get_role(row["role_id"])
        if member and role:
            try:
                await member.remove_roles(role, reason="Reaction role removido")
            except discord.HTTPException:
                pass

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=error_embed("Necesitas permiso de `Gestionar roles` para usar esto."))
            return


async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionRoles(bot))
