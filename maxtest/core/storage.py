"""Локальное хранилище результатов (SQLite).

Денормализация намеренная: в попытке хранится снимок ФИО, текста вопроса и
``test_revision``. Тест отредактируют через год, а протокол прошлой аттестации
обязан остаться правдой.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .enums import FinishReason, ScaleType
from .grader import AttemptResult, to_percent
from .models import Scale, Test, Threshold
from .paths import backup_dir, db_path
from .presenter import describe_correct, describe_given
from .session import AttemptPlan


def _scale_to_dict(scale: Scale) -> dict:
    return {
        "type": str(scale.type),
        "thresholds": [
            {"min_percent": t.min_percent, "label": t.label, "passed": t.passed}
            for t in scale.thresholds
        ],
    }


def _scale_from_dict(data: dict) -> Scale:
    thresholds = [
        Threshold(
            min_percent=int(t.get("min_percent", 0)),
            label=t.get("label", ""),
            passed=bool(t.get("passed", False)),
        )
        for t in data.get("thresholds") or []
    ]
    if not thresholds:
        return Scale.default_pass_fail()
    return Scale(type=ScaleType(data.get("type", ScaleType.PASS_FAIL.value)), thresholds=thresholds)

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- name_key = full_name.casefold(): SQLite-шные COLLATE NOCASE и lower()
-- работают только для ASCII, поэтому «Иванов» и «иванов» база считает разными
-- людьми и молча плодит дубли. Регистронезависимость делаем в Python.
CREATE TABLE IF NOT EXISTS employees (
    id         INTEGER PRIMARY KEY,
    full_name  TEXT NOT NULL,
    name_key   TEXT NOT NULL UNIQUE,
    position   TEXT DEFAULT '',
    department TEXT DEFAULT '',
    active     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS attempts (
    id            INTEGER PRIMARY KEY,
    employee_id   INTEGER REFERENCES employees(id),
    employee_name TEXT NOT NULL,
    test_id       TEXT NOT NULL,
    test_title    TEXT NOT NULL,
    test_revision INTEGER NOT NULL,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    finish_reason TEXT,
    seed          INTEGER,
    plan          TEXT,
    -- Снимок шкалы: пересчёт после ручной проверки не должен зависеть от
    -- файла теста, который к тому времени могут изменить или потерять.
    scale         TEXT,
    score         REAL,
    max_score     REAL,
    percent       INTEGER,
    grade_label   TEXT,
    passed        INTEGER,
    needs_review  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS answers (
    id              INTEGER PRIMARY KEY,
    attempt_id      INTEGER NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
    question_id     TEXT NOT NULL,
    question_text   TEXT NOT NULL,
    question_type   TEXT,
    section_title   TEXT,
    -- Ответ и эталон строкой: разбор и отчёты не должны требовать файла .qtest.
    correct_answer  TEXT,
    given_answer    TEXT,
    explanation     TEXT,
    shown_index     INTEGER,
    raw_answer      TEXT,
    is_correct      INTEGER,
    score           REAL,
    max_score       REAL,
    manual_override INTEGER NOT NULL DEFAULT 0
);

"""

