"""
cogs/snipe.py
--------------
Snipe: guarda en memoria el último mensaje borrado y el último editado de
cada canal, para poder recuperarlos con ,snipe y ,editsnipe.
"""

import time

import discord
from discord.ext import commands

from utils.embeds import base_embed, error_embed

MAX_AGE_SECONDS = 60 * 60  # solo mostramos snipes de la última hora


class Snipe(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.deleted: dict[int, dict] = {}
        self.edited: dict[int, dict] = {}

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        self.deleted[message.channel.id] = {
            "content": message.content,
            "author": message.author,
            "attachments": [a.url for a in message.attachments],
            "ts": time.time(),
        }

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild or before.content == after.content:
            return
        self.edited[before.channel.id] = {
            "before": before.content,
            "after": after.content,
            "author": before.author,
            "ts": time.time(),
        }

    @commands.command(name="snipe", help="Muestra el último mensaje borrado en este canal")
    async def snipe(self, ctx: commands.Context):
        data = self.deleted.get(ctx.channel.id)
        if not data or time.time() - data["ts"] > MAX_AGE_SECONDS:
            await ctx.send(embed=error_embed("No hay ningún mensaje reciente para recuperar aquí."))
            return

        embed = base_embed(description=data["content"] or "*(sin texto)*")
        embed.set_author(name=str(data["author"]), icon_url=data["author"].display_avatar.url)
        if data["attachments"]:
            embed.set_image(url=data["attachments"][0])
        embed.set_footer(text="Mensaje eliminado")
        await ctx.send(embed=embed)

    @commands.command(name="editsnipe", help="Muestra la última edición de un mensaje en este canal")
    async def editsnipe(self, ctx: commands.Context):
        data = self.edited.get(ctx.channel.id)
        if not data or time.time() - data["ts"] > MAX_AGE_SECONDS:
            await ctx.send(embed=error_embed("No hay ninguna edición reciente para mostrar aquí."))
            return

        embed = base_embed()
        embed.set_author(name=str(data["author"]), icon_url=data["author"].display_avatar.url)
        embed.add_field(name="Antes", value=data["before"] or "*(vacío)*", inline=False)
        embed.add_field(name="Después", value=data["after"] or "*(vacío)*", inline=False)
        embed.set_footer(text="Mensaje editado")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Snipe(bot))
