"""
cogs/giveaways.py
-------------------
Sorteos con botón para participar.

Los participantes se guardan en la base de datos (tabla giveaway_entrants)
en vez de en memoria, así que un sorteo sigue funcionando igual si el bot
se reinicia. El botón usa un custom_id fijo y una View persistente
(registrada una sola vez en __init__ con bot.add_view), y el ID del
sorteo se obtiene del propio mensaje al que está enganchado el botón
en vez de guardarse en un diccionario en RAM.

Comandos (todos con el prefijo del bot, agrupados bajo ,giveaway):
    ,giveaway start   -> crea un sorteo (con requisito de rol opcional)
    ,giveaway end     -> lo termina antes de tiempo
    ,giveaway reroll  -> vuelve a elegir ganador(es) de un sorteo ya terminado
    ,giveaway cancel  -> lo cancela sin elegir ganador
    ,giveaway list    -> lista los sorteos del servidor
"""

import random
import time
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from database import db
from utils.embeds import base_embed, error_embed, success_embed


def parse_duration(text: str) -> int | None:
    """Convierte '10m', '2h', '1d' a segundos."""
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    text = text.strip().lower()
    if len(text) < 2 or text[-1] not in units:
        return None
    try:
        amount = int(text[:-1])
    except ValueError:
        return None
    if amount <= 0:
        return None
    return amount * units[text[-1]]


