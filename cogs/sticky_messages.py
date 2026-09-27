"""
cogs/sticky_messages.py
------------------------
Un "sticky message" es un mensaje que el bot vuelve a publicar cada vez
que hay actividad nueva en el canal, para que siempre quede al final
(reglas, enlaces importantes, etc).

Uso:
    ,sticky set <mensaje>
    ,sticky remove
"""

import discord
from discord.ext import commands

from database import db
from utils.embeds import base_embed, success_embed


class StickyMessages(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="sticky", invoke_without_command=True, help="Gestiona el mensaje fijo de este canal")
    async def sticky(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @sticky.command(name="set", help="Fija un mensaje que se repetirá al final del canal")
    @commands.has_permissions(manage_messages=True)
    async def sticky_set(self, ctx: commands.Context, *, mensaje: str):
        await db.set_sticky(ctx.channel.id, ctx.guild.id, mensaje)
        sent = await ctx.channel.send(embed=base_embed(description=mensaje))
        await db.set_sticky_last_id(ctx.channel.id, sent.id)
        await ctx.send(embed=success_embed("Mensaje fijado en este canal."))

    @sticky.command(name="remove", help="Quita el mensaje fijo de este canal")
    @commands.has_permissions(manage_messages=True)
    async def sticky_remove(self, ctx: commands.Context):
        await db.remove_sticky(ctx.channel.id)
        await ctx.send(embed=success_embed("Mensaje fijo eliminado."))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        sticky = await db.get_sticky(message.channel.id)
        if sticky is None:
            return

        if sticky["last_message_id"]:
            try:
                old = await message.channel.fetch_message(sticky["last_message_id"])
                await old.delete()
            except discord.HTTPException:
                pass

        new_msg = await message.channel.send(embed=base_embed(description=sticky["content"]))
        await db.set_sticky_last_id(message.channel.id, new_msg.id)

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            from utils.embeds import error_embed
            await ctx.send(embed=error_embed("Necesitas permiso suficiente para usar esto."))
            return


async def setup(bot: commands.Bot):
    await bot.add_cog(StickyMessages(bot))
