"""
cogs/autoroles.py
------------------
Le da automáticamente un rol fijo a cualquier miembro nuevo que se une.

Comando: ,autorole @rol
"""

import discord
from discord.ext import commands

from database import db
from utils.embeds import error_embed, success_embed


class AutoRoles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="autorole", help="Define el rol que reciben los miembros nuevos. Uso: ,autorole @rol")
    @commands.has_permissions(manage_roles=True)
    async def config_autorole(self, ctx: commands.Context, *, rol: discord.Role):
        await db.set_guild_field(ctx.guild.id, "autorole_id", rol.id)
        await ctx.send(embed=success_embed(f"Los nuevos miembros recibirán el rol {rol.mention}."))

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = await db.get_guild_config(member.guild.id)
        role_id = cfg["autorole_id"]
        if not role_id:
            return
        role = member.guild.get_role(role_id)
        if role:
            try:
                await member.add_roles(role, reason="Autorole")
            except discord.HTTPException:
                pass

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=error_embed("Necesitas permiso de `Gestionar roles` para usar esto."))
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=error_embed(f"Falta el argumento `{error.param.name}`."))
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send(embed=error_embed("No encontré ese rol."))
            return


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoRoles(bot))