class GiveawayView(discord.ui.View):
    """View persistente (timeout=None, custom_id fijo). Una sola instancia de
    esta clase se registra en el bot y sirve para TODOS los sorteos, viejos y
    nuevos: qué sorteo es se determina leyendo el ID del mensaje al que está
    pegado el botón, no un atributo guardado en RAM."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎉 Participar", style=discord.ButtonStyle.primary, custom_id="giveaway_enter")
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        row = await db.get_giveaway(interaction.message.id)
        if row is None or row["ended"]:
            await interaction.response.send_message(embed=error_embed("Este sorteo ya no está activo."), ephemeral=True)
            return

        if row["required_role_id"]:
            role = interaction.guild.get_role(row["required_role_id"])
            if role and role not in interaction.user.roles:
                await interaction.response.send_message(
                    embed=error_embed(f"Necesitas el rol {role.mention} para participar en este sorteo."),
                    ephemeral=True,
                )
                return

        already = await db.is_giveaway_entrant(interaction.message.id, interaction.user.id)
        if already:
            await db.remove_giveaway_entrant(interaction.message.id, interaction.user.id)
            await interaction.response.send_message("Saliste del sorteo.", ephemeral=True)
        else:
            await db.add_giveaway_entrant(interaction.message.id, interaction.user.id)
            await interaction.response.send_message("¡Estás participando en el sorteo! 🎉", ephemeral=True)


class Giveaways(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.add_view(GiveawayView())  # persistente: sigue funcionando tras reiniciar el bot
        self.checker.start()

    def cog_unload(self):
        self.checker.cancel()

    @commands.group(name="giveaway", aliases=["gw"], invoke_without_command=True, help="Comandos de sorteos: start/end/cancel/reroll/list")
    async def giveaway(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @giveaway.command(name="start", help="Inicia un sorteo en este canal. Uso: ,giveaway start <duración> <ganadores> <premio...> [@rol_requerido]")
    @commands.has_permissions(manage_guild=True)
    async def giveaway_start(
        self, ctx: commands.Context, duracion: str, ganadores: commands.Range[int, 1], *, premio: str,
    ):
        rol_requerido = None
        palabras = premio.split()
        if palabras and palabras[-1].startswith("<@&") and palabras[-1].endswith(">"):
            try:
                role_id = int(palabras[-1].strip("<@&>"))
                rol_requerido = ctx.guild.get_role(role_id)
                if rol_requerido:
                    premio = " ".join(palabras[:-1]).strip()
            except ValueError:
                pass

        seconds = parse_duration(duracion)
        if seconds is None:
            await ctx.send(embed=error_embed("Duración inválida. Usa algo como `10m`, `2h` o `1d`."))
            return
        if not premio:
            await ctx.send(embed=error_embed("Indica el premio. Ej: `,giveaway start 10m 1 Nitro`"))
            return

        ends_at = int(time.time()) + seconds
        description = (
            f"**Premio:** {premio}\n**Ganadores:** {ganadores}\n"
            f"Termina: {discord.utils.format_dt(datetime.fromtimestamp(ends_at, tz=timezone.utc), style='R')}"
        )
        if rol_requerido:
            description += f"\n**Rol requerido:** {rol_requerido.mention}"

        embed = base_embed(title="🎉 ¡Sorteo!", description=description)
        embed.set_footer(text=f"Organizado por {ctx.author.display_name}")

        view = GiveawayView()
        message = await ctx.send(embed=embed, view=view)

        await db.create_giveaway(
            message.id, ctx.channel.id, ctx.guild.id,
            ctx.author.id, premio, ganadores, ends_at,
            required_role_id=rol_requerido.id if rol_requerido else None,
        )

    @giveaway.command(name="end", help="Termina un sorteo antes de tiempo. Uso: ,giveaway end <id_mensaje>")
    @commands.has_permissions(manage_guild=True)
    async def giveaway_end(self, ctx: commands.Context, mensaje_id: str):
        row = await self._resolve(ctx, mensaje_id, must_be_active=True)
        if row is None:
            return
        await ctx.send(embed=success_embed("Terminando el sorteo..."))
        await self._finish(row)

    @giveaway.command(name="cancel", help="Cancela un sorteo sin elegir ganador. Uso: ,giveaway cancel <id_mensaje>")
    @commands.has_permissions(manage_guild=True)
    async def giveaway_cancel(self, ctx: commands.Context, mensaje_id: str):
        row = await self._resolve(ctx, mensaje_id, must_be_active=True)
        if row is None:
            return

        await db.cancel_giveaway(row["message_id"])
        channel = self.bot.get_channel(row["channel_id"])
        if channel:
            try:
                message = await channel.fetch_message(row["message_id"])
                cancel_embed = base_embed(
                    title="🚫 Sorteo cancelado", description=f"El sorteo de **{row['prize']}** fue cancelado."
                )
                await message.edit(embed=cancel_embed, view=None)
            except discord.NotFound:
                pass
        await ctx.send(embed=success_embed("Sorteo cancelado."))

    @giveaway.command(name="reroll", help="Vuelve a elegir ganador(es) de un sorteo ya terminado. Uso: ,giveaway reroll <id_mensaje> [ganadores]")
    @commands.has_permissions(manage_guild=True)
    async def giveaway_reroll(self, ctx: commands.Context, mensaje_id: str, ganadores: commands.Range[int, 1] = 1):
        row = await self._resolve(ctx, mensaje_id, must_be_active=False)
        if row is None:
            return
        if not row["ended"]:
            await ctx.send(embed=error_embed(f"Ese sorteo todavía no ha terminado, usa `{ctx.prefix}giveaway end` primero."))
            return

        entrants = await db.get_giveaway_entrants(row["message_id"])
        if not entrants:
            await ctx.send(embed=error_embed("Nadie participó en ese sorteo."))
            return

        winners_count = min(ganadores, len(entrants))
        winners = random.sample(entrants, winners_count)
        mentions = ", ".join(f"<@{w}>" for w in winners)
        await db.end_giveaway(row["message_id"], winners_ids=",".join(str(w) for w in winners))

        await ctx.send(embed=success_embed(f"Nuevo(s) ganador(es): {mentions}"))
        channel = self.bot.get_channel(row["channel_id"])
        if channel:
            await channel.send(f"🎉 ¡Nuevo sorteo (reroll) de **{row['prize']}**! Felicidades {mentions}.")

    @giveaway.command(name="list", help="Lista los sorteos de este servidor")
    async def giveaway_list(self, ctx: commands.Context):
        rows = await db.get_guild_giveaways(ctx.guild.id, limit=10)
        if not rows:
            await ctx.send(embed=error_embed("No hay sorteos registrados en este servidor."))
            return

        lines = []
        for row in rows:
            estado = "✅ Terminado" if row["ended"] else "🟢 Activo"
            link = f"https://discord.com/channels/{row['guild_id']}/{row['channel_id']}/{row['message_id']}"
            lines.append(f"[{row['prize']}]({link}) — {estado} — {row['winners']} ganador(es)")

        embed = base_embed(title="🎉 Sorteos del servidor", description="\n".join(lines))
        await ctx.send(embed=embed)

    async def _resolve(self, ctx: commands.Context, mensaje_id: str, must_be_active: bool):
        try:
            msg_id = int(mensaje_id)
        except ValueError:
            await ctx.send(embed=error_embed("ID inválido."))
            return None
        row = await db.get_giveaway(msg_id)
        if row is None:
            await ctx.send(embed=error_embed("Ese sorteo no existe."))
            return None
        if must_be_active and row["ended"]:
            await ctx.send(embed=error_embed("Ese sorteo ya terminó."))
            return None
        return row

    @tasks.loop(seconds=30)
    async def checker(self):
        try:
            rows = await db.get_active_giveaways()
        except Exception:
            return
        now = int(time.time())
        for row in rows:
            if row["ends_at"] <= now:
                await self._finish(row)

    @checker.before_loop
    async def before_checker(self):
        await self.bot.wait_until_ready()

    async def _finish(self, row):
        entrants = await db.get_giveaway_entrants(row["message_id"])

        if not entrants:
            winners = []
            result_embed = base_embed(
                title="🎉 Sorteo terminado", description=f"Nadie participó en el sorteo de **{row['prize']}**."
            )
        else:
            winners_count = min(row["winners"], len(entrants))
            winners = random.sample(entrants, winners_count)
            mentions = ", ".join(f"<@{w}>" for w in winners)
            result_embed = base_embed(
                title="🎉 Sorteo terminado",
                description=f"**Premio:** {row['prize']}\n**Ganador(es):** {mentions}",
            )

        await db.end_giveaway(row["message_id"], winners_ids=",".join(str(w) for w in winners) if winners else None)

        channel = self.bot.get_channel(row["channel_id"])
        if channel is None:
            return

        if winners:
            mentions = ", ".join(f"<@{w}>" for w in winners)
            try:
                await channel.send(f"🎉 ¡Felicidades {mentions}! Ganaron **{row['prize']}**.")
            except discord.HTTPException:
                pass

        try:
            message = await channel.fetch_message(row["message_id"])
            await message.edit(embed=result_embed, view=None)
        except discord.HTTPException:
            pass

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=error_embed("Necesitas permiso de `Administrar servidor` para usar esto."))
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=error_embed(f"Falta el argumento `{error.param.name}`."))
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send(embed=error_embed("Uno de los datos que diste no es válido."))
            return


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaways(bot))
