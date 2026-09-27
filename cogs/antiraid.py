import time
from collections import deque

import discord
from discord.ext import commands

from database import db
from utils.embeds import error_embed, success_embed, base_embed


class AntiRaid(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.recent_joins: dict[int, deque] = {}

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = await db.get_antiraid_config(member.guild.id)
        if not cfg["enabled"]:
            return

        now = time.time()
        account_age_hours = (now - member.created_at.timestamp()) / 3600

        if account_age_hours < cfg["min_age_hours"]:
            await self._take_action(member, cfg, "cuenta demasiado nueva")
            return

        joins = self.recent_joins.setdefault(member.guild.id, deque())
        joins.append(now)
        window = cfg["join_window"]
        while joins and now - joins[0] > window:
            joins.popleft()

        if len(joins) >= cfg["join_burst"]:
            await self._alert_burst(member.guild, cfg)

    async def _take_action(self, member: discord.Member, cfg, reason: str):
        action = cfg["action"]
        try:
            if action == "kick":
                await member.kick(reason=f"Anti-raid: {reason}")
            elif action == "ban":
                await member.ban(reason=f"Anti-raid: {reason}")
        except discord.Forbidden:
            pass

    async def _alert_burst(self, guild: discord.Guild, cfg):
        guild_config = await db.get_guild_config(guild.id)
        channel = guild.get_channel(guild_config["log_channel_id"]) if guild_config["log_channel_id"] else None
        if channel is None:
            channel = guild.system_channel
        if channel:
            try:
                await channel.send(
                    embed=base_embed(
                        title="🚨 Posible raid detectado",
                        description=f"Se detectaron {cfg['join_burst']}+ entradas en {cfg['join_window']}s. "
                        f"Considera activar el modo de verificación alto del servidor.",
                    )
                )
            except discord.HTTPException:
                pass

    @commands.group(
        name="antiraid",
        invoke_without_command=True,
        help="[Admin] Muestra la configuración de protección anti-raid",
    )
    @commands.has_permissions(administrator=True)
    async def antiraid(self, ctx: commands.Context):
        await self._show_config(ctx)

    @antiraid.command(name="status", help="[Admin] Muestra la configuración de protección anti-raid")
    @commands.has_permissions(administrator=True)
    async def antiraid_status(self, ctx: commands.Context):
        await self._show_config(ctx)

    @antiraid.command(name="enable", help="[Admin] Activa la protección anti-raid")
    @commands.has_permissions(administrator=True)
    async def antiraid_enable(self, ctx: commands.Context):
        await db.set_antiraid_field(ctx.guild.id, "enabled", 1)
        await self._show_config(ctx)

    @antiraid.command(name="disable", help="[Admin] Desactiva la protección anti-raid")
    @commands.has_permissions(administrator=True)
    async def antiraid_disable(self, ctx: commands.Context):
        await db.set_antiraid_field(ctx.guild.id, "enabled", 0)
        await self._show_config(ctx)

    @antiraid.command(
        name="config",
        help=(
            "[Admin] Configura umbrales anti-raid. Uso: "
            ",antiraid config <edad_minima_horas> <entradas_sospechosas> <ventana_segundos> <kick|ban|none>"
        ),
    )
    @commands.has_permissions(administrator=True)
    async def antiraid_config(
        self,
        ctx: commands.Context,
        edad_minima_horas: commands.Range[int, 0],
        entradas_sospechosas: commands.Range[int, 2],
        ventana_segundos: commands.Range[int, 5],
        accion: str,
    ):
        accion = accion.lower()
        if accion not in ("kick", "ban", "none"):
            await ctx.send(embed=error_embed("La acción debe ser `kick`, `ban` o `none`."))
            return

        await db.set_antiraid_field(ctx.guild.id, "min_age_hours", edad_minima_horas)
        await db.set_antiraid_field(ctx.guild.id, "join_burst", entradas_sospechosas)
        await db.set_antiraid_field(ctx.guild.id, "join_window", ventana_segundos)
        await db.set_antiraid_field(ctx.guild.id, "action", accion)
        await self._show_config(ctx)

    async def _show_config(self, ctx: commands.Context):
        cfg = await db.get_antiraid_config(ctx.guild.id)
        embed = base_embed(title="🛡️ Configuración anti-raid")
        embed.add_field(name="Activo", value="✅" if cfg["enabled"] else "❌")
        embed.add_field(name="Edad mínima", value=f"{cfg['min_age_hours']}h")
        embed.add_field(name="Umbral de raid", value=f"{cfg['join_burst']} entradas / {cfg['join_window']}s")
        embed.add_field(name="Acción", value=cfg["action"])
        await ctx.send(embed=embed)

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=error_embed("Necesitas permiso de `Administrador` para usar esto."))
            return


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiRaid(bot))
