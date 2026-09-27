"""
cogs/shop.py
-------------
Tienda del servidor con una interfaz cómoda: un menú desplegable para
elegir el artículo y un botón para confirmar la compra. Los admins pueden
crear artículos que, opcionalmente, entregan un rol al comprarlos.

Comandos (todos con el prefijo del bot):
    ,shop                 -> abre la tienda
    ,buy <nombre> [cant]  -> compra un artículo por nombre
    ,inventory [usuario]  -> muestra el inventario
    ,shop add ...         -> [Admin] agrega un artículo
    ,shop remove <nombre> -> [Admin] elimina un artículo
"""

import discord
from discord.ext import commands

from config import config
from database import db
from utils.embeds import base_embed, error_embed, success_embed, money

SHOP_COLOR = config.COLOR_SHOP


def item_embed(guild: discord.Guild, items) -> discord.Embed:
    embed = base_embed(title=f"🛍️ Tienda de {guild.name}", color=SHOP_COLOR)
    if not items:
        embed.description = "Todavía no hay artículos en la tienda."
        return embed

    lines = []
    for it in items:
        stock_txt = "∞" if it["stock"] < 0 else str(it["stock"])
        extra = f" · 🎭 <@&{it['role_id']}>" if it["role_id"] else ""
        desc = f" — {it['description']}" if it["description"] else ""
        lines.append(f"**#{it['id']} · {it['name']}** — {money(it['price'])} · stock: {stock_txt}{extra}{desc}")
    embed.description = "\n".join(lines)
    embed.set_footer(text=f"Usa el menú de abajo para comprar, o {config.PREFIX}buy <nombre>")
    return embed


class BuyConfirmView(discord.ui.View):
    def __init__(self, buyer: discord.Member, item_row):
        super().__init__(timeout=60)
        self.buyer = buyer
        self.item_row = item_row

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.buyer.id:
            await interaction.response.send_message("Esta compra no es tuya.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ Confirmar compra", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        result = await purchase(interaction.guild_id, interaction.user, self.item_row, quantity=1)
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=result, view=self)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            embed=error_embed("Compra cancelada.", title="Cancelado"), view=self
        )


class ShopSelect(discord.ui.Select):
    def __init__(self, items):
        options = [
            discord.SelectOption(
                label=f"{it['name']} — {money(it['price'])}",
                description=(it["description"] or "Sin descripción")[:95],
                value=str(it["id"]),
            )
            for it in items[:25]
        ]
        super().__init__(placeholder="Elige un artículo para comprar…", options=options)

    async def callback(self, interaction: discord.Interaction):
        item_id = int(self.values[0])
        item = await db.get_shop_item(interaction.guild_id, item_id)
        if not item:
            await interaction.response.send_message(embed=error_embed("Ese artículo ya no existe."), ephemeral=True)
            return

        preview = base_embed(
            title=f"🛒 {item['name']}", description=item["description"] or "\u200b", color=SHOP_COLOR
        )
        preview.add_field(name="Precio", value=money(item["price"]))
        preview.add_field(name="Stock", value="∞" if item["stock"] < 0 else str(item["stock"]))
        if item["role_id"]:
            preview.add_field(name="Entrega", value=f"<@&{item['role_id']}>", inline=False)

        await interaction.response.send_message(
            embed=preview, view=BuyConfirmView(interaction.user, item), ephemeral=True
        )


class ShopView(discord.ui.View):
    def __init__(self, items):
        super().__init__(timeout=180)
        if items:
            self.add_item(ShopSelect(items))


async def purchase(guild_id: int, buyer: discord.Member, item_row, quantity: int) -> discord.Embed:
    """Ejecuta la compra y devuelve el embed de resultado. Reutilizable desde
    el menú desplegable (interacción de componente) y desde el comando ,buy."""
    if item_row["stock"] == 0:
        return error_embed(f"**{item_row['name']}** está agotado.")

    total_price = item_row["price"] * quantity
    user_row = await db.get_user(buyer.id, guild_id)
    if user_row["balance"] < total_price:
        return error_embed("No tienes suficiente saldo para comprar esto.")

    await db.update_balance(buyer.id, guild_id, -total_price)
    await db.add_inventory_item(guild_id, buyer.id, item_row["id"], quantity)
    if item_row["stock"] > 0:
        for _ in range(quantity):
            await db.decrement_stock(item_row["id"])

    if item_row["role_id"]:
        role = buyer.guild.get_role(item_row["role_id"])
        if role:
            try:
                await buyer.add_roles(role, reason="Compra en la tienda")
            except discord.Forbidden:
                pass

    return success_embed(
        f"Compraste **{quantity}x {item_row['name']}** por **{money(total_price)}**.",
        title="✅ Compra realizada",
    )


class Shop(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="shop", invoke_without_command=True, help="Abre la tienda del servidor")
    async def shop(self, ctx: commands.Context):
        items = await db.get_shop_items(ctx.guild.id)
        embed = item_embed(ctx.guild, items)
        await ctx.send(embed=embed, view=ShopView(items))

    @commands.command(name="buy", help="Compra un artículo de la tienda por su nombre. Uso: ,buy <nombre> [cantidad]")
    async def buy(self, ctx: commands.Context, nombre: str, cantidad: commands.Range[int, 1] = 1):
        item = await db.get_shop_item_by_name(ctx.guild.id, nombre)
        if not item:
            await ctx.send(embed=error_embed(f"No encontré ningún artículo llamado **{nombre}**."))
            return
        result = await purchase(ctx.guild.id, ctx.author, item, cantidad)
        await ctx.send(embed=result)

    @commands.command(name="inventory", aliases=["inv"], help="Muestra tu inventario o el de otro usuario")
    async def inventory(self, ctx: commands.Context, usuario: discord.Member | None = None):
        target = usuario or ctx.author
        rows = await db.get_inventory(ctx.guild.id, target.id)
        embed = base_embed(title=f"🎒 Inventario de {target.display_name}", color=SHOP_COLOR)
        if not rows:
            embed.description = "Vacío por ahora."
        else:
            embed.description = "\n".join(f"**{r['quantity']}x** {r['name']}" for r in rows)
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    @shop.command(name="add", help="[Admin] Agrega un artículo a la tienda. Uso: ,shop add <nombre> <precio> [stock] [@rol] [descripción...]")
    @commands.has_permissions(manage_guild=True)
    async def shop_add(
        self, ctx: commands.Context, nombre: str, precio: commands.Range[int, 1],
        stock: commands.Range[int, -1] = -1, rol: discord.Role | None = None,
        *, descripcion: str | None = None,
    ):
        ok = await db.add_shop_item(ctx.guild.id, nombre, precio, descripcion, rol.id if rol else None, stock)
        if not ok:
            await ctx.send(embed=error_embed("Ya existe un artículo con ese nombre en este servidor."))
            return
        await ctx.send(embed=success_embed(f"Artículo **{nombre}** agregado a la tienda por {money(precio)}."))

    @shop.command(name="remove", help="[Admin] Elimina un artículo de la tienda. Uso: ,shop remove <nombre>")
    @commands.has_permissions(manage_guild=True)
    async def shop_remove(self, ctx: commands.Context, *, nombre: str):
        ok = await db.remove_shop_item(ctx.guild.id, nombre)
        if ok:
            await ctx.send(embed=success_embed(f"Artículo **{nombre}** eliminado."))
        else:
            await ctx.send(embed=error_embed("No encontré ese artículo."))

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
    await bot.add_cog(Shop(bot))
