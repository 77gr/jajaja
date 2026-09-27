"""
cogs/general.py
----------------
Comandos generales: ,ping para revisar latencia y ,help con un resumen
de todo lo que el bot puede hacer (todo con el prefijo del bot).
"""

import platform

import discord
from discord.ext import commands

from config import config
from utils.embeds import base_embed


def _format_timedelta(delta) -> str:
    total = int(delta.total_seconds())
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


class General(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="ping", help="Muestra la latencia del bot")
    async def ping(self, ctx: commands.Context):
        await ctx.send(f"🏓 Pong! `{round(self.bot.latency * 1000)}ms`")

    @commands.command(name="uptime", help="Muestra cuánto tiempo lleva encendido el bot")
    async def uptime(self, ctx: commands.Context):
        delta = discord.utils.utcnow() - self.bot.start_time
        await ctx.send(embed=base_embed(title="⏱️ Uptime", description=f"Llevo encendido **{_format_timedelta(delta)}**."))

    @commands.command(name="stats", help="Muestra estadísticas generales del bot")
    async def stats(self, ctx: commands.Context):
        delta = discord.utils.utcnow() - self.bot.start_time
        total_members = sum(g.member_count or 0 for g in self.bot.guilds)
        embed = base_embed(title="📊 Estadísticas del bot")
        embed.add_field(name="Servidores", value=str(len(self.bot.guilds)))
        embed.add_field(name="Usuarios (aprox.)", value=str(total_members))
        embed.add_field(name="Latencia", value=f"{round(self.bot.latency * 1000)}ms")
        embed.add_field(name="Uptime", value=_format_timedelta(delta))
        embed.add_field(name="discord.py", value=discord.__version__)
        embed.add_field(name="Python", value=platform.python_version())
        await ctx.send(embed=embed)

    @commands.command(name="help", help="Muestra todos los comandos disponibles")
    async def help_command(self, ctx: commands.Context):
        p = config.PREFIX
        embed = base_embed(title="📖 Comandos disponibles")
        embed.add_field(
            name="💰 Economía",
            value=f"`{p}balance` `{p}daily` `{p}pay` `{p}leaderboard` `{p}work` `{p}rob`",
            inline=False,
        )
        embed.add_field(
            name="🎮 Minijuegos",
            value=f"`{p}mines` `{p}chicken` `{p}chickenfight` `{p}slots` `{p}coinflip` `{p}tictactoe`",
            inline=False,
        )
        embed.add_field(
            name="🛍️ Tienda",
            value=f"`{p}shop` `{p}buy` `{p}inventory` `{p}shop add` `{p}shop remove`",
            inline=False,
        )
        embed.add_field(
            name="📊 Niveles",
            value=f"`{p}rank` `{p}leveltop` `{p}setlevel` `{p}setxp` "
            f"`{p}levels lock/unlock/list/add/remove/roles/sync/stackroles/setrate/messagemode/message/leaderboard`",
            inline=False,
        )
        embed.add_field(
            name="🎧 VoiceMaster",
            value=f"`{p}voicemaster setup`",
            inline=False,
        )
        embed.add_field(
            name="🛡️ Moderación y seguridad",
            value=f"`{p}kick` `{p}ban` `{p}unban` `{p}timeout` `{p}warn` `{p}warnings` `{p}clear` `{p}slowmode` "
            f"`{p}lock` `{p}unlock` `{p}jail` `{p}unjail` `{p}antiraid` "
            f"`{p}automod setup/enable/disable/config/whitelist/blacklist`",
            inline=False,
        )
        embed.add_field(
            name="🤖 Automatización",
            value=f"`{p}autoresponder add/add-contains/edit/enable/disable/channel/remove/list` "
            f"`{p}reactiontrigger add/remove/list` "
            f"`{p}giveaway start/end/reroll/cancel/list` "
            f"`{p}bump-channel` `{p}counter setup/remove`",
            inline=False,
        )
        embed.add_field(
            name="🔔 Recordatorios",
            value=f"`{p}remind` `{p}reminders` `{p}reminder-delete`",
            inline=False,
        )
        embed.add_field(
            name="🎯 Snipe / Memes",
            value=f"`{p}snipe` `{p}editsnipe` `{p}caption <texto>`",
            inline=False,
        )
        embed.add_field(
            name="🙂 Social / Utilidad",
            value=f"`{p}avatar` `{p}userinfo` `{p}serverinfo` `{p}roleinfo` `{p}channelinfo` `{p}8ball` "
            f"`{p}uptime` `{p}stats` "
            f"`{p}ticket setup` `{p}reactionrole add/remove/list` "
            f"`{p}sticky set/remove` "
            f"`{p}welcome set/enable/disable/test` `{p}goodbye set/enable/disable/test` "
            f"`{p}autorole` `{p}logs setup`",
            inline=False,
        )
        embed.set_footer(text=f"Prefijo del bot: {p}  ·  Moneda del servidor: {config.CURRENCY_NAME} {config.CURRENCY_EMOJI}")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(General(bot))
