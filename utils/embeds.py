"""
utils/embeds.py
----------------
Helpers para construir embeds consistentes (mismo estilo de tarjeta oscura
en todo el bot, como en Mines/Chicken de tus capturas).
"""

import discord
from config import config


def base_embed(title: str | None = None, description: str | None = None,
                color: int = config.COLOR_DEFAULT) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    return embed


def success_embed(description: str, title: str | None = None) -> discord.Embed:
    return base_embed(title=title, description=description, color=config.COLOR_SUCCESS)


def error_embed(description: str, title: str | None = "Error") -> discord.Embed:
    return base_embed(title=title, description=description, color=config.COLOR_DANGER)


def info_embed(description: str, title: str | None = None) -> discord.Embed:
    return base_embed(title=title, description=description, color=config.COLOR_INFO)


def money(amount: int) -> str:
    return f"{amount:,} {config.CURRENCY_EMOJI}".replace(",", ".")
