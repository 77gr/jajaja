"""
cogs/tickets.py
----------------
Sistema de tickets de soporte: un panel con un botón "Abrir ticket" crea
un canal privado entre el usuario y el staff. Otro botón lo cierra.

Comando: ,ticket setup
"""

import discord
from discord.ext import commands

from database import db
from utils.checks import is_staff
from utils.embeds import base_embed, error_embed, success_embed


class TicketPanel(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Abrir ticket", emoji="🎫", style=discord.ButtonStyle.primary, custom_id="ticket:open")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        channel = await guild.create_text_channel(
            f"ticket-{interaction.user.name}", overwrites=overwrites, reason="Nuevo ticket"
        )
        await db.create_ticket(channel.id, guild.id, interaction.user.id)

        embed = base_embed(
            title="🎫 Ticket abierto",
            description=f"Hola {interaction.user.mention}, cuéntanos en qué te podemos ayudar.\n"
            f"El staff será notificado.",
        )
        await channel.send(embed=embed, view=TicketControls(self.bot))
        await interaction.response.send_message(
            embed=success_embed(f"Se creó tu ticket: {channel.mention}"), ephemeral=True
        )


class TicketControls(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Cerrar ticket", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="ticket:close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction.user):
            await interaction.response.send_message(
                embed=error_embed("Solo el staff puede cerrar el ticket."), ephemeral=True
            )
            return
        await db.close_ticket(interaction.channel_id)
        await interaction.response.send_message("🔒 Cerrando este ticket en 5 segundos...")
        await interaction.channel.edit(name=f"cerrado-{interaction.channel.name}")
        await interaction.channel.set_permissions(interaction.guild.default_role, view_channel=False)


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_view(TicketPanel(bot))
        bot.add_view(TicketControls(bot))

    @commands.group(name="ticket", invoke_without_command=True, help="Comandos de tickets: setup")
    async def ticket(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @ticket.command(name="setup", aliases=["panel"], help="Publica el panel para abrir tickets de soporte")
    @commands.has_permissions(manage_guild=True)
    async def ticket_setup(self, ctx: commands.Context):
        embed = base_embed(
            title="🎫 Soporte",
            description="Pulsa el botón para abrir un ticket privado con el staff.",
        )
        await ctx.channel.send(embed=embed, view=TicketPanel(self.bot))
        await ctx.send("Panel publicado.", delete_after=5)

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=error_embed("Necesitas permiso de `Administrar servidor` para usar esto."))
            return


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
