"""
cogs/bump.py
-------------
Bump Reminder: detecta cuando alguien hace bump del servidor con el bot
de Disboard (lee el embed de confirmación que Disboard publica) y, tras
el cooldown de 2 horas, recuerda en el canal configurado que ya se puede
volver a hacer /bump.
"""

import asyncio
import time

import discord
from discord.ext import commands

from database import db
from utils.embeds import error_embed, success_embed

DISBOARD_BOT_ID = 302050872383242240
BUMP_COOLDOWN = 2 * 60 * 60


class Bump(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.id != DISBOARD_BOT_ID or not message.guild:
            return
        if not message.embeds:
            return

        config_row = await db.get_bump_config(message.guild.id)
        if not config_row["channel_id"]:
            return

        await db.set_bump_field(message.guild.id, "last_bump", int(time.time()))
        await message.channel.send(
            embed=success_embed("¡Gracias por el bump! Te recuerdo en 2 horas para el siguiente. ⏰")
        )

        asyncio.create_task(self._remind_later(message.guild.id))

    async def _remind_later(self, guild_id: int):
        await asyncio.sleep(BUMP_COOLDOWN)
        config_row = await db.get_bump_config(guild_id)
        channel_id = config_row["channel_id"]
        if not channel_id:
            return
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            return

        role_mention = f"<@&{config_row['role_id']}> " if config_row["role_id"] else ""
        try:
            await channel.send(f"{role_mention}⏰ ¡Ya puedes usar `/bump` de nuevo!")
        except discord.HTTPException:
            pass

    @commands.command(
        name="bump-channel",
        help="[Admin] Configura el canal para recordatorios de bump. Uso: ,bump-channel #canal [@rol]",
    )
    @commands.has_permissions(manage_guild=True)
    async def bump_channel(
        self, ctx: commands.Context, canal: discord.TextChannel, rol: discord.Role | None = None
    ):
        await db.set_bump_field(ctx.guild.id, "channel_id", canal.id)
        if rol:
            await db.set_bump_field(ctx.guild.id, "role_id", rol.id)
        await ctx.send(embed=success_embed(f"Los recordatorios de bump se enviarán en {canal.mention}."))

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=error_embed("Necesitas permiso de `Administrar servidor` para usar esto."))
            return


async def setup(bot: commands.Bot):
    await bot.add_cog(Bump(bot))
