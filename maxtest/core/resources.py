"""Доступ к файлам из папки ``maxtest/resources``.

В собранном PyInstaller приложении файлы лежат не рядом с исходниками, а во
временной папке распаковки (``sys._MEIPASS``) или в ``_internal``. Один хелпер
на оба случая избавляет от «в разработке картинка есть, в сборке нет».
"""

from __future__ import annotations

import sys
from pathlib import Path


def resources_dir() -> Path:
    base = getattr(sys, "_MEIPASS", None)
    if base:  # собранное приложение
        return Path(base) / "maxtest" / "resources"
    return Path(__file__).resolve().parent.parent / "resources"


def resource_path(name: str) -> Path:
    return resources_dir() / name


def read_bytes(name: str) -> bytes | None:
    """Байты ресурса или ``None``, если файла нет.

    Отсутствие картинки не должно ронять программу: интерфейс просто
    обойдётся без неё.
    """
    try:
        return resource_path(name).read_bytes()
    except OSError:
        return None
