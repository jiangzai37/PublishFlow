import hashlib
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.config import get_settings

COVER_SIZE = (1200, 630)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        ["C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/simhei.ttf"]
        if bold
        else ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simsun.ttc"]
    )
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _wrap_title(
    draw: ImageDraw.ImageDraw, title: str, font: ImageFont.ImageFont, width: int
) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in title:
        candidate = current + char
        if draw.textbbox((0, 0), candidate, font=font)[2] > width and current:
            lines.append(current)
            current = char
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:3]


def create_cover(
    title: str, subtitle: str = "PUBLISHFLOW · ORIGINAL", background: Path | None = None
) -> str:
    settings = get_settings()
    if background:
        with Image.open(background) as source:
            image = source.convert("RGB")
        ratio = max(COVER_SIZE[0] / image.width, COVER_SIZE[1] / image.height)
        image = image.resize((round(image.width * ratio), round(image.height * ratio)))
        left = (image.width - COVER_SIZE[0]) // 2
        top = (image.height - COVER_SIZE[1]) // 2
        image = image.crop((left, top, left + COVER_SIZE[0], top + COVER_SIZE[1]))
        overlay = Image.new("RGBA", image.size, (31, 27, 22, 110))
        image = Image.alpha_composite(image.convert("RGBA"), overlay)
    else:
        image = Image.new("RGBA", COVER_SIZE, (242, 237, 227, 255))
        draw = ImageDraw.Draw(image)
        draw.ellipse((820, -160, 1370, 390), fill=(167, 72, 50, 230))
        draw.ellipse((920, 110, 1320, 510), fill=(49, 93, 112, 210))
        draw.rectangle((0, 568, 1200, 630), fill=(167, 72, 50, 255))
        draw.line((78, 104, 162, 104), fill=(167, 72, 50, 255), width=5)

    draw = ImageDraw.Draw(image)
    title_font = _font(68, bold=True)
    lines = _wrap_title(draw, title[:70], title_font, 1000)
    start_y = 208 if len(lines) > 1 else 248
    for index, line in enumerate(lines):
        draw.text(
            (80, start_y + index * 94),
            line,
            font=title_font,
            fill=(255, 250, 240, 255) if background else (33, 30, 26, 255),
        )
    draw.text(
        (82, 526),
        subtitle,
        font=_font(22),
        fill=(235, 226, 212, 255) if background else (112, 99, 84, 255),
    )
    draw.text((1045, 522), "PF", font=_font(30, bold=True), fill=(255, 250, 240, 255))

    filename = f"{uuid.uuid4().hex[:12]}-{hashlib.sha1(title.encode()).hexdigest()[:6]}.png"
    output = settings.data_dir / "covers" / filename
    image.convert("RGB").save(output, quality=92)
    return f"/media/{filename}"
