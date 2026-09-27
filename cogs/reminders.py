"""
cogs/reminders.py
-------------------
FASE 2: recordatorios personales.

,remind           -> crea un recordatorio ("dentro de 10m", "en 2h", etc.)
,reminders         -> lista tus recordatorios pendientes en este servidor
,reminder-delete   -> borra uno de tus recordatorios

Los recordatorios se guardan en la base de datos (tabla `reminders`), así
que si el bot se reinicia no se pierden: una tarea de fondo revisa cada
30 segundos si hay alguno vencido y lo envía en ese momento (si el bot
estuvo apagado más tiempo del debido, lo envía apenas vuelve a conectarse).
"""

import time
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from database import db
from utils.embeds import base_embed, error_embed, success_embed
from utils.checks import is_staff


def parse_duration(text: str) -> int | None:
    """Convierte '10m', '2h', '1d' (o combinaciones simples) a segundos."""
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    text = text.strip().lower()
    if len(text) < 2 or text[-1] not in units:
        return None
    try:
        amount = int(text[:-1])
    except ValueError:
        return None
    if amount <= 0:
        return None
    return amount * units[text[-1]]


class Reminders(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.checker.start()

    def cog_unload(self):
        self.checker.cancel()

    @commands.command(name="remind", help="Crea un recordatorio. Uso: ,remind <tiempo, ej. 10m/2h/1d> <mensaje>")
    async def remind(self, ctx: commands.Context, tiempo: str, *, mensaje: str):
        seconds = parse_duration(tiempo)
        if seconds is None:
            await ctx.send(embed=error_embed("Tiempo inválido. Usa algo como `10m`, `2h` o `1d`."))
            return
        if len(mensaje) > 500:
            await ctx.send(embed=error_embed("El mensaje es demasiado largo."))
            return

        remind_at = int(time.time()) + seconds
        reminder_id = await db.add_reminder(
            ctx.guild.id, ctx.channel.id, ctx.author.id, mensaje, remind_at
        )

        when = discord.utils.format_dt(datetime.fromtimestamp(remind_at, tz=timezone.utc), style="R")
        await ctx.send(embed=success_embed(f"Listo, te recordaré esto {when}: **{mensaje}**\n`ID: {reminder_id}`"))

    @commands.command(name="reminders", help="Muestra tus recordatorios pendientes en este servidor")
    async def reminders_list(self, ctx: commands.Context):
        rows = await db.get_user_reminders(ctx.guild.id, ctx.author.id)
        if not rows:
            await ctx.send(embed=error_embed("No tienes recordatorios pendientes aquí."))
            return

        lines = []
        for row in rows:
            when = discord.utils.format_dt(datetime.fromtimestamp(row["remind_at"], tz=timezone.utc), style="R")
            lines.append(f"`#{row['id']}` {when} — {row['message']}")

        embed = base_embed(title="🔔 Tus recordatorios", description="\n".join(lines))
        await ctx.send(embed=embed)

    @commands.command(name="reminder-delete", help="Borra uno de tus recordatorios. Uso: ,reminder-delete <id>")
    async def reminder_delete(self, ctx: commands.Context, id: int):
        row = await db.get_reminder(id)
        if row is None or row["guild_id"] != ctx.guild.id:
            await ctx.send(embed=error_embed("No encontré ese recordatorio en este servidor."))
            return

        is_owner = row["user_id"] == ctx.author.id
        if not is_owner and not is_staff(ctx.author):
            await ctx.send(embed=error_embed("Solo puedes borrar tus propios recordatorios."))
            return

        await db.delete_reminder(id)
        await ctx.send(embed=success_embed("Recordatorio eliminado."))

    @tasks.loop(seconds=30)
    async def checker(self):
        try:
            rows = await db.get_due_reminders(int(time.time()))
        except Exception:
            return
        for row in rows:
            await self._send(row)
            await db.delete_reminder(row["id"])

    @checker.before_loop
    async def before_checker(self):
        await self.bot.wait_until_ready()

    async def _send(self, row):
        text = f"⏰ <@{row['user_id']}>, me pediste que te recordara esto: **{row['message']}**"
        channel = self.bot.get_channel(row["channel_id"])
        if channel is not None:
            try:
                await channel.send(text)
                return
            except discord.HTTPException:
                pass
        # Si el canal ya no existe o no pudo enviarse ahí, intenta por DM como respaldo.
        user = self.bot.get_user(row["user_id"])
        if user is not None:
            try:
                await user.send(text)
            except discord.HTTPException:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Reminders(bot))
