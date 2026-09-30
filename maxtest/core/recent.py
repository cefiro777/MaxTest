"""Список недавно открытых тестов.

Нужен, чтобы «Пройти тест» не требовал каждый раз лазить по папкам: файлы
могут лежать не только в папке тестов, но и на флешке или в сетевой шаре.
"""

from __future__ import annotations

import json
from pathlib import Path

from .paths import data_dir

MAX_ENTRIES = 15


class RecentTests:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else data_dir() / "recent_tests.json"

    def list(self) -> list[Path]:
        """Только существующие файлы: удалённые записи молча отсеиваются."""
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(raw, list):
            return []

        result: list[Path] = []
        for item in raw:
            candidate = Path(str(item))
            if candidate.exists() and candidate not in result:
                result.append(candidate)
        return result[:MAX_ENTRIES]

    def add(self, path: str | Path) -> None:
        path = Path(path).resolve()
        entries = [p for p in self.list() if p.resolve() != path]
        entries.insert(0, path)
        try:
            self.path.write_text(
                json.dumps([str(p) for p in entries[:MAX_ENTRIES]], ensure_ascii=False, indent=1),
                encoding="utf-8",
            )
        except OSError:
            pass  # не смогли запомнить — не повод мешать работе
