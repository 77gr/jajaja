"""
main.py
-------
Punto de entrada. Ejecuta esto con:  python main.py

Se encarga de:
1. Crear el bot con los intents necesarios.
2. Conectar la base de datos SQLite.
3. Cargar todos los cogs de la carpeta /cogs.
4. Sincronizar los slash commands.
"""

import asyncio
import logging
import os

import discord
from discord.ext import commands

from config import config
from database import db

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bot")

INTENTS = discord.Intents.default()
INTENTS.members = True          # necesario para bienvenidas, autoroles, niveles por miembro
INTENTS.message_content = True  # necesario para comandos con prefijo y sticky messages
INTENTS.voice_states = True     # necesario para el VoiceMaster


class DiscordBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or(config.PREFIX),
            intents=INTENTS,
            help_command=None,
        )
        self.start_time = discord.utils.utcnow()

    async def setup_hook(self):
        await db.connect()
        log.info("Base de datos conectada en %s", config.DB_PATH)

        cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")
        for filename in sorted(os.listdir(cogs_dir)):
            if filename.endswith(".py") and not filename.startswith("_"):
                extension = f"cogs.{filename[:-3]}"
                try:
                    await self.load_extension(extension)
                    log.info("Cog cargado: %s", extension)
                except Exception:
                    log.exception("No se pudo cargar el cog %s", extension)

        # El bot ya NO usa slash commands (/): todos los comandos ahora se
        # registran con el prefijo configurado en config.PREFIX (por defecto ",").
        # Igualmente sincronizamos el árbol de comandos de aplicación (vacío)
        # para que Discord retire cualquier slash command que haya quedado
        # registrado de una versión anterior del bot.
        if config.DEV_GUILD_ID:
            guild = discord.Object(id=config.DEV_GUILD_ID)
            self.tree.clear_commands(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Slash commands limpiados en el servidor de desarrollo (%d restantes)", len(synced))
        else:
            self.tree.clear_commands(guild=None)
            synced = await self.tree.sync()
            log.info("Slash commands limpiados globalmente (%d restantes)", len(synced))

    async def close(self):
        await db.close()
        await super().close()


bot = DiscordBot()


@bot.event
async def on_ready():
    log.info("Conectado como %s (ID: %s)", bot.user, bot.user.id)
    log.info("En %d servidores", len(bot.guilds))
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching, name=f"{config.PREFIX}help · minijuegos"
        )
    )


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    # Los cogs que necesitan un mensaje de error específico definen su propio
    # cog_command_error (se ejecuta antes que este). Este handler global solo
    # evita que errores comunes (o no manejados) tumben al bot con un traceback.
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(f"⚠️ Te falta el permiso: `{', '.join(error.missing_permissions)}`.")
        return
    if isinstance(error, commands.BotMissingPermissions):
        await ctx.send(f"⚠️ Me falta el permiso: `{', '.join(error.missing_permissions)}`.")
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"⚠️ Falta el argumento `{error.param.name}`. Usa `{config.PREFIX}help` para ver el uso.")
        return
    if isinstance(error, (commands.BadArgument, commands.BadUnionArgument)):
        await ctx.send("⚠️ Uno de los datos que diste no es válido.")
        return
    if isinstance(error, commands.CheckFailure):
        return
    log.exception("Error no manejado en el comando %s", ctx.command, exc_info=error)


async def main():
    if not config.TOKEN:
        raise SystemExit(
            "Falta DISCORD_TOKEN. Copia .env.example como .env y pega tu token del bot ahí."
        )
    async with bot:
        await bot.start(config.TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
