"""Рисует resources/icon.ico — иконку приложения.

Генератором, а не бинарником в репозитории: иконку легко поправить, и не нужно
хранить в проекте файл, происхождение которого через год никто не вспомнит.

Запуск:  python -m tools.make_icon
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "maxtest" / "resources" / "icon.ico"

BACKGROUND = (31, 78, 63)
SHEET = (245, 245, 240)
CHECK = (46, 160, 87)


def draw_icon(size: int = 256) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 256  # все координаты заданы для 256×256

    d.rounded_rectangle([8 * s, 8 * s, 248 * s, 248 * s], radius=40 * s, fill=BACKGROUND)
    # Лист с ответами
    d.rounded_rectangle([64 * s, 40 * s, 192 * s, 216 * s], radius=12 * s, fill=SHEET)
    for row in range(3):
        y = (78 + row * 34) * s
        d.rounded_rectangle([84 * s, y, 172 * s, y + 12 * s], radius=6 * s, fill=(200, 205, 200))
    # Галочка поверх листа
    d.line(
        [(88 * s, 168 * s), (120 * s, 200 * s), (196 * s, 108 * s)],
        fill=CHECK,
        width=int(22 * s),
        joint="curve",
    )
    return img


def build() -> Path:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    master = draw_icon(256)
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    master.save(OUT, format="ICO", sizes=sizes)
    return OUT


if __name__ == "__main__":
    path = build()
    print(f"Готово: {path} ({path.stat().st_size / 1024:.1f} КБ)")
