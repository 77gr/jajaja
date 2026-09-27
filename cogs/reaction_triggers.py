"""
cogs/reaction_triggers.py
----------------------------
Como el autoresponder, pero en vez de responder con un mensaje, el bot
reacciona al mensaje con un emoji cuando detecta el trigger.

Uso:
    ,reactiontrigger add <trigger> <emoji>
    ,reactiontrigger remove <trigger>
    ,reactiontrigger list
"""

import discord
from discord.ext import commands

from database import db
from utils.checks import is_staff
from utils.embeds import base_embed, error_embed, success_embed


class ReactionTriggers(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._cache: dict[int, list] = {}

    async def _rows(self, guild_id: int):
        if guild_id not in self._cache:
            self._cache[guild_id] = await db.get_reaction_triggers(guild_id)
        return self._cache[guild_id]

    def _invalidate(self, guild_id: int):
        self._cache.pop(guild_id, None)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        content = message.content.strip().lower()
        if not content:
            return

        rows = await self._rows(message.guild.id)
        for row in rows:
            match = content == row["trigger"] if row["match_type"] == "strict" else row["trigger"] in content
            if match:
                try:
                    await message.add_reaction(row["emoji"])
                except discord.HTTPException:
                    pass

    @commands.group(name="reactiontrigger", aliases=["rt"], invoke_without_command=True)
    async def reactiontrigger(self, ctx: commands.Context):
        await self.list_triggers(ctx)

    @reactiontrigger.command(name="add")
    async def add(self, ctx: commands.Context, trigger: str, emoji: str):
        if not is_staff(ctx.author):
            await ctx.send(embed=error_embed("Necesitas permiso de `Administrar servidor` para usar esto."))
            return
        await db.add_reaction_trigger(ctx.guild.id, trigger, emoji, "contains", ctx.author.id)
        self._invalidate(ctx.guild.id)
        await ctx.send(embed=success_embed(f"Cuando alguien escriba **{trigger}**, reaccionaré con {emoji}."))

    @reactiontrigger.command(name="remove", aliases=["delete", "del"])
    async def remove(self, ctx: commands.Context, trigger: str):
        if not is_staff(ctx.author):
            await ctx.send(embed=error_embed("Necesitas permiso de `Administrar servidor` para usar esto."))
            return
        ok = await db.remove_reaction_trigger(ctx.guild.id, trigger)
        self._invalidate(ctx.guild.id)
        if ok:
            await ctx.send(embed=success_embed(f"Reaction trigger **{trigger}** eliminado."))
        else:
            await ctx.send(embed=error_embed("No encontré ese trigger."))

    @reactiontrigger.command(name="list")
    async def list_triggers(self, ctx: commands.Context):
        rows = await self._rows(ctx.guild.id)
        if not rows:
            await ctx.send(embed=error_embed("No hay reaction triggers configurados."))
            return
        lines = [f"{row['emoji']} — **{row['trigger']}**" for row in rows]
        await ctx.send(embed=base_embed(title="⚡ Reaction Triggers", description="\n".join(lines)))

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=error_embed("Uso: `,reactiontrigger add <trigger> <emoji>`"))
            return
        await ctx.send(embed=error_embed(f"Ocurrió un error: `{error}`"))


async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionTriggers(bot))
