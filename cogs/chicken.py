"""
cogs/chicken.py
----------------
Minijuego "Chicken" (como el de tu captura): el usuario apuesta y avanza
carril por carril. Cada avance sube el multiplicador pero arriesga la
apuesta según la dificultad elegida. Puede retirarse en cualquier momento.
Al retirarte se te muestra, a modo de intriga, cuántos carriles más
habrían sido seguros si hubieras seguido.
"""

import math
import random

import discord
from discord.ext import commands

from config import config
from database import db
from utils.embeds import base_embed, error_embed, money

TOTAL_STAGES = 10
HOUSE_EDGE = 0.97

DIFFICULTIES = {
    "facil": {"label": "Fácil", "survival": 0.90, "growth": 1.12, "base": 1.05},
    "media": {"label": "Media", "survival": 0.78, "growth": 1.28, "base": 1.10},
    "dificil": {"label": "Difícil", "survival": 0.60, "growth": 1.55, "base": 1.20},
}


def stage_multiplier(difficulty: dict, stage: int) -> float:
    """Multiplicador acumulado tras sobrevivir `stage` carriles (stage >= 1)."""
    if stage <= 0:
        return 1.0
    return round(HOUSE_EDGE * difficulty["base"] * (difficulty["growth"] ** (stage - 1)), 2)


class ChickenView(discord.ui.View):
    def __init__(self, user: discord.Member, guild_id: int, bet: int, difficulty_key: str):
        super().__init__(timeout=180)
        self.user = user
        self.guild_id = guild_id
        self.bet = bet
        self.difficulty_key = difficulty_key
        self.difficulty = DIFFICULTIES[difficulty_key]
        self.stage = 0
        self.finished = False
        self.message: discord.Message | None = None
        # Camino pregenerado: True = ese carril era seguro, False = ahí estaba el peligro.
        self.outcomes = [random.random() < self.difficulty["survival"] for _ in range(TOTAL_STAGES)]

        self.advance_button = discord.ui.Button(
            label=f"➡️ Avanzar x{stage_multiplier(self.difficulty, 1)}",
            style=discord.ButtonStyle.primary,
        )
        self.advance_button.callback = self.advance
        self.cashout_button = discord.ui.Button(
            label=f"💰 Retirar {money(bet)}", style=discord.ButtonStyle.success
        )
        self.cashout_button.callback = self.cash_out
        self.add_item(self.advance_button)
        self.add_item(self.cashout_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("Esta partida no es tuya.", ephemeral=True)
            return False
        return True

    def progress_bar(self) -> str:
        done = "✅" * self.stage
        pending = "⬜" * (TOTAL_STAGES - self.stage)
        return done + pending

    def current_payout(self) -> int:
        return math.floor(self.bet * stage_multiplier(self.difficulty, self.stage))

    def build_embed(self, *, status: str, color: int, extra: str | None = None) -> discord.Embed:
        embed = base_embed(title=f"🐔 Chicken · {self.difficulty['label']}", color=color)
        embed.description = f"{self.progress_bar()}\n\n{status}"
        embed.add_field(name="Apuesta", value=money(self.bet))
        embed.add_field(name="Cobras", value=money(self.current_payout()))
        if self.stage < TOTAL_STAGES:
            embed.add_field(
                name="Siguiente avance",
                value=f"x{stage_multiplier(self.difficulty, self.stage + 1)}",
            )
        if extra:
            embed.add_field(name="\u200b", value=extra, inline=False)
        return embed

    async def advance(self, interaction: discord.Interaction):
        if self.finished:
            return
        safe = self.outcomes[self.stage]
        self.stage += 1

        if not safe:
            self.finished = True
            self.stop()
            for item in self.children:
                item.disabled = True
            embed = self.build_embed(
                status=f"💥 ¡Te atropellaron en el carril {self.stage}! Perdiste **{money(self.bet)}**.",
                color=config.COLOR_DANGER,
            )
            await interaction.response.edit_message(embed=embed, view=self)
            return

        if self.stage >= TOTAL_STAGES:
            await self._finish_win(interaction, final=True)
            return

        self.advance_button.label = f"➡️ Avanzar x{stage_multiplier(self.difficulty, self.stage + 1)}"
        self.cashout_button.label = f"💰 Retirar {money(self.current_payout())}"
        embed = self.build_embed(status="Sigue avanzando o retírate cuando quieras.", color=config.COLOR_DEFAULT)
        await interaction.response.edit_message(embed=embed, view=self)

    async def cash_out(self, interaction: discord.Interaction):
        if self.finished:
            return
        await self._finish_win(interaction, final=False)

    async def _finish_win(self, interaction: discord.Interaction, final: bool):
        self.finished = True
        payout = self.current_payout()
        new_balance = await db.update_balance(self.user.id, self.guild_id, payout)
        self.stop()
        for item in self.children:
            item.disabled = True

        extra = None
        if not final:
            # Cuenta cuántos carriles siguientes habrían sido seguros, para intriga.
            free_ahead = 0
            look = self.stage
            while look < TOTAL_STAGES and self.outcomes[look]:
                free_ahead += 1
                look += 1
            if free_ahead > 0:
                would_have_payout = math.floor(
                    self.bet * stage_multiplier(self.difficulty, self.stage + free_ahead)
                )
                extra = (
                    f"🐓 Los {free_ahead} siguientes estaban libres: "
                    f"habrías cobrado {money(would_have_payout)}."
                )
            else:
                extra = "🐓 ¡Justo a tiempo! El siguiente carril tenía peligro."

        status = "🏁 ¡Cruzaste todos los carriles!" if final else "💰 Te retiraste a tiempo."
        embed = self.build_embed(status=f"{status} Cobras **{money(payout)}**.", color=config.COLOR_SUCCESS, extra=extra)
        embed.add_field(name="Saldo", value=money(new_balance))
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        payout = self.current_payout()
        await db.update_balance(self.user.id, self.guild_id, payout)
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                embed = self.build_embed(
                    status=f"⌛ Tiempo agotado. Te retiramos automáticamente **{money(payout)}**.",
                    color=config.COLOR_WARNING,
                )
                await self.message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass


class Chicken(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(
        name="chicken",
        help="Juega Chicken: avanza por los carriles sin que te atropellen. Uso: ,chicken <apuesta> [facil|media|dificil]",
    )
    async def chicken(
        self,
        ctx: commands.Context,
        apuesta: commands.Range[int, 1],
        dificultad: str = "media",
    ):
        difficulty_key = dificultad.lower()
        if difficulty_key not in DIFFICULTIES:
            await ctx.send(embed=error_embed("La dificultad debe ser `facil`, `media` o `dificil`."))
            return

        user_row = await db.get_user(ctx.author.id, ctx.guild.id)
        if user_row["balance"] < apuesta:
            await ctx.send(embed=error_embed("No tienes suficiente saldo para esa apuesta."))
            return

        await db.update_balance(ctx.author.id, ctx.guild.id, -apuesta)

        view = ChickenView(ctx.author, ctx.guild.id, apuesta, difficulty_key)
        embed = view.build_embed(status="¡Avanza cuando quieras!", color=config.COLOR_DEFAULT)
        view.message = await ctx.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Chicken(bot))
