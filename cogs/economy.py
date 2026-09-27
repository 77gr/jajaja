"""
cogs/economy.py
----------------
Comandos base de la economía virtual del bot: ver saldo, reclamar la
recompensa diaria, transferir monedas y ver la tabla de líderes.
Los minijuegos (Mines, Chicken) están en sus propios archivos y usan
las mismas funciones de database.py para leer/escribir el saldo.
"""

import time

import discord
from discord.ext import commands

from config import config
from database import db
from utils.embeds import base_embed, error_embed, success_embed, money


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="balance", aliases=["bal"], help="Muestra tu saldo o el de otro usuario")
    async def balance(self, ctx: commands.Context, usuario: discord.Member | None = None):
        target = usuario or ctx.author
        row = await db.get_user(target.id, ctx.guild.id)
        embed = base_embed(title=f"💰 Saldo de {target.display_name}")
        embed.add_field(name="Cartera", value=money(row["balance"]))
        embed.add_field(name="Banco", value=money(row["bank"]))
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="daily", help="Reclama tu recompensa diaria")
    async def daily(self, ctx: commands.Context):
        row = await db.get_user(ctx.author.id, ctx.guild.id)
        now = int(time.time())
        elapsed = now - row["last_daily"]
        cooldown = 24 * 60 * 60

        if elapsed < cooldown:
            remaining = cooldown - elapsed
            hours, rem = divmod(remaining, 3600)
            minutes = rem // 60
            await ctx.send(embed=error_embed(f"Ya reclamaste tu diario. Vuelve en **{hours}h {minutes}m**."))
            return

        new_balance = await db.update_balance(ctx.author.id, ctx.guild.id, config.DAILY_AMOUNT)
        await db.set_last_daily(ctx.author.id, ctx.guild.id, now)
        await ctx.send(
            embed=success_embed(
                f"Reclamaste tu recompensa diaria de **{money(config.DAILY_AMOUNT)}**.\n"
                f"Saldo actual: **{money(new_balance)}**",
                title="✅ Diario reclamado",
            )
        )

    @commands.command(name="pay", help="Transfiere monedas a otro usuario. Uso: ,pay @usuario <cantidad>")
    async def pay(self, ctx: commands.Context, usuario: discord.Member, cantidad: commands.Range[int, 1]):
        if usuario.id == ctx.author.id:
            await ctx.send(embed=error_embed("No puedes transferirte dinero a ti mismo."))
            return
        if usuario.bot:
            await ctx.send(embed=error_embed("No puedes transferirle dinero a un bot."))
            return

        sender = await db.get_user(ctx.author.id, ctx.guild.id)
        if sender["balance"] < cantidad:
            await ctx.send(embed=error_embed("No tienes suficiente saldo para esa transferencia."))
            return

        await db.update_balance(ctx.author.id, ctx.guild.id, -cantidad)
        await db.update_balance(usuario.id, ctx.guild.id, cantidad)

        await ctx.send(
            embed=success_embed(f"{ctx.author.mention} le transfirió **{money(cantidad)}** a {usuario.mention}.")
        )

    @commands.command(name="leaderboard", aliases=["baltop"], help="Top de usuarios con más monedas en el servidor")
    async def leaderboard(self, ctx: commands.Context):
        rows = await db.leaderboard(ctx.guild.id, limit=10)
        if not rows:
            await ctx.send(embed=error_embed("Todavía no hay datos."))
            return

        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, row in enumerate(rows):
            member = ctx.guild.get_member(row["user_id"])
            name = member.display_name if member else f"Usuario {row['user_id']}"
            prefix = medals[i] if i < 3 else f"`#{i + 1}`"
            lines.append(f"{prefix} **{name}** — {money(row['balance'])}")

        embed = base_embed(title=f"🏆 Top {config.CURRENCY_NAME}", description="\n".join(lines))
        await ctx.send(embed=embed)

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"⚠️ Falta el argumento `{error.param.name}`.")
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send("⚠️ Uno de los datos que diste no es válido.")
            return


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
