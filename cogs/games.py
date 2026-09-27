"""
cogs/games.py
--------------
Minijuegos económicos rápidos: ,work, ,rob, ,slots y ,coinflip.
Todos usan el mismo saldo de la economía.
"""

import random
import time

import discord
from discord.ext import commands

from config import config
from database import db
from utils.embeds import base_embed, error_embed, success_embed, money

WORK_JOBS = [
    "repartiste pizzas por toda la ciudad",
    "programaste un bot de Discord",
    "paseaste perros en el parque",
    "vendiste limonada en la esquina",
    "ayudaste a mudar muebles",
    "hiciste un stream random",
    "reparaste una computadora",
]

SLOT_EMOJIS = ["🍒", "🍋", "🍇", "🔔", "💎", "7️⃣"]
SLOT_PAYOUTS = {"7️⃣": 10, "💎": 6, "🔔": 4, "🍇": 3, "🍋": 2, "🍒": 2}


def cooldown_remaining(last_used: int, cooldown: int) -> int:
    return max(0, cooldown - (int(time.time()) - last_used))


def fmt_seconds(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


class Games(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="work", help="Trabaja para ganar monedas")
    async def work(self, ctx: commands.Context):
        last = await db.get_cooldown(ctx.guild.id, ctx.author.id, "work")
        remaining = cooldown_remaining(last, config.WORK_COOLDOWN)
        if remaining > 0:
            await ctx.send(embed=error_embed(f"Ya trabajaste. Vuelve en **{fmt_seconds(remaining)}**."))
            return

        earnings = random.randint(config.WORK_MIN, config.WORK_MAX)
        job = random.choice(WORK_JOBS)
        await db.set_cooldown(ctx.guild.id, ctx.author.id, "work", int(time.time()))
        new_balance = await db.update_balance(ctx.author.id, ctx.guild.id, earnings)

        await ctx.send(
            embed=success_embed(
                f"Hoy {job} y ganaste **{money(earnings)}**.\nSaldo actual: **{money(new_balance)}**",
                title="💼 ¡A trabajar!",
            )
        )

    @commands.command(name="rob", help="Intenta robarle monedas a otro usuario (arriesgado)")
    async def rob(self, ctx: commands.Context, usuario: discord.Member):
        if usuario.id == ctx.author.id or usuario.bot:
            await ctx.send(embed=error_embed("Ese objetivo no es válido."))
            return

        last = await db.get_cooldown(ctx.guild.id, ctx.author.id, "rob")
        remaining = cooldown_remaining(last, config.ROB_COOLDOWN)
        if remaining > 0:
            await ctx.send(embed=error_embed(f"Estás escondiéndote de la policía. Espera **{fmt_seconds(remaining)}**."))
            return

        victim_row = await db.get_user(usuario.id, ctx.guild.id)
        if victim_row["balance"] < 100:
            await ctx.send(embed=error_embed(f"{usuario.display_name} no tiene suficiente dinero para valer la pena robarle."))
            return

        await db.set_cooldown(ctx.guild.id, ctx.author.id, "rob", int(time.time()))
        success = random.random() < config.ROB_SUCCESS_RATE

        if success:
            stolen = random.randint(int(victim_row["balance"] * 0.05), int(victim_row["balance"] * 0.25) or 1)
            stolen = max(stolen, 1)
            await db.update_balance(usuario.id, ctx.guild.id, -stolen)
            new_balance = await db.update_balance(ctx.author.id, ctx.guild.id, stolen)
            await ctx.send(
                embed=success_embed(
                    f"Le robaste **{money(stolen)}** a {usuario.mention}.\nSaldo actual: **{money(new_balance)}**",
                    title="🕵️ ¡Robo exitoso!",
                )
            )
        else:
            robber_row = await db.get_user(ctx.author.id, ctx.guild.id)
            fine = min(robber_row["balance"], random.randint(50, 250))
            new_balance = await db.update_balance(ctx.author.id, ctx.guild.id, -fine)
            await ctx.send(
                embed=error_embed(
                    f"Te atraparon intentando robarle a {usuario.mention} y pagaste una multa de "
                    f"**{money(fine)}**.\nSaldo actual: **{money(new_balance)}**",
                    title="🚨 ¡Te atraparon!",
                )
            )

    @commands.command(name="slots", help="Juega a la tragamonedas. Uso: ,slots <apuesta>")
    async def slots(self, ctx: commands.Context, apuesta: commands.Range[int, 1]):
        row = await db.get_user(ctx.author.id, ctx.guild.id)
        if row["balance"] < apuesta:
            await ctx.send(embed=error_embed("No tienes suficiente saldo para esa apuesta."))
            return

        result = [random.choice(SLOT_EMOJIS) for _ in range(3)]
        display = " | ".join(result)

        if result[0] == result[1] == result[2]:
            multiplier = SLOT_PAYOUTS[result[0]]
            winnings = apuesta * multiplier
            delta = winnings - apuesta
            title = f"🎰 ¡JACKPOT! x{multiplier}"
            color = config.COLOR_SUCCESS
        elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
            winnings = int(apuesta * 1.5)
            delta = winnings - apuesta
            title = "🎰 ¡Par! Ganancia pequeña"
            color = config.COLOR_SUCCESS
        else:
            delta = -apuesta
            title = "🎰 Sin suerte esta vez"
            color = config.COLOR_DANGER

        new_balance = await db.update_balance(ctx.author.id, ctx.guild.id, delta)
        embed = base_embed(title=title, color=color)
        embed.description = f"**[ {display} ]**"
        embed.add_field(name="Resultado", value=money(delta) if delta >= 0 else f"-{money(abs(delta))}")
        embed.add_field(name="Saldo", value=money(new_balance))
        await ctx.send(embed=embed)

    @commands.command(name="coinflip", help="Apuesta cara o cruz. Uso: ,coinflip <apuesta> <cara|cruz>")
    async def coinflip(self, ctx: commands.Context, apuesta: commands.Range[int, 1], lado: str):
        lado = lado.lower()
        if lado not in ("cara", "cruz"):
            await ctx.send(embed=error_embed("Elige `cara` o `cruz`. Ej: `,coinflip 100 cara`"))
            return

        row = await db.get_user(ctx.author.id, ctx.guild.id)
        if row["balance"] < apuesta:
            await ctx.send(embed=error_embed("No tienes suficiente saldo para esa apuesta."))
            return

        result = random.choice(["cara", "cruz"])
        won = result == lado
        delta = apuesta if won else -apuesta
        new_balance = await db.update_balance(ctx.author.id, ctx.guild.id, delta)

        emoji = "🪙"
        title = "✅ ¡Ganaste!" if won else "❌ Perdiste"
        color = config.COLOR_SUCCESS if won else config.COLOR_DANGER
        embed = base_embed(title=f"{emoji} {title}", color=color)
        embed.description = f"Salió **{result}**. Apostaste a **{lado}**."
        embed.add_field(name="Resultado", value=money(delta) if delta >= 0 else f"-{money(abs(delta))}")
        embed.add_field(name="Saldo", value=money(new_balance))
        await ctx.send(embed=embed)

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"⚠️ Falta el argumento `{error.param.name}`.")
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send("⚠️ Uno de los datos que diste no es válido.")
            return


async def setup(bot: commands.Bot):
    await bot.add_cog(Games(bot))
