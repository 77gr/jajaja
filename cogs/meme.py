"""
cogs/meme.py
-------------
Comando "caption": le pone una barra blanca con texto en negro arriba de
una imagen o gif (el mismo estilo clásico de meme que viste en tu
captura de "rompió"). Funciona con:
  - una imagen/gif adjunto en el mismo mensaje, o
  - respondiendo (reply) a un mensaje que tenga una imagen/gif.

Uso:  ,caption <texto>
"""

import io

import aiohttp
import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont, ImageSequence

from utils.embeds import error_embed

MAX_FRAMES = 60  # límite para que un gif gigante no cuelgue al bot


def _find_font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = f"{current} {word}".strip()
        if draw.textlength(test, font=font) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _caption_bar_height(width: int, lines: list[str], font_size: int) -> int:
    return max(int(font_size * 1.4 * len(lines)) + 20, int(width * 0.15))


def _draw_caption(frame: Image.Image, text: str) -> Image.Image:
    frame = frame.convert("RGBA")
    width, height = frame.size
    font_size = max(int(width / 10), 18)
    font = _find_font(font_size)

    dummy = Image.new("RGBA", (width, 10))
    draw = ImageDraw.Draw(dummy)
    lines = _wrap_text(draw, text.upper(), font, width - 20)

    # Reduce el tamaño de fuente si el texto no cabe en pocas líneas.
    while len(lines) > 3 and font_size > 12:
        font_size -= 2
        font = _find_font(font_size)
        lines = _wrap_text(draw, text.upper(), font, width - 20)

    bar_height = _caption_bar_height(width, lines, font_size)
    canvas = Image.new("RGBA", (width, height + bar_height), (255, 255, 255, 255))
    canvas.paste(frame, (0, bar_height))

    draw = ImageDraw.Draw(canvas)
    y = 10
    for line in lines:
        text_width = draw.textlength(line, font=font)
        x = (width - text_width) / 2
        draw.text((x, y), line, font=font, fill=(0, 0, 0, 255))
        y += int(font_size * 1.4)

    return canvas


async def _find_source_url(message: discord.Message) -> str | None:
    if message.attachments:
        return message.attachments[0].url
    if message.reference and isinstance(message.reference.resolved, discord.Message):
        ref = message.reference.resolved
        if ref.attachments:
            return ref.attachments[0].url
    return None


class Meme(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="caption")
    async def caption(self, ctx: commands.Context, *, texto: str = None):
        if not texto:
            await ctx.send(embed=error_embed("Escribe el texto del caption. Ej: `,caption rompió`"))
            return

        url = await _find_source_url(ctx.message)
        if not url:
            await ctx.send(
                embed=error_embed(
                    "Adjunta una imagen/gif en el mismo mensaje, o responde (reply) a un mensaje que tenga una."
                )
            )
            return

        async with ctx.typing():
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        await ctx.send(embed=error_embed("No pude descargar esa imagen."))
                        return
                    raw = await resp.read()

            try:
                source = Image.open(io.BytesIO(raw))
            except Exception:
                await ctx.send(embed=error_embed("Ese archivo no parece ser una imagen o gif válido."))
                return

            is_animated = getattr(source, "is_animated", False)
            buffer = io.BytesIO()
            filename = "caption.png"

            if is_animated:
                frames = []
                durations = []
                for i, frame in enumerate(ImageSequence.Iterator(source)):
                    if i >= MAX_FRAMES:
                        break
                    frames.append(_draw_caption(frame, texto).convert("RGB"))
                    durations.append(frame.info.get("duration", 80))
                frames[0].save(
                    buffer, format="GIF", save_all=True, append_images=frames[1:],
                    duration=durations, loop=0,
                )
                filename = "caption.gif"
            else:
                _draw_caption(source, texto).save(buffer, format="PNG")

            buffer.seek(0)
            await ctx.send(file=discord.File(buffer, filename=filename))


async def setup(bot: commands.Bot):
    await bot.add_cog(Meme(bot))
