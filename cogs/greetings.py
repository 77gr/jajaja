"""
cogs/greetings.py
------------------
Mensajes de bienvenida y despedida configurables por servidor.
Usa {usuario}, {servidor} y {total_miembros} como variables en el mensaje.

Uso:
    ,welcome set #canal <mensaje>
    ,welcome enable / ,welcome disable
    ,welcome test
    ,goodbye set #canal <mensaje>
    ,goodbye enable / ,goodbye disable
    ,goodbye test
"""

import discord
from discord.ext import commands

from database import db
from utils.embeds import base_embed, error_embed, success_embed


def render(template: str, member: discord.Member) -> str:
    return (
        template.replace("{usuario}", member.mention)
        .replace("{servidor}", member.guild.name)
        .replace("{total_miembros}", str(member.guild.member_count))
    )


class Greetings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Bienvenida ---

    @commands.group(name="welcome", invoke_without_command=True, help="Gestiona el sistema de bienvenida")
    async def welcome(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @welcome.command(name="set", help="[Admin] Configura el canal y mensaje de bienvenida. Uso: ,welcome set #canal <mensaje>")
    @commands.has_permissions(manage_guild=True)
    async def config_welcome(self, ctx: commands.Context, canal: discord.TextChannel, *, mensaje: str):
        await db.set_guild_field(ctx.guild.id, "welcome_channel_id", canal.id)
        await db.set_guild_field(ctx.guild.id, "welcome_message", mensaje)
        await ctx.send(embed=success_embed(f"Bienvenidas configuradas en {canal.mention}."))

    @welcome.command(name="enable", help="[Admin] Activa el sistema de bienvenida")
    @commands.has_permissions(manage_guild=True)
    async def welcome_enable(self, ctx: commands.Context):
        await db.set_guild_field(ctx.guild.id, "welcome_enabled", 1)
        await ctx.send(embed=success_embed("Sistema de bienvenida **activado**."))

    @welcome.command(name="disable", help="[Admin] Desactiva el sistema de bienvenida")
    @commands.has_permissions(manage_guild=True)
    async def welcome_disable(self, ctx: commands.Context):
        await db.set_guild_field(ctx.guild.id, "welcome_enabled", 0)
        await ctx.send(embed=success_embed("Sistema de bienvenida **desactivado**."))

    @welcome.command(name="test", help="[Admin] Envía un mensaje de bienvenida de prueba")
    @commands.has_permissions(manage_guild=True)
    async def bienvenida_test(self, ctx: commands.Context):
        cfg = await db.get_guild_config(ctx.guild.id)
        if not cfg["welcome_message"]:
            await ctx.send(embed=error_embed("Todavía no configuraste un mensaje con `,welcome set`."))
            return
        embed = base_embed(description=render(cfg["welcome_message"], ctx.author))
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        channel = ctx.guild.get_channel(cfg["welcome_channel_id"]) if cfg["welcome_channel_id"] else None
        if channel:
            await channel.send(embed=embed)
            await ctx.send(embed=success_embed(f"Mensaje de prueba enviado en {channel.mention}."))
        else:
            await ctx.send(embed=embed)

    # --- Despedida ---

    @commands.group(name="goodbye", invoke_without_command=True, help="Gestiona el sistema de despedida")
    async def goodbye(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @goodbye.command(name="set", help="[Admin] Configura el canal y mensaje de despedida. Uso: ,goodbye set #canal <mensaje>")
    @commands.has_permissions(manage_guild=True)
    async def config_leave(self, ctx: commands.Context, canal: discord.TextChannel, *, mensaje: str):
        await db.set_guild_field(ctx.guild.id, "leave_channel_id", canal.id)
        await db.set_guild_field(ctx.guild.id, "leave_message", mensaje)
        await ctx.send(embed=success_embed(f"Despedidas configuradas en {canal.mention}."))

    @goodbye.command(name="enable", help="[Admin] Activa el sistema de despedida")
    @commands.has_permissions(manage_guild=True)
    async def goodbye_enable(self, ctx: commands.Context):
        await db.set_guild_field(ctx.guild.id, "leave_enabled", 1)
        await ctx.send(embed=success_embed("Sistema de despedida **activado**."))

    @goodbye.command(name="disable", help="[Admin] Desactiva el sistema de despedida")
    @commands.has_permissions(manage_guild=True)
    async def goodbye_disable(self, ctx: commands.Context):
        await db.set_guild_field(ctx.guild.id, "leave_enabled", 0)
        await ctx.send(embed=success_embed("Sistema de despedida **desactivado**."))

    @goodbye.command(name="test", help="[Admin] Envía un mensaje de despedida de prueba")
    @commands.has_permissions(manage_guild=True)
    async def despedida_test(self, ctx: commands.Context):
        cfg = await db.get_guild_config(ctx.guild.id)
        if not cfg["leave_message"]:
            await ctx.send(embed=error_embed("Todavía no configuraste un mensaje con `,goodbye set`."))
            return
        embed = base_embed(description=render(cfg["leave_message"], ctx.author))
        channel = ctx.guild.get_channel(cfg["leave_channel_id"]) if cfg["leave_channel_id"] else None
        if channel:
            await channel.send(embed=embed)
            await ctx.send(embed=success_embed(f"Mensaje de prueba enviado en {channel.mention}."))
        else:
            await ctx.send(embed=embed)

    # --- Eventos ---

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = await db.get_guild_config(member.guild.id)
        if not cfg["welcome_enabled"] or not cfg["welcome_channel_id"] or not cfg["welcome_message"]:
            return
        channel = member.guild.get_channel(cfg["welcome_channel_id"])
        if channel is None:
            return
        embed = base_embed(description=render(cfg["welcome_message"], member))
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        cfg = await db.get_guild_config(member.guild.id)
        if not cfg["leave_enabled"] or not cfg["leave_channel_id"] or not cfg["leave_message"]:
            return
        channel = member.guild.get_channel(cfg["leave_channel_id"])
        if channel is None:
            return
        embed = base_embed(description=render(cfg["leave_message"], member))
        await channel.send(embed=embed)

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=error_embed("Necesitas permiso de `Administrar servidor` para usar esto."))
            return


async def setup(bot: commands.Bot):
    await bot.add_cog(Greetings(bot))
