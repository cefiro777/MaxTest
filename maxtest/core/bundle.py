"""Чтение и запись файла теста ``.qtest``.

Формат — обычный zip (как ``.docx``)::

    demo.qtest
    ├── manifest.json     — вся структура теста
    └── media/            — картинки вопросов

Медиа держим целиком в памяти: 20 вопросов × картинка ≈ единицы мегабайт после
ресайза, зато не нужно следить за временными папками и блокировками файлов.

Сохранение атомарное: пишем во временный файл рядом и подменяем через
``os.replace``. Без этого аварийное завершение посреди записи убивает тест
целиком, а на Windows ещё и невозможно перезаписать открытый zip «поверх себя».
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .models import Test, now_iso
from .schema import SchemaError, load_test, dump_test

MANIFEST_NAME = "manifest.json"
MEDIA_DIR = "media"
DEFAULT_EXT = ".qtest"

#: Максимальная сторона картинки после вставки. Фото с телефона (5 МБ) иначе
#: раздувают тест до сотен мегабайт и вешают превью в конструкторе.
IMAGE_MAX_SIDE = 1200
IMAGE_QUALITY = 85


class BundleError(Exception):
    """Файл теста не открывается или не сохраняется."""


def _is_safe_media_path(name: str) -> bool:
    """Защита от zip-slip: только ``media/<имя>`` без выходов наверх."""
    if name.startswith("/") or ":" in name or "\\" in name:
        return False
    parts = name.split("/")
    return len(parts) == 2 and parts[0] == MEDIA_DIR and parts[1] not in ("", ".", "..")


@dataclass
class TestInfo:
    """Краткие сведения о тесте без загрузки картинок — для списка выбора."""

    path: Path
    id: str = ""
    title: str = ""
    description: str = ""
    question_count: int = 0
    revision: int = 1
    modified_at: str = ""

    @property
    def name(self) -> str:
        return self.path.name


def peek(path: str | Path) -> TestInfo | None:
    """Читает только manifest.json. Возвращает ``None``, если это не тест.

    Для списка из двадцати файлов распаковывать картинки незачем — окно выбора
    открывалось бы заметно дольше.
    """
    path = Path(path)
    try:
        with zipfile.ZipFile(path, "r") as zf:
            data = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
    except (OSError, KeyError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None
    return TestInfo(
        path=path,
        id=str(data.get("id", "")),
        title=str(data.get("title") or path.stem),
        description=str(data.get("description") or ""),
        question_count=len(data.get("questions") or []),
        revision=int(data.get("revision", 1) or 1),
        modified_at=str(data.get("modified_at") or ""),
    )


class Bundle:
    """Открытый файл теста: модель + медиа + путь на диске."""

    def __init__(
        self,
        test: Test,
        media: dict[str, bytes] | None = None,
        path: Path | None = None,
    ) -> None:
        self.test = test
        self.media: dict[str, bytes] = media or {}
        self.path: Path | None = Path(path) if path else None
        #: Картинки, на которые ссылаются вопросы, но которых нет в архиве.
        self.missing_media: list[str] = []

    # ---------------------------------------------------------------- create

    @classmethod
    def new(cls, title: str = "Новый тест") -> "Bundle":
        return cls(Test(title=title))

    # ------------------------------------------------------------------ load

    @classmethod
    def load(cls, path: str | Path) -> "Bundle":
        path = Path(path)
        if not path.exists():
            raise BundleError(f"Файл не найден: {path}")

        try:
            with zipfile.ZipFile(path, "r") as zf:
                try:
                    raw = zf.read(MANIFEST_NAME)
                except KeyError:
                    raise BundleError(
                        f"{path.name}: это не файл теста MaxTest "
                        f"(внутри нет {MANIFEST_NAME})"
                    )

                try:
                    data = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise BundleError(f"{path.name}: повреждён {MANIFEST_NAME} ({exc})")

                media: dict[str, bytes] = {}
                for name in zf.namelist():
                    if name == MANIFEST_NAME or name.endswith("/"):
                        continue
                    if not _is_safe_media_path(name):
                        continue  # мусор или подозрительный путь — молча пропускаем
                    media[name] = zf.read(name)

        except zipfile.BadZipFile:
            raise BundleError(f"{path.name}: файл повреждён или не является файлом теста")

        try:
            test = load_test(data)
        except SchemaError as exc:
            raise BundleError(f"{path.name}: {exc}")

        bundle = cls(test, media, path)
        bundle.missing_media = sorted(test.used_images() - set(media))
        return bundle

    # ------------------------------------------------------------------ save

    def save(self, path: str | Path | None = None, bump_revision: bool = True) -> Path:
        """Атомарно записывает бандл. Возвращает фактический путь."""
        target = Path(path) if path else self.path
        if target is None:
            raise BundleError("Не указан путь для сохранения теста")
        if target.suffix == "":
            target = target.with_suffix(DEFAULT_EXT)

        if bump_revision:
            self.test.revision += 1
            self.test.modified_at = now_iso()

        target.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_name = tempfile.mkstemp(
            dir=str(target.parent), prefix=f".{target.stem}_", suffix=".tmp"
        )
        os.close(fd)
        tmp_path = Path(tmp_name)

        try:
            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
                manifest = json.dumps(
                    dump_test(self.test), ensure_ascii=False, indent=2
                )
                zf.writestr(MANIFEST_NAME, manifest.encode("utf-8"))
                for name, blob in sorted(self.media.items()):
                    # Картинки уже сжаты — второй раз не жмём.
                    zf.writestr(name, blob, compress_type=zipfile.ZIP_STORED)
            os.replace(tmp_path, target)
        except Exception as exc:
            tmp_path.unlink(missing_ok=True)
            raise BundleError(f"Не удалось сохранить {target.name}: {exc}")

        self.path = target
        return target

    # ----------------------------------------------------------------- media

    def add_image(self, src: str | Path) -> str:
        """Добавляет картинку с ресайзом. Возвращает путь вида ``media/img_ab12cd34.jpg``.

        Имя файла — хеш уже обработанных байт, поэтому одна и та же картинка,
        вставленная в десять вопросов, лежит в архиве один раз.
        """
        src = Path(src)
        if not src.exists():
            raise BundleError(f"Картинка не найдена: {src}")

        blob, ext = self._process_image(src)
        digest = hashlib.md5(blob).hexdigest()[:8]
        name = f"{MEDIA_DIR}/img_{digest}{ext}"
        self.media[name] = blob
        return name

    def add_image_bytes(self, blob: bytes, ext: str = ".png") -> str:
        """Кладёт готовые байты как есть (для тестов и генерации примеров)."""
        digest = hashlib.md5(blob).hexdigest()[:8]
        name = f"{MEDIA_DIR}/img_{digest}{ext}"
        self.media[name] = blob
        return name

    def get_image_bytes(self, rel_path: str | None) -> bytes | None:
        if not rel_path:
            return None
        return self.media.get(rel_path)

    def prune_media(self) -> list[str]:
        """Удаляет медиа, на которые больше никто не ссылается."""
        used = self.test.used_images()
        orphans = [name for name in self.media if name not in used]
        for name in orphans:
            del self.media[name]
        return orphans

    @staticmethod
    def _process_image(src: Path) -> tuple[bytes, str]:
        """Ресайз + перекодирование. PNG с прозрачностью остаётся PNG."""
        try:
            from PIL import Image
        except ImportError:
            raise BundleError(
                "Для работы с картинками нужен Pillow (pip install Pillow)"
            )

        try:
            with Image.open(src) as img:
                img.load()
                has_alpha = img.mode in ("RGBA", "LA") or (
                    img.mode == "P" and "transparency" in img.info
                )

                if max(img.size) > IMAGE_MAX_SIDE:
                    img.thumbnail((IMAGE_MAX_SIDE, IMAGE_MAX_SIDE), Image.LANCZOS)

                buf = io.BytesIO()
                if has_alpha:
                    img.convert("RGBA").save(buf, format="PNG", optimize=True)
                    ext = ".png"
                else:
                    img.convert("RGB").save(
                        buf, format="JPEG", quality=IMAGE_QUALITY, optimize=True
                    )
                    ext = ".jpg"
                return buf.getvalue(), ext
        except BundleError:
            raise
        except Exception as exc:
            raise BundleError(f"Не удалось прочитать изображение {src.name}: {exc}")
