"""Автосохранение незавершённой попытки.

Если приложение закроют, обесточат компьютер или оно упадёт посреди теста,
человек не должен проходить всё заново. Состояние попытки пишется в отдельный
JSON рядом с базой и удаляется при нормальном завершении; всё, что осталось в
папке при следующем запуске, — это оборванная попытка.

Файл прогресса намеренно не в базе: запись в SQLite каждые 15 секунд ради
данных, которые живут минуты, — лишний риск для базы с результатами.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .models import new_id
from .paths import data_dir


def progress_dir() -> Path:
    d = data_dir() / "progress"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class PendingAttempt:
    """Снимок незавершённой попытки."""

    id: str = field(default_factory=lambda: new_id("run_"))
    test_path: str = ""
    test_id: str = ""
    test_title: str = ""
    employee_name: str = ""
    employee_id: int | None = None
    started_at: str = ""
    saved_at: str = ""
    elapsed_sec: int = 0
    index: int = 0
    plan: dict = field(default_factory=dict)
    answers: dict = field(default_factory=dict)

    @property
    def answered_count(self) -> int:
        return sum(1 for value in self.answers.values() if value)

    @property
    def total_count(self) -> int:
        return len(self.plan.get("question_ids") or [])


class ProgressStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.dir = Path(directory) if directory else progress_dir()
        self.dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, attempt_id: str) -> Path:
        return self.dir / f"{attempt_id}.json"

    def save(self, pending: PendingAttempt) -> Path:
        pending.saved_at = datetime.now().replace(microsecond=0).isoformat()
        target = self.path_for(pending.id)

        # Атомарно: оборванная запись прогресса не должна ломать восстановление.
        fd, tmp_name = tempfile.mkstemp(dir=str(self.dir), suffix=".tmp")
        os.close(fd)
        tmp_path = Path(tmp_name)
        try:
            tmp_path.write_text(
                json.dumps(asdict(pending), ensure_ascii=False, indent=1),
                encoding="utf-8",
            )
            os.replace(tmp_path, target)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
        return target

    def list_pending(self) -> list[PendingAttempt]:
        out: list[PendingAttempt] = []
        for path in sorted(self.dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                out.append(PendingAttempt(**data))
            except Exception:
                # Битый файл прогресса не должен мешать запуску программы.
                continue
        return out

    def delete(self, attempt_id: str) -> None:
        self.path_for(attempt_id).unlink(missing_ok=True)

    def clear(self) -> None:
        for path in self.dir.glob("*.json"):
            path.unlink(missing_ok=True)
