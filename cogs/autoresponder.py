"""
cogs/autoresponder.py
----------------------
Sistema de autoresponder (como el de tu captura de bleed): permite crear
palabras/frases "trigger" que, cuando alguien las escribe, hacen que el bot
responda automáticamente. La respuesta puede ser texto o un archivo
adjunto (imagen/gif), igual que en tu captura de "madrid".

Uso (comandos con prefijo, ej. si tu PREFIX es ","):
    ,autoresponder add <trigger> <respuesta...>            -> coincidencia exacta (strict)
    ,autoresponder add <trigger> [+ adjunto, sin texto]     -> también funciona con solo un gif/imagen
    ,autoresponder add-contains <trigger> <respuesta...>    -> coincidencia parcial
    ,autoresponder edit <trigger> <nueva respuesta...>      -> FASE 2: cambia solo la respuesta
    ,autoresponder enable <trigger>                         -> FASE 2
    ,autoresponder disable <trigger>                        -> FASE 2
    ,autoresponder channel <trigger> #canal|ninguno         -> FASE 2: limita a un canal (o quita el límite)
    ,autoresponder remove <trigger>
    ,autoresponder list
"""

import discord
from discord.ext import commands

from database import db
from utils.checks import is_staff
from utils.embeds import base_embed, error_embed, success_embed


