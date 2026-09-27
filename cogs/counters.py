"""
cogs/counters.py
------------------
Counters: crea canales de voz "de solo lectura" cuyo nombre muestra una
estadística del servidor (miembros, bots) y se actualiza solo cada
cierto tiempo (Discord limita los renombres a 2 cada 10 minutos).

Uso:
    ,counter setup <members|bots|voice>
    ,counter remove <members|bots|voice>
"""

import discord
from discord.ext import commands, tasks

from database import db
from utils.embeds import error_embed, success_embed

KINDS = {
    "members": "👥 Miembros: {count}",
    "bots": "🤖 Bots: {count}",
    "voice": "🎤 En voz: {count}",
}


class Counters(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.updater.start()

    def cog_unload(self):
        self.updater.cancel()

    @commands.group(name="counter", invoke_without_command=True, help="Gestiona los canales contador del servidor")
    async def counter(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @counter.command(name="setup", help="[Admin] Crea un canal contador. Uso: ,counter setup <members|bots|voice>")
    @commands.has_permissions(manage_guild=True)
    async def counter_setup(self, ctx: commands.Context, tipo: str):
        tipo = tipo.lower()
        if tipo not in KINDS:
            await ctx.send(embed=error_embed(f"Tipo inválido. Usa uno de: {', '.join(KINDS)}"))
            return
        template = KINDS[tipo]
        count = self._count(ctx.guild, tipo)
        channel = await ctx.guild.create_voice_channel(
            name=template.format(count=count),
            reason="Counter creado por comando de administración",
        )
        try:
            await channel.set_permissions(ctx.guild.default_role, connect=False)
        except discord.Forbidden:
            pass

        await db.set_counter(ctx.guild.id, channel.id, tipo, template)
        await ctx.send(embed=success_embed(f"Contador creado: {channel.mention}"))

    @counter.command(name="remove", help="[Admin] Elimina un contador. Uso: ,counter remove <members|bots|voice>")
    @commands.has_permissions(manage_guild=True)
    async def counter_remove(self, ctx: commands.Context, tipo: str):
        tipo = tipo.lower()
        if tipo not in KINDS:
            await ctx.send(embed=error_embed(f"Tipo inválido. Usa uno de: {', '.join(KINDS)}"))
            return
        ok = await db.remove_counter(ctx.guild.id, tipo)
        if ok:
            await ctx.send(embed=success_embed("Contador eliminado (borra el canal manualmente si quieres)."))
        else:
            await ctx.send(embed=error_embed("No tenías ese contador configurado."))

    def _count(self, guild: discord.Guild, kind: str) -> int:
        if kind == "members":
            return guild.member_count
        if kind == "bots":
            return sum(1 for m in guild.members if m.bot)
        if kind == "voice":
            return sum(len(vc.members) for vc in guild.voice_channels)
        return 0

    @tasks.loop(minutes=10)
    async def updater(self):
        for guild in self.bot.guilds:
            try:
                rows = await db.get_counters(guild.id)
            except Exception:
                continue
            for row in rows:
                channel = guild.get_channel(row["channel_id"])
                if channel is None:
                    continue
                count = self._count(guild, row["kind"])
                new_name = row["template"].format(count=count)
                if channel.name != new_name:
                    try:
                        await channel.edit(name=new_name)
                    except discord.HTTPException:
                        pass

    @updater.before_loop
    async def before_updater(self):
        await self.bot.wait_until_ready()

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=error_embed("Necesitas permiso de `Administrar servidor` para usar esto."))
            return


async def setup(bot: commands.Bot):
    await bot.add_cog(Counters(bot))
