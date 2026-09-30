"""PIN-код на административные разделы программы.

Хранится не сам код, а его хеш: файл настроек лежит в той же папке, что и
результаты, и человек, открывший его блокнотом, не должен узнать код.

Чего эта защита НЕ делает (важно понимать границы): она не защищает файлы.
``.qtest`` — обычный zip, ``results.db`` — обычный SQLite; тот, кто доберётся
до папки с данными, прочитает их в обход программы. PIN закрывает доступ к
разделам интерфейса — то есть ровно тот сценарий, когда сотрудник в ожидании
своей очереди листает конструктор и смотрит правильные ответы.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
from pathlib import Path

from .paths import data_dir

#: Медленная функция: перебор коротких кодов не должен быть мгновенным.
ITERATIONS = 200_000
SALT_BYTES = 16
MIN_LENGTH = 4
FILE_VERSION = 1


class PinError(Exception):
    """PIN не соответствует требованиям."""


def _hash(pin: str, salt: bytes, iterations: int = ITERATIONS) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations)
    return digest.hex()


class PinStore:
    """Хранилище PIN-кода администратора."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else data_dir() / "security.json"

    # ------------------------------------------------------------------ чтение

    def _read(self) -> dict | None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or "hash" not in data or "salt" not in data:
            return None
        return data

    def is_set(self) -> bool:
        return self._read() is not None

    # ------------------------------------------------------------------ запись

    def set_pin(self, pin: str) -> None:
        pin = (pin or "").strip()
        if len(pin) < MIN_LENGTH:
            raise PinError(f"PIN должен быть не короче {MIN_LENGTH} символов")

        salt = secrets.token_bytes(SALT_BYTES)
        payload = {
            "version": FILE_VERSION,
            "iterations": ITERATIONS,
            "salt": salt.hex(),
            "hash": _hash(pin, salt),
        }

        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Атомарно: оборванная запись не должна оставить файл, который читается
        # как «PIN не задан» — это молча снимало бы защиту.
        fd, tmp_name = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        os.close(fd)
        tmp_path = Path(tmp_name)
        try:
            tmp_path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
            os.replace(tmp_path, self.path)
        except OSError:
            tmp_path.unlink(missing_ok=True)
            raise

    def verify(self, pin: str) -> bool:
        data = self._read()
        if data is None:
            return False
        try:
            salt = bytes.fromhex(data["salt"])
            iterations = int(data.get("iterations", ITERATIONS))
        except (ValueError, TypeError):
            return False
        # compare_digest — против атак по времени сравнения.
        return hmac.compare_digest(_hash(pin, salt, iterations), str(data["hash"]))

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