class AutoResponder(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._cache: dict[int, list] = {}

    async def _rows(self, guild_id: int):
        if guild_id not in self._cache:
            self._cache[guild_id] = await db.get_autoresponders(guild_id)
        return self._cache[guild_id]

    def _invalidate(self, guild_id: int):
        self._cache.pop(guild_id, None)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        content = message.content.strip()
        if not content:
            return

        rows = await self._rows(message.guild.id)
        lowered = content.lower()

        for row in rows:
            if not row["enabled"]:
                continue
            if row["channel_id"] and message.channel.id != row["channel_id"]:
                continue
            if row["match_type"] == "strict":
                if lowered == row["trigger"]:
                    await message.channel.send(row["response"])
                    return
            else:
                if row["trigger"] in lowered:
                    await message.channel.send(row["response"])
                    return

    @commands.group(name="autoresponder", aliases=["ar"], invoke_without_command=True)
    async def autoresponder(self, ctx: commands.Context):
        await self.list_autoresponders(ctx)

    @autoresponder.command(name="add")
    async def add_strict(self, ctx: commands.Context, trigger: str, *, respuesta: str = None):
        """Crea un autoresponder de coincidencia exacta (strict match)."""
        await self._add(ctx, trigger, respuesta, "strict")

    @autoresponder.command(name="add-contains", aliases=["addcontains"])
    async def add_contains(self, ctx: commands.Context, trigger: str, *, respuesta: str = None):
        """Crea un autoresponder que dispara si el mensaje CONTIENE el trigger."""
        await self._add(ctx, trigger, respuesta, "contains")

    async def _add(self, ctx: commands.Context, trigger: str, respuesta: str | None, match_type: str):
        if not is_staff(ctx.author):
            await ctx.send(embed=error_embed("Necesitas permiso de `Administrar servidor` para usar esto."))
            return

        # El trigger puede llegar con una coma pegada (",autoresponder add madrid,") -> la quitamos.
        trigger = trigger.strip().rstrip(",")

        # Si no escribieron texto de respuesta, usamos el primer adjunto (imagen/gif) como respuesta.
        if not respuesta and ctx.message.attachments:
            respuesta = ctx.message.attachments[0].url

        if not trigger:
            await ctx.send(embed=error_embed("Tienes que indicar un trigger. Ej: `,autoresponder add hola Hola!`"))
            return
        if not respuesta:
            await ctx.send(
                embed=error_embed(
                    "Tienes que darle una respuesta: escribe texto después del trigger, "
                    "o adjunta una imagen/gif en el mismo mensaje."
                )
            )
            return
        if len(trigger) > 100 or len(respuesta) > 1800:
            await ctx.send(embed=error_embed("El trigger o la respuesta son demasiado largos."))
            return

        await db.add_autoresponder(ctx.guild.id, trigger, respuesta, match_type, ctx.author.id)
        self._invalidate(ctx.guild.id)

        modo = "exacta" if match_type == "strict" else "parcial (contains)"
        await ctx.send(
            embed=success_embed(
                f"Autoresponder **{trigger}** creado con coincidencia {modo}.",
                title="✅ Autoresponder creado",
            )
        )

    @autoresponder.command(name="edit")
    async def edit(self, ctx: commands.Context, trigger: str, *, nueva_respuesta: str = None):
        """FASE 2: cambia solo el texto de respuesta de un autoresponder ya creado."""
        if not is_staff(ctx.author):
            await ctx.send(embed=error_embed("Necesitas permiso de `Administrar servidor` para usar esto."))
            return

        trigger = trigger.strip().rstrip(",")
        if not nueva_respuesta and ctx.message.attachments:
            nueva_respuesta = ctx.message.attachments[0].url
        if not nueva_respuesta:
            await ctx.send(embed=error_embed("Tienes que dar la nueva respuesta (texto o adjunto)."))
            return
        if len(nueva_respuesta) > 1800:
            await ctx.send(embed=error_embed("La respuesta es demasiado larga."))
            return

        ok = await db.edit_autoresponder_response(ctx.guild.id, trigger, nueva_respuesta)
        self._invalidate(ctx.guild.id)
        if ok:
            await ctx.send(embed=success_embed(f"Autoresponder **{trigger}** actualizado."))
        else:
            await ctx.send(embed=error_embed("No encontré ningún autoresponder con ese trigger."))

    @autoresponder.command(name="enable", aliases=["activar", "on"])
    async def enable(self, ctx: commands.Context, trigger: str):
        """FASE 2: reactiva un autoresponder desactivado."""
        await self._set_enabled(ctx, trigger, True)

    @autoresponder.command(name="disable", aliases=["desactivar", "off"])
    async def disable(self, ctx: commands.Context, trigger: str):
        """FASE 2: desactiva un autoresponder sin borrarlo."""
        await self._set_enabled(ctx, trigger, False)

    async def _set_enabled(self, ctx: commands.Context, trigger: str, enabled: bool):
        if not is_staff(ctx.author):
            await ctx.send(embed=error_embed("Necesitas permiso de `Administrar servidor` para usar esto."))
            return
        ok = await db.set_autoresponder_enabled(ctx.guild.id, trigger, enabled)
        self._invalidate(ctx.guild.id)
        if ok:
            estado = "activado" if enabled else "desactivado"
            await ctx.send(embed=success_embed(f"Autoresponder **{trigger}** {estado}."))
        else:
            await ctx.send(embed=error_embed("No encontré ningún autoresponder con ese trigger."))

    @autoresponder.command(name="channel", aliases=["canal"])
    async def channel(self, ctx: commands.Context, trigger: str, canal: discord.TextChannel = None):
        """FASE 2: limita el autoresponder a un canal (o quita el límite si no das canal)."""
        if not is_staff(ctx.author):
            await ctx.send(embed=error_embed("Necesitas permiso de `Administrar servidor` para usar esto."))
            return
        ok = await db.set_autoresponder_channel(ctx.guild.id, trigger, canal.id if canal else None)
        self._invalidate(ctx.guild.id)
        if not ok:
            await ctx.send(embed=error_embed("No encontré ningún autoresponder con ese trigger."))
            return
        if canal:
            await ctx.send(embed=success_embed(f"Autoresponder **{trigger}** limitado a {canal.mention}."))
        else:
            await ctx.send(embed=success_embed(f"Autoresponder **{trigger}** ya no está limitado a ningún canal."))

    @autoresponder.command(name="remove", aliases=["delete", "del"])
    async def remove(self, ctx: commands.Context, trigger: str):
        if not is_staff(ctx.author):
            await ctx.send(embed=error_embed("Necesitas permiso de `Administrar servidor` para usar esto."))
            return
        ok = await db.remove_autoresponder(ctx.guild.id, trigger)
        self._invalidate(ctx.guild.id)
        if ok:
            await ctx.send(embed=success_embed(f"Autoresponder **{trigger}** eliminado."))
        else:
            await ctx.send(embed=error_embed("No encontré ningún autoresponder con ese trigger."))

    @autoresponder.command(name="list")
    async def list_autoresponders(self, ctx: commands.Context):
        rows = await self._rows(ctx.guild.id)
        if not rows:
            await ctx.send(embed=error_embed("Este servidor no tiene autoresponders configurados."))
            return

        lines = []
        for row in rows:
            tag = "🔒 exacta" if row["match_type"] == "strict" else "🔎 parcial"
            estado = "🟢" if row["enabled"] else "🔴"
            canal = f" — <#{row['channel_id']}>" if row["channel_id"] else ""
            lines.append(f"{estado} **{row['trigger']}** — {tag}{canal}")

        embed = base_embed(title="🤖 Autoresponders del servidor", description="\n".join(lines))
        await ctx.send(embed=embed)

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """Evita que errores de argumentos (o cualquier otro) tumben al bot con un traceback feo."""
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == "trigger":
                await ctx.send(
                    embed=error_embed(
                        "Falta el trigger. Ej: `,autoresponder add hola Hola!` o adjunta un gif/imagen "
                        "en el mismo mensaje después de poner el trigger."
                    )
                )
            else:
                await ctx.send(embed=error_embed("Faltan datos para ese comando."))
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send(embed=error_embed("Uno de los datos que diste no es válido."))
            return
        # Cualquier otro error: lo mostramos de forma controlada en vez de crashear.
        await ctx.send(embed=error_embed(f"Ocurrió un error inesperado: `{error}`"))


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoResponder(bot))
