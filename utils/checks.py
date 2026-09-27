"""
utils/checks.py
----------------
Pequeñas funciones de permisos reutilizadas por varios cogs
(moderación, tickets, voicemaster, etc).
"""

import discord


def is_staff(member: discord.Member) -> bool:
    """True si el miembro puede administrar el servidor o el canal (moderador/admin)."""
    perms = member.guild_permissions
    return perms.administrator or perms.manage_guild or perms.manage_channels
