"""
cogs/chickenfight.py
----------------------
"Pelea de pollos": un minijuego PvP. Retas a otro usuario a apostar la
misma cantidad; si acepta, el bot anima un pequeño combate por rondas y el
ganador se lleva el pozo completo (con una pequeña comisión de la casa).
"""

import asyncio
import random

import discord
from discord.ext import commands

from config import config
from database import db
from utils.embeds import base_embed, error_embed, money

HOUSE_EDGE = 0.95  # el ganador se lleva el 95% del pozo total

ROUND_LINES = [
    "🐔 {a} picotea a {b}!",
    "🐔 {b} le da un aletazo a {a}!",
    "🐔 {a} esquiva por poco!",
    "🐔 {b} esquiva por poco!",
    "🐔 ¡Ambos se lanzan plumas el uno al otro!",
    "🐔 {a} gana terreno en el gallinero!",
    "🐔 {b} gana terreno en el gallinero!",
]


class ChallengeView(discord.ui.View):
    def __init__(self, challenger: discord.Member, opponent: discord.Member, bet: int):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.opponent = opponent
        self.bet = bet
        self.resolved = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message(
                "Este reto de pelea de pollos no es para ti.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="🐔 Aceptar pelea", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.resolved:
            return
        self.resolved = True

        opponent_row = await db.get_user(self.opponent.id, interaction.guild_id)
        if opponent_row["balance"] < self.bet:
            for c in self.children:
                c.disabled = True
            await interaction.response.edit_message(
                embed=error_embed("No tienes suficiente saldo para aceptar esta apuesta."), view=self
            )
            return

        challenger_row = await db.get_user(self.challenger.id, interaction.guild_id)
        if challenger_row["balance"] < self.bet:
            for c in self.children:
                c.disabled = True
            await interaction.response.edit_message(
                embed=error_embed(f"{self.challenger.mention} ya no tiene saldo suficiente para esta pelea."),
                view=self,
            )
            return

        for c in self.children:
            c.disabled = True
        await interaction.response.edit_message(view=self)

        await db.update_balance(self.challenger.id, interaction.guild_id, -self.bet)
        await db.update_balance(self.opponent.id, interaction.guild_id, -self.bet)

        message = await interaction.original_response()
        await run_fight(message, interaction.guild_id, self.challenger, self.opponent, self.bet)

    @discord.ui.button(label="❌ Rechazar", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.resolved:
            return
        self.resolved = True
        for c in self.children:
            c.disabled = True
        await interaction.response.edit_message(
            embed=error_embed(f"{self.opponent.display_name} rechazó la pelea."), view=self
        )

    async def on_timeout(self):
        if self.resolved:
            return
        self.resolved = True
        for c in self.children:
            c.disabled = True


async def run_fight(message: discord.Message, guild_id: int, a: discord.Member, b: discord.Member, bet: int):
    pot = bet * 2
    payout = int(pot * HOUSE_EDGE)

    rounds = random.randint(3, 5)

    for i in range(rounds):
        line = random.choice(ROUND_LINES).format(a=a.mention, b=b.mention)
        embed = base_embed(title="🐔 ¡Pelea de pollos en curso!", description=line)
        embed.add_field(name="Pozo en juego", value=money(pot))
        embed.set_footer(text=f"Ronda {i + 1}/{rounds}")
        await message.edit(embed=embed, view=None)
        await asyncio.sleep(1.4)

    winner, loser = random.sample([a, b], 2)
    new_balance = await db.update_balance(winner.id, guild_id, payout)

    embed = base_embed(title="🏆 ¡Pelea terminada!", color=config.COLOR_SUCCESS)
    embed.description = (
        f"{winner.mention} venció a {loser.mention} en el gallinero y se lleva "
        f"**{money(payout)}**."
    )
    embed.add_field(name=f"Saldo de {winner.display_name}", value=money(new_balance))
    await message.edit(embed=embed, view=None)


class ChickenFight(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(
        name="chickenfight",
        help="Reta a otro usuario a una pelea de pollos apostando monedas. Uso: ,chickenfight @usuario <apuesta>",
    )
    async def chickenfight(
        self, ctx: commands.Context, usuario: discord.Member, apuesta: commands.Range[int, 1]
    ):
        if usuario.id == ctx.author.id:
            await ctx.send(embed=error_embed("No puedes retarte a ti mismo."))
            return
        if usuario.bot:
            await ctx.send(embed=error_embed("No puedes retar a un bot."))
            return

        challenger_row = await db.get_user(ctx.author.id, ctx.guild.id)
        if challenger_row["balance"] < apuesta:
            await ctx.send(embed=error_embed("No tienes suficiente saldo para esa apuesta."))
            return

        embed = base_embed(
            title="🐔 ¡Reto de pelea de pollos!",
            description=(
                f"{ctx.author.mention} reta a {usuario.mention} a una pelea "
                f"apostando **{money(apuesta)}** cada uno.\n\n"
                f"{usuario.mention}, ¿aceptas?"
            ),
        )
        view = ChallengeView(ctx.author, usuario, apuesta)
        await ctx.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(ChickenFight(bot))
