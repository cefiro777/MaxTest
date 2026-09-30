"""Готовит картинку QR-кода для окна «Поддержать проект».

Исходник — PDF от банка, в котором сама карточка занимает четверть страницы,
а остальное поле. Скрипт рендерит страницу, обрезает поля по содержимому и
сохраняет PNG нужного размера.

Запуск:  python -m tools.make_donate_qr [путь_к_pdf]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "build" / "donate_qr_source.pdf"
OUT = ROOT / "maxtest" / "resources" / "donate_qr.png"

#: Ширина итоговой картинки. Больше не нужно: QR со стороной ~420 px камера
#: телефона читает с экрана без проблем, а файл остаётся лёгким.
TARGET_WIDTH = 460
RENDER_SCALE = 4
MARGIN = 12


def render_pdf(path: Path):
    """PDF читается плагином Qt ``qpdf`` — тем же, что показывает картинки."""
    from PyQt6.QtGui import QImageReader
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])  # noqa: F841 — нужен для плагинов

    reader = QImageReader(str(path))
    if not reader.canRead():
        raise SystemExit(f"Не удалось прочитать {path}: {reader.errorString()}")

    reader.setScaledSize(reader.size() * RENDER_SCALE)
    image = reader.read()
    if image.isNull():
        raise SystemExit(f"Пустая страница в {path}")

    temp = Path(os.environ.get("TEMP", ".")) / "_donate_render.png"
    image.save(str(temp))
    return temp


def crop_and_resize(rendered: Path) -> Path:
    from PIL import Image, ImageChops

    with Image.open(rendered) as img:
        img = img.convert("RGB")
        # Ищем именно жёлтую карточку, а не «всё, что не белое»: по краям
        # страницы PDF есть тонкие тёмные полосы, из-за которых обрезка по
        # содержимому возвращает лист целиком.
        red, green, blue = img.split()
        # Пиксель жёлтый, когда выполняются ВСЕ три условия сразу, поэтому
        # маски объединяются логическим И, а не складываются в один канал.
        masks = (
            red.point(lambda v: 255 if v > 200 else 0).convert("1"),
            green.point(lambda v: 255 if v > 170 else 0).convert("1"),
            blue.point(lambda v: 255 if v < 140 else 0).convert("1"),
        )
        yellow = ImageChops.logical_and(ImageChops.logical_and(*masks[:2]), masks[2])
        box = yellow.getbbox()

        if box is None:  # не нашли карточку — обрезаем по содержимому
            background = Image.new("RGB", img.size, (255, 255, 255))
            box = ImageChops.difference(img, background).convert("L").point(
                lambda v: 255 if v > 12 else 0
            ).getbbox()
        if box is None:
            raise SystemExit("На странице не найдено содержимое для обрезки")

        left, top, right, bottom = box
        left = max(0, left - MARGIN)
        top = max(0, top - MARGIN)
        right = min(img.width, right + MARGIN)
        bottom = min(img.height, bottom + MARGIN)

        card = img.crop((left, top, right, bottom))
        height = round(card.height * TARGET_WIDTH / card.width)
        card = card.resize((TARGET_WIDTH, height), Image.LANCZOS)

        OUT.parent.mkdir(parents=True, exist_ok=True)
        card.save(OUT, format="PNG", optimize=True)
    return OUT


def main() -> int:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else SOURCE
    if not source.exists():
        raise SystemExit(f"Не найден исходный файл: {source}")

    rendered = render_pdf(source)
    out = crop_and_resize(rendered)
    rendered.unlink(missing_ok=True)

    from PIL import Image

    with Image.open(out) as img:
        print(f"Готово: {out} ({img.width}x{img.height}, "
              f"{out.stat().st_size / 1024:.1f} КБ)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
