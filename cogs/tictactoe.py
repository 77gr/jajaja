"""
cogs/tictactoe.py
--------------------
Tres en raya (tic-tac-toe) PvP con botones, uno de los juegos clásicos
que traen los bots todo-en-uno.
"""

import discord
from discord.ext import commands

from utils.embeds import base_embed, error_embed


class TicTacToeButton(discord.ui.Button):
    def __init__(self, row: int, col: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="\u200b", row=row)
        self.row_i = row
        self.col_i = col

    async def callback(self, interaction: discord.Interaction):
        view: "TicTacToeView" = self.view
        await view.play(interaction, self)


class TicTacToeView(discord.ui.View):
    X, O = "❌", "⭕"

    def __init__(self, player_x: discord.Member, player_o: discord.Member):
        super().__init__(timeout=120)
        self.player_x = player_x
        self.player_o = player_o
        self.turn = player_x
        self.board = [[None] * 3 for _ in range(3)]
        for r in range(3):
            for c in range(3):
                self.add_item(TicTacToeButton(r, c))

    def current_symbol(self) -> str:
        return self.X if self.turn == self.player_x else self.O

    def check_winner(self) -> str | None:
        lines = []
        lines.extend(self.board)  # filas
        lines.extend([[self.board[r][c] for r in range(3)] for c in range(3)])  # columnas
        lines.append([self.board[i][i] for i in range(3)])
        lines.append([self.board[i][2 - i] for i in range(3)])
        for line in lines:
            if line[0] is not None and line[0] == line[1] == line[2]:
                return line[0]
        if all(self.board[r][c] is not None for r in range(3) for c in range(3)):
            return "draw"
        return None

    async def play(self, interaction: discord.Interaction, button: TicTacToeButton):
        if interaction.user.id != self.turn.id:
            await interaction.response.send_message("No es tu turno.", ephemeral=True)
            return
        if self.board[button.row_i][button.col_i] is not None:
            await interaction.response.send_message("Esa casilla ya está ocupada.", ephemeral=True)
            return

        symbol = self.current_symbol()
        self.board[button.row_i][button.col_i] = symbol
        button.label = symbol
        button.disabled = True
        button.style = discord.ButtonStyle.danger if symbol == self.X else discord.ButtonStyle.success

        result = self.check_winner()
        if result == "draw":
            for child in self.children:
                child.disabled = True
            embed = base_embed(title="🎮 Tic-Tac-Toe", description="¡Empate!")
            await interaction.response.edit_message(embed=embed, view=self)
            self.stop()
            return
        if result is not None:
            winner = self.player_x if result == self.X else self.player_o
            for child in self.children:
                child.disabled = True
            embed = base_embed(title="🎮 Tic-Tac-Toe", description=f"¡{winner.mention} gana! 🎉")
            await interaction.response.edit_message(embed=embed, view=self)
            self.stop()
            return

        self.turn = self.player_o if self.turn == self.player_x else self.player_x
        embed = base_embed(
            title="🎮 Tic-Tac-Toe",
            description=f"Turno de {self.turn.mention} ({self.current_symbol()})",
        )
        await interaction.response.edit_message(embed=embed, view=self)


class TicTacToe(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="tictactoe", help="Reta a otro usuario a tres en raya. Uso: ,tictactoe @usuario")
    async def tictactoe(self, ctx: commands.Context, usuario: discord.Member):
        if usuario.id == ctx.author.id or usuario.bot:
            await ctx.send(embed=error_embed("Ese oponente no es válido."))
            return

        view = TicTacToeView(ctx.author, usuario)
        embed = base_embed(
            title="🎮 Tic-Tac-Toe",
            description=f"{ctx.author.mention} ({view.X}) vs {usuario.mention} ({view.O})\n"
            f"Turno de {ctx.author.mention}",
        )
        await ctx.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(TicTacToe(bot))
