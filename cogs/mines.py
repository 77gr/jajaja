"""
cogs/mines.py
-------------
Minijuego "Mines" (como el de tu captura): el usuario apuesta, elige
cuántas minas quiere en el tablero y va destapando casillas. Cada casilla
segura sube el multiplicador; si cae en una mina, pierde la apuesta.
Puede retirarse ("cobrar") en cualquier momento para asegurar las ganancias.
"""

import math
import random

import discord
from discord.ext import commands

from config import config
from database import db
from utils.embeds import base_embed, error_embed, money

GRID_COLUMNS = 4
GRID_ROWS = 4
TOTAL_CELLS = GRID_COLUMNS * GRID_ROWS
HOUSE_EDGE = 0.97  # 3% de margen de la casa, como cualquier casino de este estilo


def fair_multiplier(picks: int, mines: int) -> float:
    """Multiplicador justo para `picks` casillas seguras destapadas con `mines` minas
    en un tablero de TOTAL_CELLS, aplicando el margen de la casa."""
    if picks == 0:
        return 1.0
    total = TOTAL_CELLS
    mult = 1.0
    for i in range(picks):
        mult *= (total - i) / (total - mines - i)
    return mult * HOUSE_EDGE


class MinesView(discord.ui.View):
    def __init__(self, cog: "Mines", user: discord.Member, guild_id: int, bet: int, mines: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.user = user
        self.guild_id = guild_id
        self.bet = bet
        self.mines = mines
        self.picks = 0
        self.finished = False
        self.message: discord.Message | None = None
        self.mine_positions = set(random.sample(range(TOTAL_CELLS), mines))

        self.cell_buttons: list[discord.ui.Button] = []
        for index in range(TOTAL_CELLS):
            button = discord.ui.Button(
                label="❔", style=discord.ButtonStyle.secondary, row=index // GRID_COLUMNS
            )
            button.callback = self._make_callback(index)
            self.cell_buttons.append(button)
            self.add_item(button)

        self.cashout_button = discord.ui.Button(
            label=f"💰 Retirar {money(bet)}", style=discord.ButtonStyle.success, row=4
        )
        self.cashout_button.callback = self.cash_out
        self.add_item(self.cashout_button)

    def _make_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            await self.reveal(interaction, index)
        return callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "Esta partida no es tuya.", ephemeral=True
            )
            return False
        return True

    def current_payout(self) -> int:
        return math.floor(self.bet * fair_multiplier(self.picks, self.mines))

    def build_embed(self, *, status: str, color: int) -> discord.Embed:
        embed = base_embed(title="💣 Mines", color=color)
        embed.add_field(name="Apuesta", value=money(self.bet))
        embed.add_field(name="Minas", value=str(self.mines))
        embed.add_field(name="Destapadas", value=str(self.picks))
        mult = fair_multiplier(self.picks, self.mines)
        embed.add_field(name="Multiplicador", value=f"x{mult:.2f}")
        embed.add_field(name="Retirando ahora cobras", value=money(self.current_payout()))
        embed.description = status
        return embed

    async def reveal(self, interaction: discord.Interaction, index: int):
        if self.finished:
            return
        button = self.cell_buttons[index]
        button.disabled = True

        if index in self.mine_positions:
            self.finished = True
            for i, b in enumerate(self.cell_buttons):
                b.disabled = True
                if i in self.mine_positions:
                    b.label = "💣"
                    b.style = discord.ButtonStyle.danger
            self.cashout_button.disabled = True
            self.stop()
            embed = self.build_embed(
                status=f"💥 ¡Mina! Perdiste **{money(self.bet)}**.",
                color=config.COLOR_DANGER,
            )
            embed.add_field(name="Saldo", value=money((await db.get_user(self.user.id, self.guild_id))["balance"]))
            await interaction.response.edit_message(embed=embed, view=self)
            return

        button.label = "💎"
        button.style = discord.ButtonStyle.success
        self.picks += 1
        self.cashout_button.label = f"💰 Retirar {money(self.current_payout())}"

        if self.picks == TOTAL_CELLS - self.mines:
            await self._finish_win(interaction)
            return

        embed = self.build_embed(status="Sigue destapando o retírate cuando quieras.", color=config.COLOR_DEFAULT)
        await interaction.response.edit_message(embed=embed, view=self)

    async def cash_out(self, interaction: discord.Interaction):
        if self.finished:
            return
        await self._finish_win(interaction)

    async def _finish_win(self, interaction: discord.Interaction):
        self.finished = True
        payout = self.current_payout()
        new_balance = await db.update_balance(self.user.id, self.guild_id, payout)

        for i, b in enumerate(self.cell_buttons):
            b.disabled = True
            if i in self.mine_positions:
                b.label = "💣"
        self.cashout_button.disabled = True
        self.stop()

        embed = self.build_embed(
            status=f"✅ Te retiraste a tiempo y cobraste **{money(payout)}**.",
            color=config.COLOR_SUCCESS,
        )
        embed.add_field(name="Saldo", value=money(new_balance))
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        payout = self.current_payout()
        await db.update_balance(self.user.id, self.guild_id, payout)
        for b in self.cell_buttons:
            b.disabled = True
        self.cashout_button.disabled = True
        if self.message:
            try:
                embed = self.build_embed(
                    status=f"⌛ Tiempo agotado. Te retiramos automáticamente **{money(payout)}**.",
                    color=config.COLOR_WARNING,
                )
                await self.message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass


class Mines(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(
        name="mines",
        help="Juega Mines: destapa casillas seguras y evita las minas. Uso: ,mines <apuesta> [minas 1-10]",
    )
    async def mines(
        self,
        ctx: commands.Context,
        apuesta: commands.Range[int, 1],
        minas: commands.Range[int, 1, 10] = 3,
    ):
        user_row = await db.get_user(ctx.author.id, ctx.guild.id)
        if user_row["balance"] < apuesta:
            await ctx.send(embed=error_embed("No tienes suficiente saldo para esa apuesta."))
            return
        if minas >= TOTAL_CELLS:
            await ctx.send(embed=error_embed(f"El tablero solo tiene {TOTAL_CELLS} casillas."))
            return

        await db.update_balance(ctx.author.id, ctx.guild.id, -apuesta)

        view = MinesView(self, ctx.author, ctx.guild.id, apuesta, minas)
        embed = view.build_embed(status="Elige una casilla para empezar.", color=config.COLOR_DEFAULT)
        view.message = await ctx.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Mines(bot))
