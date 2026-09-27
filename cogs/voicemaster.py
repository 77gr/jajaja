"""
cogs/voicemaster.py
--------------------
Sistema de "canal de voz para crear canales" (como en tu tercera captura):

- ,voicemaster setup crea una categoría, un canal "➕ Crear canal" y publica
  un panel con botones para administrar el canal de voz propio.
- Cuando alguien se une al canal "➕ Crear canal", el bot le crea un canal
  de voz temporal, lo mueve ahí y lo marca como dueño.
- El panel permite: Lock, Unlock, Ghost, Reveal, Claim, Desconectar,
  Iniciar actividad, Ver info, subir/bajar el límite de usuarios.
- El canal temporal se borra solo cuando se queda vacío.
"""

import discord
from discord.ext import commands

from database import db
from utils.checks import is_staff
from utils.embeds import base_embed, error_embed, success_embed

PANEL_TITLE = "🎧 VoiceMaster · Interfaz"
PANEL_DESCRIPTION = (
    "Usa los botones de abajo para controlar tu canal de voz.\n\n"
    "🔒 **Lock** — bloquea el canal\n"
    "🔓 **Unlock** — desbloquea el canal\n"
    "👻 **Ghost** — oculta el canal\n"
    "👁️ **Reveal** — muestra el canal\n"
    "🎙️ **Claim** — reclama el canal si el dueño se fue\n"
    "🔌 **Desconectar** — expulsa a alguien de tu canal\n"
    "🎮 **Actividad** — inicia una actividad de Discord\n"
    "ℹ️ **Info** — muestra información del canal\n"
    "➕ / ➖ — sube o baja el límite de usuarios"
)

# Algunas actividades integradas de Discord (application IDs públicos de Discord).
ACTIVITIES = {
    "Watch Together": "880218394199220334",
    "Poker Night": "755827207812677713",
    "Chess in the Park": "832012774040141894",
    "Sketch Heads": "902271654783242291",
    "Land-io": "903769130790969345",
}


async def get_member_voice_channel(bot: commands.Bot, interaction: discord.Interaction):
    """Devuelve el canal de voz del usuario si es un canal creado por VoiceMaster."""
    member = interaction.user
    if not isinstance(member, discord.Member) or member.voice is None or member.voice.channel is None:
        return None
    channel = member.voice.channel
    row = await db.get_voice_channel(channel.id)
    if row is None:
        return None
    return channel, row


class DisconnectSelect(discord.ui.UserSelect):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(placeholder="Elige a quién desconectar", min_values=1, max_values=1)
        self.channel = channel

    async def callback(self, interaction: discord.Interaction):
        member = self.values[0]
        if not isinstance(member, discord.Member) or member.voice is None or member.voice.channel != self.channel:
            await interaction.response.edit_message(content="Esa persona ya no está en tu canal.", view=None)
            return
        await member.move_to(None, reason=f"Expulsado por {interaction.user} desde el panel de VoiceMaster")
        await interaction.response.edit_message(content=f"🔌 Desconectaste a **{member.display_name}**.", view=None)


class DisconnectView(discord.ui.View):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.add_item(DisconnectSelect(channel))


class ActivitySelect(discord.ui.Select):
    def __init__(self, channel: discord.VoiceChannel):
        options = [discord.SelectOption(label=name) for name in ACTIVITIES]
        super().__init__(placeholder="Elige una actividad", options=options)
        self.channel = channel

    async def callback(self, interaction: discord.Interaction):
        app_id = ACTIVITIES[self.values[0]]
        try:
            invite = await self.channel.create_invite(
                max_age=3600,
                target_type=discord.InviteTarget.embedded_application,
                target_application_id=int(app_id),
            )
            await interaction.response.edit_message(
                content=f"🎮 **{self.values[0]}** — {invite.url}", view=None
            )
        except discord.HTTPException:
            await interaction.response.edit_message(
                content="No pude iniciar esa actividad (puede que Discord no la permita aquí).",
                view=None,
            )


