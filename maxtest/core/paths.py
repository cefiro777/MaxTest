"""Пути к данным приложения.

Ни один байт не пишется рядом с ``.exe``: в ``Program Files`` у обычного
пользователя нет прав на запись, и приложение упадёт на первом же сохранении
результата. Всё уходит в ``%APPDATA%\\MaxTest``.

Переменная окружения ``MAXTEST_DATA_DIR`` переопределяет корень — это нужно
тестам и позволяет админу держать данные на сетевом/съёмном диске.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_DIR_NAME = "MaxTest"
ENV_OVERRIDE = "MAXTEST_DATA_DIR"


def data_dir() -> Path:
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        root = Path(override)
    else:
        base = os.environ.get("APPDATA") or Path.home()
        root = Path(base) / APP_DIR_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def db_path() -> Path:
    return data_dir() / "results.db"


def backup_dir() -> Path:
    d = data_dir() / "backup"
    d.mkdir(parents=True, exist_ok=True)
    return d


def logs_dir() -> Path:
    d = data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def tests_dir() -> Path:
    """Папка по умолчанию для файлов ``.qtest``."""
    d = data_dir() / "tests"
    d.mkdir(parents=True, exist_ok=True)
    return d
