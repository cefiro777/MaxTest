"""Рисует og-image — картинку 1200×630 для превью ссылки в мессенджерах и соцсетях.

Без неё ссылка выглядит голым текстом, а в поисковой выдаче и в пересылке
такое превью — половина решения «открывать или нет».

Запуск:  python site/make_og_image.py
"""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE / "assets" / "og-image.png"

WIDTH, HEIGHT = 1200, 630
PAPER = (245, 247, 250)
INK = (14, 23, 38)
ACCENT = (36, 87, 214)
MUTED = (90, 100, 120)
RULE = (216, 222, 233)

FONTS = Path("C:/Windows/Fonts")


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def build() -> Path:
    img = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(img)

    # Скриншот главного окна — справа, с рамкой.
    images = json.loads((HERE / "images.json").read_text(encoding="utf-8"))
    raw = base64.b64decode(images["main"].split(",", 1)[1])
    with Image.open(io.BytesIO(raw)) as shot:
        shot = shot.convert("RGB")
        target_w = 520
        shot = shot.resize((target_w, round(shot.height * target_w / shot.width)), Image.LANCZOS)
        box = (WIDTH - target_w - 60, 96)
        img.paste(shot, box)
        draw.rectangle(
            [box[0] - 1, box[1] - 1, box[0] + shot.width, box[1] + shot.height],
            outline=RULE, width=2,
        )

    x = 72
    draw.text((x, 96), "АТТЕСТАЦИЯ ПЕРСОНАЛА · WINDOWS · ОФЛАЙН",
              font=font("consola.ttf", 20), fill=MUTED)

    # Составное слово: «Max» чернилами, «Test» акцентом — как на самой странице.
    title_font = font("georgiab.ttf", 92)
    draw.text((x, 140), "Max", font=title_font, fill=INK)
    max_width = draw.textlength("Max", font=title_font)
    draw.text((x + max_width, 140), "Test", font=title_font, fill=ACCENT)

    body = font("segoeui.ttf", 30)
    lines = [
        "Программа для проверки знаний",
        "сотрудников на одном компьютере.",
        "Без интернета и передачи данных",
        "на чужие серверы.",
    ]
    y = 276
    for line in lines:
        draw.text((x, y), line, font=body, fill=INK)
        y += 44

    draw.line([(x, 486), (x + 470, 486)], fill=RULE, width=2)
    draw.text((x, 508), "Бесплатно · лицензия MIT · Windows 10 / 11",
              font=font("segoeui.ttf", 24), fill=MUTED)
    draw.text((x, 552), "infomaxtest.ru", font=font("consolab.ttf", 26), fill=ACCENT)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, "PNG", optimize=True)
    return OUT


if __name__ == "__main__":
    path = build()
    print(f"{path}: {path.stat().st_size / 1024:.0f} KB")