# Индексы создаются ОТДЕЛЬНО и после миграции: в базе предыдущей версии
# колонки, по которой строится индекс, может ещё не быть.
INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_attempts_employee ON attempts(employee_id);
CREATE INDEX IF NOT EXISTS idx_attempts_test     ON attempts(test_id);
CREATE INDEX IF NOT EXISTS idx_answers_attempt   ON answers(attempt_id);
"""

DB_VERSION = "1"
BACKUP_KEEP = 30


@dataclass
class Employee:
    id: int
    full_name: str
    position: str = ""
    department: str = ""


class Storage:
    """Соединение с базой результатов. Использовать как контекстный менеджер."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._closed = False
        self.path = Path(path) if path else db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA_SQL)
        self._migrate()
        self.conn.executescript(INDEX_SQL)
        self.conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES ('db_version', ?)", (DB_VERSION,)
        )
        self.conn.commit()

    def _migrate(self) -> None:
        """Догоняет схему в базах, созданных прежними версиями программы.

        ``CREATE TABLE IF NOT EXISTS`` не добавляет колонки в существующую
        таблицу — старая база просто осталась бы без новых полей.
        """
        additions = {
            "attempts": {
                "employee_id": "INTEGER",
                "test_id": "TEXT",
                "seed": "INTEGER",
                "plan": "TEXT",
                "scale": "TEXT",
                "finished_at": "TEXT",
                "finish_reason": "TEXT",
                "score": "REAL",
                "max_score": "REAL",
                "percent": "INTEGER",
                "grade_label": "TEXT",
                "passed": "INTEGER",
            },
            "answers": {
                "question_type": "TEXT",
                "section_title": "TEXT",
                "correct_answer": "TEXT",
                "given_answer": "TEXT",
                "explanation": "TEXT",
                "raw_answer": "TEXT",
                "is_correct": "INTEGER",
                "score": "REAL",
                "max_score": "REAL",
                "manual_override": "INTEGER NOT NULL DEFAULT 0",
            },
        }
        for table, columns in additions.items():
            existing = {
                row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")
            }
            for name, sql_type in columns.items():
                if name not in existing:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
        self.conn.commit()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self.conn.close()

    @property
    def is_open(self) -> bool:
        """Qt уничтожает окна уже после выхода из ``app.exec()``, когда база
        закрыта. Обработчики сигналов обязаны это проверять."""
        return not self._closed

    # ------------------------------------------------------------- сотрудники

    @staticmethod
    def _name_key(full_name: str) -> str:
        """Ключ сравнения ФИО: регистр и лишние пробелы не важны, ё = е."""
        return " ".join(full_name.split()).casefold().replace("ё", "е")

    def add_employee(self, full_name: str, position: str = "", department: str = "") -> int:
        full_name = " ".join(full_name.split())
        cur = self.conn.execute(
            "INSERT INTO employees(full_name, name_key, position, department) "
            "VALUES (?, ?, ?, ?)",
            (full_name, self._name_key(full_name), position.strip(), department.strip()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def list_employees(self, active_only: bool = True) -> list[Employee]:
        sql = "SELECT id, full_name, position, department FROM employees"
        if active_only:
            sql += " WHERE active = 1"
        sql += " ORDER BY name_key"
        return [
            Employee(r["id"], r["full_name"], r["position"] or "", r["department"] or "")
            for r in self.conn.execute(sql)
        ]

    def find_employee(self, full_name: str) -> Employee | None:
        row = self.conn.execute(
            "SELECT id, full_name, position, department FROM employees WHERE name_key = ?",
            (self._name_key(full_name),),
        ).fetchone()
        if row is None:
            return None
        return Employee(row["id"], row["full_name"], row["position"] or "", row["department"] or "")

    def get_or_create_employee(self, full_name: str) -> int:
        found = self.find_employee(full_name)
        return found.id if found else self.add_employee(full_name)

    def update_employee(
        self, employee_id: int, full_name: str, position: str = "", department: str = ""
    ) -> None:
        full_name = " ".join(full_name.split())
        self.conn.execute(
            "UPDATE employees SET full_name = ?, name_key = ?, position = ?, "
            "department = ? WHERE id = ?",
            (
                full_name,
                self._name_key(full_name),
                position.strip(),
                department.strip(),
                employee_id,
            ),
        )
        self.conn.commit()

    def set_employee_active(self, employee_id: int, active: bool) -> None:
        """Только флаг: физическое удаление уносит историю аттестаций."""
        self.conn.execute(
            "UPDATE employees SET active = ? WHERE id = ?", (int(active), employee_id)
        )
        self.conn.commit()

    def deactivate_employee(self, employee_id: int) -> None:
        self.set_employee_active(employee_id, False)

    def is_employee_active(self, employee_id: int) -> bool:
        row = self.conn.execute(
            "SELECT active FROM employees WHERE id = ?", (employee_id,)
        ).fetchone()
        return bool(row and row["active"])

    # ---------------------------------------------------------------- попытки

    def save_attempt(
        self,
        test: Test,
        plan: AttemptPlan,
        answers: dict[str, dict | None],
        result: AttemptResult,
        employee_name: str,
        employee_id: int | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
        finish_reason: FinishReason = FinishReason.COMPLETED,
    ) -> int:
        now = datetime.now().replace(microsecond=0).isoformat()
        by_question = {qr.question_id: qr for qr in result.per_question}

        with self.conn:  # одна транзакция: попытка и ответы либо есть, либо нет
            cur = self.conn.execute(
                """
                INSERT INTO attempts(
                    employee_id, employee_name, test_id, test_title, test_revision,
                    started_at, finished_at, finish_reason, seed, plan, scale,
                    score, max_score, percent, grade_label, passed, needs_review
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    employee_id,
                    employee_name,
                    test.id,
                    test.title,
                    test.revision,
                    started_at or now,
                    finished_at or now,
                    finish_reason.value,
                    plan.seed,
                    json.dumps(plan.to_dict(), ensure_ascii=False),
                    json.dumps(_scale_to_dict(test.grading.scale), ensure_ascii=False),
                    result.score,
                    result.max_score,
                    result.percent,
                    result.grade_label,
                    int(result.passed),
                    int(result.needs_review),
                ),
            )
            attempt_id = int(cur.lastrowid)

            sections = {s.id: s.title for s in test.sections}
            rows = []
            for index, qid in enumerate(plan.question_ids, start=1):
                q = test.question_by_id(qid)
                qr = by_question.get(qid)
                raw = answers.get(qid)
                rows.append(
                    (
                        attempt_id,
                        qid,
                        q.text if q else "",
                        str(q.type) if q else None,
                        sections.get(q.section_id) if q else None,
                        describe_correct(q) if q else None,
                        describe_given(q, raw) if q else None,
                        q.explanation if q else None,
                        index,
                        json.dumps(raw, ensure_ascii=False) if raw is not None else None,
                        None if qr is None or qr.is_correct is None else int(qr.is_correct),
                        qr.score if qr else 0.0,
                        qr.max_score if qr else 0.0,
                    )
                )
            self.conn.executemany(
                """
                INSERT INTO answers(
                    attempt_id, question_id, question_text, question_type,
                    section_title, correct_answer, given_answer, explanation,
                    shown_index, raw_answer, is_correct, score, max_score
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                rows,
            )

        return attempt_id

    def list_attempts(
        self,
        test_id: str | None = None,
        employee_id: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        only_failed: bool = False,
        limit: int = 2000,
    ) -> list[sqlite3.Row]:
        sql = (
            "SELECT id, employee_id, employee_name, test_id, test_title, "
            "test_revision, started_at, finished_at, finish_reason, score, "
            "max_score, percent, grade_label, passed, needs_review FROM attempts"
        )
        where: list[str] = []
        params: list = []

        if test_id:
            where.append("test_id = ?")
            params.append(test_id)
        if employee_id is not None:
            where.append("employee_id = ?")
            params.append(employee_id)
        if date_from:
            where.append("started_at >= ?")
            params.append(date_from)
        if date_to:
            # Дата «по» включительно: сравниваем с концом суток.
            where.append("started_at <= ?")
            params.append(f"{date_to}T23:59:59")
        if only_failed:
            where.append("passed = 0")

        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return list(self.conn.execute(sql, params))

    def list_tests(self) -> list[sqlite3.Row]:
        """Тесты, по которым есть попытки — для фильтра в отчётах."""
        return list(
            self.conn.execute(
                "SELECT test_id, test_title, COUNT(*) AS attempts FROM attempts "
                "GROUP BY test_id, test_title ORDER BY test_title"
            )
        )

    def delete_attempt(self, attempt_id: int) -> None:
        """Ответы удаляются каскадом (см. FOREIGN KEY в схеме)."""
        with self.conn:
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.conn.execute("DELETE FROM attempts WHERE id = ?", (attempt_id,))

    def section_totals(self, attempt_id: int) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT COALESCE(section_title, 'Вне разделов') AS section, "
                "SUM(score) AS score, SUM(max_score) AS max_score, COUNT(*) AS questions "
                "FROM answers WHERE attempt_id = ? GROUP BY section ORDER BY section",
                (attempt_id,),
            )
        )

    def section_totals_for(self, attempt_ids: list[int]) -> list[sqlite3.Row]:
        """Сводка по разделам сразу для нескольких попыток."""
        if not attempt_ids:
            return []
        placeholders = ",".join("?" * len(attempt_ids))
        return list(
            self.conn.execute(
                "SELECT COALESCE(section_title, 'Вне разделов') AS section, "
                "SUM(score) AS score, SUM(max_score) AS max_score, "
                "SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct, "
                "COUNT(*) AS answers "
                f"FROM answers WHERE attempt_id IN ({placeholders}) "
                "GROUP BY section ORDER BY section",
                attempt_ids,
            )
        )

    def hardest_questions(self, attempt_ids: list[int], limit: int = 20) -> list[sqlite3.Row]:
        """Вопросы с наибольшей долей ошибок — самая полезная часть отчёта."""
        if not attempt_ids:
            return []
        placeholders = ",".join("?" * len(attempt_ids))
        return list(
            self.conn.execute(
                "SELECT question_text, COALESCE(section_title, '') AS section, "
                "COUNT(*) AS asked, "
                "SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct "
                f"FROM answers WHERE attempt_id IN ({placeholders}) "
                "GROUP BY question_id, question_text, section "
                "HAVING asked > 0 ORDER BY (CAST(correct AS REAL) / asked) ASC, asked DESC "
                "LIMIT ?",
                attempt_ids + [limit],
            )
        )

    def list_attempts_to_review(self) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT id, employee_name, test_title, started_at, percent, "
                "grade_label FROM attempts WHERE needs_review = 1 ORDER BY id DESC"
            )
        )

    def count_attempts_to_review(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM attempts WHERE needs_review = 1"
        ).fetchone()
        return int(row["n"])

    def review_answer(self, answer_id: int, accepted: bool) -> int:
        """Решение проверяющего по одному ответу. Возвращает id попытки."""
        row = self.conn.execute(
            "SELECT attempt_id, max_score FROM answers WHERE id = ?", (answer_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Ответ {answer_id} не найден")

        self.conn.execute(
            "UPDATE answers SET is_correct = ?, score = ?, manual_override = 1 "
            "WHERE id = ?",
            (int(accepted), row["max_score"] if accepted else 0.0, answer_id),
        )
        self.conn.commit()
        self.recalculate_attempt(row["attempt_id"])
        return int(row["attempt_id"])

    def recalculate_attempt(self, attempt_id: int) -> sqlite3.Row:
        """Пересчёт баллов, процента, оценки и признака «сдал» одной транзакцией.

        Иначе легко получить попытку с 90 % и меткой «Не сдал»: обновили баллы,
        а оценку забыли.
        """
        totals = self.conn.execute(
            "SELECT COALESCE(SUM(score), 0) AS score, "
            "COALESCE(SUM(max_score), 0) AS max_score, "
            "SUM(CASE WHEN is_correct IS NULL THEN 1 ELSE 0 END) AS pending "
            "FROM answers WHERE attempt_id = ?",
            (attempt_id,),
        ).fetchone()

        score = float(totals["score"])
        max_score = float(totals["max_score"])
        percent = to_percent(score, max_score)
        scale = self._scale_of(attempt_id)
        threshold = scale.grade(percent)

        with self.conn:
            self.conn.execute(
                "UPDATE attempts SET score = ?, max_score = ?, percent = ?, "
                "grade_label = ?, passed = ?, needs_review = ? WHERE id = ?",
                (
                    score,
                    max_score,
                    percent,
                    threshold.label,
                    int(threshold.passed),
                    int(bool(totals["pending"])),
                    attempt_id,
                ),
            )
        return self.get_attempt(attempt_id)

    def _scale_of(self, attempt_id: int) -> Scale:
        row = self.conn.execute(
            "SELECT scale FROM attempts WHERE id = ?", (attempt_id,)
        ).fetchone()
        if row is None or not row["scale"]:
            # Попытка из версии без снимка шкалы — считаем по умолчанию.
            return Scale.default_pass_fail()
        return _scale_from_dict(json.loads(row["scale"]))

    def get_attempt(self, attempt_id: int) -> sqlite3.Row:
        return self.conn.execute(
            "SELECT * FROM attempts WHERE id = ?", (attempt_id,)
        ).fetchone()

    def get_answers(self, attempt_id: int) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT * FROM answers WHERE attempt_id = ? ORDER BY shown_index",
                (attempt_id,),
            )
        )

    # ------------------------------------------------------------------ бэкап

    def backup(self, keep: int = BACKUP_KEEP, force: bool = False) -> Path:
        """Копия базы раз в сутки. База результатов существует в одном экземпляре
        на одном ПК — случайное удаление уносит годовую аттестацию.

        ``force`` — копия по требованию пользователя, с точным временем в имени.
        """
        if force:
            target = backup_dir() / f"results_{datetime.now():%Y%m%d_%H%M%S}.db"
        else:
            target = backup_dir() / f"results_{date.today():%Y%m%d}.db"
            if target.exists():
                return target

        dest = sqlite3.connect(str(target))
        try:
            self.conn.backup(dest)  # консистентная копия даже при открытой БД
        finally:
            dest.close()

        backups = sorted(backup_dir().glob("results_*.db"))
        for old in backups[:-keep]:
            old.unlink(missing_ok=True)
        return target