class ActivityView(discord.ui.View):
    def __init__(self, channel: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.add_item(ActivitySelect(channel))


class VoiceMasterPanel(discord.ui.View):
    """Vista persistente: timeout=None + custom_id fijos para que sobreviva a reinicios."""

    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    async def _resolve(self, interaction: discord.Interaction, *, need_owner: bool = True):
        result = await get_member_voice_channel(self.bot, interaction)
        if result is None:
            await interaction.response.send_message(
                embed=error_embed("Debes estar en un canal de voz creado por VoiceMaster."), ephemeral=True
            )
            return None
        channel, row = result
        if need_owner and interaction.user.id != row["owner_id"] and not is_staff(interaction.user):
            await interaction.response.send_message(
                embed=error_embed("Solo el dueño del canal (o un moderador) puede hacer eso."), ephemeral=True
            )
            return None
        return channel, row

    @discord.ui.button(label="Lock", emoji="🔒", style=discord.ButtonStyle.secondary, custom_id="vm:lock")
    async def lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        resolved = await self._resolve(interaction)
        if not resolved:
            return
        channel, _ = resolved
        overwrite = channel.overwrites_for(interaction.guild.default_role)
        overwrite.connect = False
        await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await db.set_voice_flag(channel.id, "locked", 1)
        await interaction.response.send_message(embed=success_embed("🔒 Canal bloqueado."), ephemeral=True)

    @discord.ui.button(label="Unlock", emoji="🔓", style=discord.ButtonStyle.secondary, custom_id="vm:unlock")
    async def unlock(self, interaction: discord.Interaction, button: discord.ui.Button):
        resolved = await self._resolve(interaction)
        if not resolved:
            return
        channel, _ = resolved
        overwrite = channel.overwrites_for(interaction.guild.default_role)
        overwrite.connect = True
        await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await db.set_voice_flag(channel.id, "locked", 0)
        await interaction.response.send_message(embed=success_embed("🔓 Canal desbloqueado."), ephemeral=True)

    @discord.ui.button(label="Ghost", emoji="👻", style=discord.ButtonStyle.secondary, custom_id="vm:ghost")
    async def ghost(self, interaction: discord.Interaction, button: discord.ui.Button):
        resolved = await self._resolve(interaction)
        if not resolved:
            return
        channel, _ = resolved
        overwrite = channel.overwrites_for(interaction.guild.default_role)
        overwrite.view_channel = False
        await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await db.set_voice_flag(channel.id, "ghosted", 1)
        await interaction.response.send_message(embed=success_embed("👻 Canal ocultado."), ephemeral=True)

    @discord.ui.button(label="Reveal", emoji="👁️", style=discord.ButtonStyle.secondary, custom_id="vm:reveal")
    async def reveal(self, interaction: discord.Interaction, button: discord.ui.Button):
        resolved = await self._resolve(interaction)
        if not resolved:
            return
        channel, _ = resolved
        overwrite = channel.overwrites_for(interaction.guild.default_role)
        overwrite.view_channel = True
        await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await db.set_voice_flag(channel.id, "ghosted", 0)
        await interaction.response.send_message(embed=success_embed("👁️ Canal visible de nuevo."), ephemeral=True)

    @discord.ui.button(label="Claim", emoji="🎙️", style=discord.ButtonStyle.secondary, custom_id="vm:claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        resolved = await self._resolve(interaction, need_owner=False)
        if not resolved:
            return
        channel, row = resolved
        owner_still_here = any(m.id == row["owner_id"] for m in channel.members)
        if owner_still_here:
            await interaction.response.send_message(
                embed=error_embed("El dueño sigue en el canal, no puedes reclamarlo."), ephemeral=True
            )
            return
        await db.set_voice_owner(channel.id, interaction.user.id)
        await interaction.response.send_message(
            embed=success_embed(f"🎙️ {interaction.user.mention} ahora es el dueño del canal.")
        )

    @discord.ui.button(label="Desconectar", emoji="🔌", style=discord.ButtonStyle.secondary, custom_id="vm:disconnect")
    async def disconnect(self, interaction: discord.Interaction, button: discord.ui.Button):
        resolved = await self._resolve(interaction)
        if not resolved:
            return
        channel, _ = resolved
        await interaction.response.send_message(
            "¿A quién quieres desconectar?", view=DisconnectView(channel), ephemeral=True
        )

    @discord.ui.button(label="Actividad", emoji="🎮", style=discord.ButtonStyle.secondary, custom_id="vm:activity")
    async def activity(self, interaction: discord.Interaction, button: discord.ui.Button):
        resolved = await self._resolve(interaction, need_owner=False)
        if not resolved:
            return
        channel, _ = resolved
        await interaction.response.send_message(
            "Elige qué actividad iniciar:", view=ActivityView(channel), ephemeral=True
        )

    @discord.ui.button(label="Info", emoji="ℹ️", style=discord.ButtonStyle.secondary, custom_id="vm:info")
    async def info(self, interaction: discord.Interaction, button: discord.ui.Button):
        resolved = await self._resolve(interaction, need_owner=False)
        if not resolved:
            return
        channel, row = resolved
        owner = interaction.guild.get_member(row["owner_id"])
        embed = base_embed(title=f"ℹ️ {channel.name}")
        embed.add_field(name="Dueño", value=owner.mention if owner else "Desconocido")
        embed.add_field(name="Miembros", value=str(len(channel.members)))
        embed.add_field(name="Límite", value=str(channel.user_limit) if channel.user_limit else "Sin límite")
        embed.add_field(name="Bloqueado", value="Sí" if row["locked"] else "No")
        embed.add_field(name="Oculto", value="Sí" if row["ghosted"] else "No")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="➕", style=discord.ButtonStyle.secondary, custom_id="vm:increase")
    async def increase(self, interaction: discord.Interaction, button: discord.ui.Button):
        resolved = await self._resolve(interaction)
        if not resolved:
            return
        channel, _ = resolved
        new_limit = min((channel.user_limit or 0) + 1, 99)
        await channel.edit(user_limit=new_limit)
        await interaction.response.send_message(
            embed=success_embed(f"Límite ahora es **{new_limit}**."), ephemeral=True
        )

    @discord.ui.button(label="➖", style=discord.ButtonStyle.secondary, custom_id="vm:decrease")
    async def decrease(self, interaction: discord.Interaction, button: discord.ui.Button):
        resolved = await self._resolve(interaction)
        if not resolved:
            return
        channel, _ = resolved
        new_limit = max((channel.user_limit or 0) - 1, 0)
        await channel.edit(user_limit=new_limit)
        label = "Sin límite" if new_limit == 0 else str(new_limit)
        await interaction.response.send_message(embed=success_embed(f"Límite ahora es **{label}**."), ephemeral=True)


class VoiceMaster(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_view(VoiceMasterPanel(bot))  # hace que los botones sigan funcionando tras reiniciar

    @commands.group(
        name="voicemaster",
        aliases=["vm"],
        invoke_without_command=True,
        help="Configura el sistema de canales de voz temporales",
    )
    async def voicemaster_group(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @voicemaster_group.command(name="setup", help="[Admin] Crea la categoría, el canal de unión y el panel de control")
    @commands.has_permissions(manage_guild=True)
    async def setup_voicemaster(self, ctx: commands.Context):
        guild = ctx.guild
        category = await guild.create_category("Canales de voz", reason="Configuración de VoiceMaster")
        join_channel = await guild.create_voice_channel(
            "➕ Crear canal", category=category, reason="Canal de unión de VoiceMaster"
        )

        await db.set_guild_field(guild.id, "vm_category_id", category.id)
        await db.set_guild_field(guild.id, "vm_join_channel_id", join_channel.id)

        embed = base_embed(title=PANEL_TITLE, description=PANEL_DESCRIPTION)
        panel_channel = await guild.create_text_channel(
            "interfaz-voz", category=category, reason="Panel de control de VoiceMaster"
        )
        await panel_channel.send(embed=embed, view=VoiceMasterPanel(self.bot))
        await db.set_guild_field(guild.id, "vm_interface_channel_id", panel_channel.id)

        await ctx.send(
            embed=success_embed(
                f"Listo. Únete a {join_channel.mention} para crear tu canal, "
                f"y controla todo desde {panel_channel.mention}."
            )
        )

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=error_embed("Necesitas permiso de `Administrar servidor` para usar esto."))
            return

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ):
        guild_config = await db.get_guild_config(member.guild.id)
        join_channel_id = guild_config["vm_join_channel_id"]

        # El usuario se unió al canal "➕ Crear canal": crear su canal temporal.
        if join_channel_id and after.channel and after.channel.id == join_channel_id:
            category = after.channel.category
            new_channel = await member.guild.create_voice_channel(
                f"🔊 Canal de {member.display_name}",
                category=category,
                reason="Canal temporal de VoiceMaster",
            )
            await db.create_voice_channel(new_channel.id, member.guild.id, member.id)
            try:
                await member.move_to(new_channel, reason="VoiceMaster: canal temporal")
            except discord.HTTPException:
                pass

        # El canal anterior era un canal temporal y se quedó vacío: borrarlo.
        if before.channel is not None:
            row = await db.get_voice_channel(before.channel.id)
            if row is not None and len(before.channel.members) == 0:
                try:
                    await before.channel.delete(reason="VoiceMaster: canal vacío")
                except discord.HTTPException:
                    pass
                await db.delete_voice_channel(before.channel.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceMaster(bot))
