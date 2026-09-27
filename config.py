"""
config.py
---------
Carga toda la configuración del bot desde el archivo .env
Cualquier otro archivo del proyecto importa sus ajustes desde aquí,
así nunca hay valores "hardcodeados" repartidos por el código.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


class Config:
    # --- Credenciales / identidad ---
    TOKEN: str = os.getenv("DISCORD_TOKEN", "")
    DEV_GUILD_ID: int | None = int(os.getenv("DEV_GUILD_ID")) if os.getenv("DEV_GUILD_ID") else None

    # --- Comportamiento general ---
    PREFIX: str = os.getenv("PREFIX", ",")

    # --- Economía ---
    CURRENCY_NAME: str = os.getenv("CURRENCY_NAME", "Diamantes")
    CURRENCY_EMOJI: str = os.getenv("CURRENCY_EMOJI", "💎")
    STARTING_BALANCE: int = _get_int("STARTING_BALANCE", 1000)
    DAILY_AMOUNT: int = _get_int("DAILY_AMOUNT", 250)

    # --- Trabajo / robo ---
    WORK_MIN: int = _get_int("WORK_MIN", 50)
    WORK_MAX: int = _get_int("WORK_MAX", 300)
    WORK_COOLDOWN: int = _get_int("WORK_COOLDOWN", 60 * 30)  # 30 min
    ROB_COOLDOWN: int = _get_int("ROB_COOLDOWN", 60 * 60)    # 1 hora
    ROB_SUCCESS_RATE: float = 0.45

    # --- Rutas ---
    DB_PATH: str = os.path.join("data", "bot.sqlite3")

    # --- Colores de embeds (tema morado en toda la interfaz) ---
    COLOR_DEFAULT: int = 0x9B59B6   # morado principal, usado por defecto en todos los embeds
    COLOR_PRIMARY: int = 0x9B59B6
    COLOR_SHOP: int = 0x8E44AD      # morado un poco más oscuro para la tienda
    COLOR_SUCCESS: int = 0x57F287
    COLOR_DANGER: int = 0xED4245
    COLOR_INFO: int = 0xA569BD
    COLOR_WARNING: int = 0xFEE75C


config = Config()
