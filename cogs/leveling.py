"""
cogs/leveling.py
-----------------
Sistema de experiencia y niveles: cada mensaje da XP (con cooldown para
evitar spam), y al subir de nivel se anuncia en el canal (o por DM, o
en silencio, según se configure). Incluye recompensas de rol por nivel,
canales ignorados para XP, y comandos de administración.
"""

import random
import time

import discord
from discord.ext import commands

from database import db
from utils.checks import is_staff
from utils.embeds import base_embed, error_embed, success_embed

XP_COOLDOWN_SECONDS = 60
XP_MIN, XP_MAX = 15, 25


def xp_for_level(level: int) -> int:
    """Curva de XP necesaria para alcanzar `level` (cuadrática, como la mayoría de bots)."""
    return 5 * (level ** 2) + 50 * level + 100


class Leveling(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        ignored = await db.get_ignored_level_channels(message.guild.id)
        if message.channel.id in ignored:
            return

        row = await db.get_user(message.author.id, message.guild.id)
        now = int(time.time())
        if now - row["last_xp"] < XP_COOLDOWN_SECONDS:
            return

        await db.conn.execute(
            "UPDATE users SET last_xp = ? WHERE user_id = ? AND guild_id = ?",
            (now, message.author.id, message.guild.id),
        )
        await db.conn.commit()

        settings = await db.get_level_settings(message.guild.id)
        gained = round(random.randint(XP_MIN, XP_MAX) * settings["xp_rate"])
        row = await db.add_xp(message.author.id, message.guild.id, gained)

        needed = xp_for_level(row["level"] + 1)
        if row["xp"] >= needed:
            new_level = row["level"] + 1
            await db.set_level(message.author.id, message.guild.id, new_level)
            await self._announce_level_up(message, new_level, settings)
            await self._apply_level_roles(message.author, message.guild, new_level, settings)

    async def _announce_level_up(self, message: discord.Message, new_level: int, settings):
        if settings["announce_mode"] == "silent":
            return
        template = settings["announce_message"] or "🎉 {user} subió a **nivel {level}**!"
        text = template.replace("{user}", message.author.mention).replace("{level}", str(new_level))

        try:
            if settings["announce_mode"] == "dm":
                await message.author.send(text)
            else:
                await message.channel.send(text)
        except discord.HTTPException:
            pass

    async def _apply_level_roles(self, member: discord.Member, guild: discord.Guild, level: int, settings):
        rewards = await db.get_level_roles(guild.id)
        earned = [r for r in rewards if r["level"] <= level]
        if not earned:
            return

        roles_to_add = []
        for reward in earned:
            role = guild.get_role(reward["role_id"])
            if role and role not in member.roles:
                roles_to_add.append(role)

        if not settings["stack_roles"] and earned:
            # Solo se queda con el rol del nivel más alto alcanzado; quita los anteriores.
            highest = earned[-1]
            highest_role = guild.get_role(highest["role_id"])
            roles_to_remove = [
                guild.get_role(r["role_id"])
                for r in rewards
                if r["level"] != highest["level"] and guild.get_role(r["role_id"]) in member.roles
            ]
            roles_to_remove = [r for r in roles_to_remove if r]
            if roles_to_remove:
                try:
                    await member.remove_roles(*roles_to_remove, reason="Level roles (no stack)")
                except discord.Forbidden:
                    pass
            roles_to_add = [highest_role] if highest_role and highest_role not in member.roles else []

        if roles_to_add:
            try:
                await member.add_roles(*roles_to_add, reason="Recompensa de nivel")
            except discord.Forbidden:
                pass

    @commands.command(name="rank", help="Muestra tu nivel y experiencia")
    async def rank(self, ctx: commands.Context, usuario: discord.Member | None = None):
        target = usuario or ctx.author
        row = await db.get_user(target.id, ctx.guild.id)
        needed = xp_for_level(row["level"] + 1)

        embed = base_embed(title=f"📊 Nivel de {target.display_name}")
        embed.add_field(name="Nivel", value=str(row["level"]))
        embed.add_field(name="XP", value=f"{row['xp']} / {needed}")
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="leveltop", help="Top de niveles del servidor")
    async def rank_top(self, ctx: commands.Context):
        await self.levels_leaderboard(ctx)

    @commands.command(name="setlevel", help="[Admin] Fija el nivel de un usuario")
    @commands.has_permissions(manage_guild=True)
    async def setlevel(self, ctx: commands.Context, usuario: discord.Member, nivel: commands.Range[int, 0]):
        await db.set_xp_and_level(usuario.id, ctx.guild.id, xp_for_level(nivel), nivel)
        await ctx.send(embed=success_embed(f"{usuario.mention} ahora está en nivel **{nivel}**."))

    @commands.command(name="setxp", help="[Admin] Fija el XP de un usuario")
    @commands.has_permissions(manage_guild=True)
    async def setxp(self, ctx: commands.Context, usuario: discord.Member, xp: commands.Range[int, 0]):
        row = await db.get_user(usuario.id, ctx.guild.id)
        await db.set_xp_and_level(usuario.id, ctx.guild.id, xp, row["level"])
        await ctx.send(embed=success_embed(f"{usuario.mention} ahora tiene **{xp} XP**."))

    # ---------------- Grupo de comandos con prefijo: ,levels ... ----------------

    @commands.group(name="levels", invoke_without_command=True)
    async def levels(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @levels.command(name="lock")
    async def levels_lock(self, ctx: commands.Context, canal: discord.TextChannel = None):
        if not is_staff(ctx.author):
            return await ctx.send(embed=error_embed("Necesitas permiso de `Administrar servidor`."))
        canal = canal or ctx.channel
        await db.ignore_level_channel(ctx.guild.id, canal.id)
        await ctx.send(embed=success_embed(f"{canal.mention} ya no dará XP."))

    @levels.command(name="unlock")
    async def levels_unlock(self, ctx: commands.Context, canal: discord.TextChannel = None):
        if not is_staff(ctx.author):
            return await ctx.send(embed=error_embed("Necesitas permiso de `Administrar servidor`."))
        canal = canal or ctx.channel
        ok = await db.unignore_level_channel(ctx.guild.id, canal.id)
        if ok:
            await ctx.send(embed=success_embed(f"{canal.mention} vuelve a dar XP."))
        else:
            await ctx.send(embed=error_embed("Ese canal no estaba bloqueado."))

    @levels.command(name="ignore")
    async def levels_ignore(self, ctx: commands.Context, canal: discord.TextChannel = None):
        await self.levels_lock(ctx, canal)

    @levels.command(name="list")
    async def levels_list(self, ctx: commands.Context):
        ignored = await db.get_ignored_level_channels(ctx.guild.id)
        if not ignored:
            return await ctx.send(embed=error_embed("No hay canales bloqueados para XP."))
        mentions = " ".join(f"<#{c}>" for c in ignored)
        await ctx.send(embed=base_embed(title="🔒 Canales sin XP", description=mentions))

    @levels.command(name="add")
    async def levels_add(self, ctx: commands.Context, nivel: int, rol: discord.Role):
        if not is_staff(ctx.author):
            return await ctx.send(embed=error_embed("Necesitas permiso de `Administrar servidor`."))
        await db.add_level_role(ctx.guild.id, nivel, rol.id)
        await ctx.send(embed=success_embed(f"Al llegar a nivel **{nivel}** se entregará {rol.mention}."))

    @levels.command(name="remove")
    async def levels_remove(self, ctx: commands.Context, nivel: int):
        if not is_staff(ctx.author):
            return await ctx.send(embed=error_embed("Necesitas permiso de `Administrar servidor`."))
        ok = await db.remove_level_role(ctx.guild.id, nivel)
        if ok:
            await ctx.send(embed=success_embed(f"Recompensa del nivel **{nivel}** eliminada."))
        else:
            await ctx.send(embed=error_embed("No había recompensa configurada para ese nivel."))

    @levels.command(name="roles")
    async def levels_roles(self, ctx: commands.Context):
        rewards = await db.get_level_roles(ctx.guild.id)
        if not rewards:
            return await ctx.send(embed=error_embed("No hay recompensas de rol configuradas."))
        lines = [f"Nivel **{r['level']}** → <@&{r['role_id']}>" for r in rewards]
        await ctx.send(embed=base_embed(title="🎭 Recompensas por nivel", description="\n".join(lines)))

    @levels.command(name="sync")
    async def levels_sync(self, ctx: commands.Context):
        if not is_staff(ctx.author):
            return await ctx.send(embed=error_embed("Necesitas permiso de `Administrar servidor`."))
        settings = await db.get_level_settings(ctx.guild.id)
        count = 0
        async with ctx.typing():
            for member in ctx.guild.members:
                if member.bot:
                    continue
                row = await db.get_user(member.id, ctx.guild.id)
                await self._apply_level_roles(member, ctx.guild, row["level"], settings)
                count += 1
        await ctx.send(embed=success_embed(f"Roles de nivel sincronizados para {count} miembros."))

    @levels.command(name="stackroles")
    async def levels_stackroles(self, ctx: commands.Context, estado: str):
        if not is_staff(ctx.author):
            return await ctx.send(embed=error_embed("Necesitas permiso de `Administrar servidor`."))
        value = estado.lower() in ("on", "true", "si", "sí", "1")
        await db.set_level_setting(ctx.guild.id, "stack_roles", int(value))
        await ctx.send(embed=success_embed(f"Acumular roles de nivel: **{'activado' if value else 'desactivado'}**."))

    @levels.command(name="setrate")
    async def levels_setrate(self, ctx: commands.Context, multiplicador: float):
        if not is_staff(ctx.author):
            return await ctx.send(embed=error_embed("Necesitas permiso de `Administrar servidor`."))
        await db.set_level_setting(ctx.guild.id, "xp_rate", multiplicador)
        await ctx.send(embed=success_embed(f"Multiplicador de XP fijado en **x{multiplicador}**."))

    @levels.command(name="messagemode")
    async def levels_messagemode(self, ctx: commands.Context, modo: str):
        if not is_staff(ctx.author):
            return await ctx.send(embed=error_embed("Necesitas permiso de `Administrar servidor`."))
        modo = modo.lower()
        if modo not in ("channel", "dm", "silent"):
            return await ctx.send(embed=error_embed("Modo inválido. Usa `channel`, `dm` o `silent`."))
        await db.set_level_setting(ctx.guild.id, "announce_mode", modo)
        await ctx.send(embed=success_embed(f"Los anuncios de nivel ahora son: **{modo}**."))

    @levels.command(name="message")
    async def levels_message(self, ctx: commands.Context, *, plantilla: str):
        if not is_staff(ctx.author):
            return await ctx.send(embed=error_embed("Necesitas permiso de `Administrar servidor`."))
        await db.set_level_setting(ctx.guild.id, "announce_message", plantilla)
        await ctx.send(
            embed=success_embed(
                f"Mensaje de nivel actualizado. Usa `{{user}}` y `{{level}}` como variables.\nEjemplo: {plantilla}"
            )
        )

    @levels.command(name="leaderboard")
    async def levels_leaderboard(self, ctx: commands.Context):
        cur = await db.conn.execute(
            "SELECT * FROM users WHERE guild_id = ? ORDER BY xp DESC LIMIT 10", (ctx.guild.id,)
        )
        rows = await cur.fetchall()
        if not rows:
            return await ctx.send(embed=error_embed("Todavía no hay datos."))
        lines = []
        for i, row in enumerate(rows, start=1):
            member = ctx.guild.get_member(row["user_id"])
            name = member.display_name if member else f"Usuario {row['user_id']}"
            lines.append(f"`#{i}` **{name}** — Nivel {row['level']} ({row['xp']} XP)")
        await ctx.send(embed=base_embed(title="🏆 Top niveles", description="\n".join(lines)))

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
    await bot.add_cog(Leveling(bot))
