"""
cogs/utility.py
----------------
Comandos de utilidad y social que le dan más vida al bot: ,avatar,
,userinfo, ,serverinfo y ,8ball.
"""

import random

import discord
from discord.ext import commands

from utils.embeds import base_embed

EIGHT_BALL_ANSWERS = [
    "Sí, sin duda.", "Es cierto.", "Sin duda alguna.", "Confía en ello.",
    "Como yo lo veo, sí.", "Probablemente.", "Las perspectivas son buenas.",
    "Las señales apuntan a que sí.", "Respuesta confusa, intenta de nuevo.",
    "Pregunta de nuevo más tarde.", "Mejor no te digo ahora.",
    "No puedo predecirlo ahora.", "Concéntrate y pregunta de nuevo.",
    "No cuentes con ello.", "Mi respuesta es no.", "Mis fuentes dicen que no.",
    "Las perspectivas no son buenas.", "Muy dudoso.",
]


class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="avatar", help="Muestra el avatar de un usuario")
    async def avatar(self, ctx: commands.Context, usuario: discord.Member | None = None):
        target = usuario or ctx.author
        embed = base_embed(title=f"🖼️ Avatar de {target.display_name}")
        embed.set_image(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="userinfo", help="Muestra información de un usuario")
    async def userinfo(self, ctx: commands.Context, usuario: discord.Member | None = None):
        target = usuario or ctx.author
        embed = base_embed(title=f"👤 {target.display_name}")
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Usuario", value=str(target))
        embed.add_field(name="ID", value=str(target.id))
        embed.add_field(
            name="Cuenta creada",
            value=discord.utils.format_dt(target.created_at, style="R"),
        )
        if isinstance(target, discord.Member) and target.joined_at:
            embed.add_field(
                name="Se unió al servidor",
                value=discord.utils.format_dt(target.joined_at, style="R"),
            )
            roles = [r.mention for r in target.roles if r.name != "@everyone"]
            embed.add_field(
                name=f"Roles ({len(roles)})",
                value=" ".join(roles) if roles else "Ninguno",
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.command(name="serverinfo", help="Muestra información del servidor")
    async def serverinfo(self, ctx: commands.Context):
        guild = ctx.guild
        embed = base_embed(title=f"🏰 {guild.name}")
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Dueño", value=f"<@{guild.owner_id}>")
        embed.add_field(name="Miembros", value=str(guild.member_count))
        embed.add_field(name="Roles", value=str(len(guild.roles)))
        embed.add_field(name="Canales de texto", value=str(len(guild.text_channels)))
        embed.add_field(name="Canales de voz", value=str(len(guild.voice_channels)))
        embed.add_field(
            name="Creado",
            value=discord.utils.format_dt(guild.created_at, style="R"),
        )
        await ctx.send(embed=embed)

    @commands.command(name="roleinfo", help="Muestra información de un rol")
    async def roleinfo(self, ctx: commands.Context, *, rol: discord.Role):
        embed = base_embed(title=f"🎭 {rol.name}")
        embed.color = rol.color if rol.color.value else embed.color
        embed.add_field(name="ID", value=str(rol.id))
        embed.add_field(name="Color", value=str(rol.color))
        embed.add_field(name="Posición", value=str(rol.position))
        embed.add_field(name="Miembros", value=str(len(rol.members)))
        embed.add_field(name="Mencionable", value="Sí" if rol.mentionable else "No")
        embed.add_field(name="Mostrado por separado", value="Sí" if rol.hoist else "No")
        embed.add_field(name="Gestionado por una integración", value="Sí" if rol.managed else "No")
        embed.add_field(
            name="Creado",
            value=discord.utils.format_dt(rol.created_at, style="R"),
        )
        await ctx.send(embed=embed)

    @commands.command(name="channelinfo", help="Muestra información de un canal (por defecto, este mismo)")
    async def channelinfo(
        self,
        ctx: commands.Context,
        canal: discord.TextChannel | discord.VoiceChannel | discord.CategoryChannel | None = None,
    ):
        target = canal or ctx.channel
        tipo = {
            discord.ChannelType.text: "Texto",
            discord.ChannelType.voice: "Voz",
            discord.ChannelType.category: "Categoría",
            discord.ChannelType.news: "Anuncios",
            discord.ChannelType.forum: "Foro",
            discord.ChannelType.stage_voice: "Escenario",
        }.get(target.type, str(target.type))

        embed = base_embed(title=f"📄 #{target.name}" if hasattr(target, "name") else "📄 Canal")
        embed.add_field(name="ID", value=str(target.id))
        embed.add_field(name="Tipo", value=tipo)
        embed.add_field(name="Posición", value=str(getattr(target, "position", "—")))
        if target.category:
            embed.add_field(name="Categoría", value=target.category.name)
        if isinstance(target, discord.TextChannel):
            embed.add_field(name="Tema", value=target.topic or "Sin tema", inline=False)
            embed.add_field(name="Modo lento", value=f"{target.slowmode_delay}s")
            embed.add_field(name="NSFW", value="Sí" if target.nsfw else "No")
        if isinstance(target, discord.VoiceChannel):
            embed.add_field(name="Límite de usuarios", value=str(target.user_limit or "Sin límite"))
            embed.add_field(name="Bitrate", value=f"{target.bitrate // 1000}kbps")
        embed.add_field(
            name="Creado",
            value=discord.utils.format_dt(target.created_at, style="R"),
        )
        await ctx.send(embed=embed)

    @commands.command(name="8ball", help="Hazle una pregunta a la bola 8")
    async def eight_ball(self, ctx: commands.Context, *, pregunta: str):
        embed = base_embed(title="🎱 Bola 8 mágica")
        embed.add_field(name="Pregunta", value=pregunta, inline=False)
        embed.add_field(name="Respuesta", value=random.choice(EIGHT_BALL_ANSWERS), inline=False)
        await ctx.send(embed=embed)

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"⚠️ Falta el argumento `{error.param.name}`.")
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send("⚠️ Uno de los datos que diste no es válido.")
            return


async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
