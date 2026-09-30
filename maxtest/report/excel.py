"""Выгрузка результатов в Excel.

Excel, а не PDF: openpyxl работает с кириллицей из коробки, кадровику удобнее
получить таблицу, которую можно отсортировать, а стандартные шрифты reportlab
кириллицу не содержат и дают квадратики без явного подключения TTF.

Модуль ничего не знает про Qt — его можно вызвать и из скрипта.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from ..core.storage import Storage

HEADER_FONT = Font(bold=True, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="4F6228")
FAIL_FILL = PatternFill("solid", fgColor="F8CBAD")
PASS_FILL = PatternFill("solid", fgColor="E2EFDA")

#: Ширина колонки считается вручную: openpyxl не умеет auto-fit, а отчёт
#: со слипшимися колонками кадровик открывать не станет.
MIN_WIDTH = 9
MAX_WIDTH = 70


@dataclass
class ReportStats:
    attempts: int = 0
    passed: int = 0
    failed: int = 0
    average_percent: float = 0.0


def export_attempts(storage: Storage, attempts: list[sqlite3.Row], path: str | Path) -> Path:
    """Пишет книгу из трёх листов: сводная, по вопросам, по разделам."""
    path = Path(path)
    if path.suffix.lower() != ".xlsx":
        path = path.with_suffix(".xlsx")

    attempt_ids = [row["id"] for row in attempts]
    workbook = Workbook()

    _write_summary(workbook.active, attempts)
    _write_details(workbook.create_sheet("По вопросам"), storage, attempts)
    _write_sections(workbook.create_sheet("По разделам"), storage, attempt_ids)
    _write_hardest(workbook.create_sheet("Сложные вопросы"), storage, attempt_ids)

    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    return path


def stats_of(attempts: list[sqlite3.Row]) -> ReportStats:
    if not attempts:
        return ReportStats()
    passed = sum(1 for a in attempts if a["passed"])
    percents = [a["percent"] or 0 for a in attempts]
    return ReportStats(
        attempts=len(attempts),
        passed=passed,
        failed=len(attempts) - passed,
        average_percent=round(sum(percents) / len(percents), 1),
    )


# --------------------------------------------------------------------------
# Листы
# --------------------------------------------------------------------------


def _write_summary(sheet, attempts: list[sqlite3.Row]) -> None:
    sheet.title = "Сводная"
    stats = stats_of(attempts)

    sheet.append(["Результаты тестирования"])
    sheet["A1"].font = Font(bold=True, size=14)
    sheet.append([f"Сформировано: {datetime.now():%d.%m.%Y %H:%M}"])
    sheet.append(
        [
            f"Попыток: {stats.attempts}",
            f"Сдали: {stats.passed}",
            f"Не сдали: {stats.failed}",
            f"Средний результат: {stats.average_percent}%",
        ]
    )
    sheet.append([])

    headers = (
        "Сотрудник", "Тест", "Ред.", "Дата", "Баллы", "Максимум",
        "Процент", "Оценка", "Итог", "Примечание",
    )
    _append_header(sheet, headers)

    for row in attempts:
        sheet.append(
            [
                row["employee_name"],
                row["test_title"],
                row["test_revision"],
                _format_dt(row["started_at"]),
                round(row["score"] or 0, 2),
                round(row["max_score"] or 0, 2),
                row["percent"],
                row["grade_label"] or "",
                "Сдал" if row["passed"] else "Не сдал",
                _note(row),
            ]
        )
        fill = PASS_FILL if row["passed"] else FAIL_FILL
        for column in range(1, len(headers) + 1):
            sheet.cell(row=sheet.max_row, column=column).fill = fill

    sheet.freeze_panes = "A6"
    _autosize(sheet)


def _write_details(sheet, storage: Storage, attempts: list[sqlite3.Row]) -> None:
    headers = (
        "Сотрудник", "Тест", "Дата", "№", "Раздел", "Вопрос",
        "Ответ сотрудника", "Правильный ответ", "Верно", "Балл", "Макс.",
    )
    _append_header(sheet, headers)

    for attempt in attempts:
        for answer in storage.get_answers(attempt["id"]):
            if answer["is_correct"] is None:
                verdict = "ждёт проверки"
            else:
                verdict = "да" if answer["is_correct"] else "нет"
            sheet.append(
                [
                    attempt["employee_name"],
                    attempt["test_title"],
                    _format_dt(attempt["started_at"]),
                    answer["shown_index"],
                    answer["section_title"] or "",
                    answer["question_text"],
                    answer["given_answer"] or "",
                    answer["correct_answer"] or "",
                    verdict,
                    round(answer["score"] or 0, 2),
                    round(answer["max_score"] or 0, 2),
                ]
            )
            if answer["is_correct"] == 0:
                for column in range(1, len(headers) + 1):
                    sheet.cell(row=sheet.max_row, column=column).fill = FAIL_FILL

    sheet.freeze_panes = "A2"
    _autosize(sheet)


def _write_sections(sheet, storage: Storage, attempt_ids: list[int]) -> None:
    headers = ("Раздел", "Баллы", "Максимум", "Процент", "Верных ответов", "Всего ответов")
    _append_header(sheet, headers)

    for row in storage.section_totals_for(attempt_ids):
        max_score = row["max_score"] or 0
        percent = round((row["score"] or 0) / max_score * 100) if max_score else 0
        sheet.append(
            [
                row["section"],
                round(row["score"] or 0, 2),
                round(max_score, 2),
                percent,
                row["correct"],
                row["answers"],
            ]
        )

    sheet.freeze_panes = "A2"
    _autosize(sheet)


def _write_hardest(sheet, storage: Storage, attempt_ids: list[int]) -> None:
    headers = ("Вопрос", "Раздел", "Задавался", "Верных ответов", "Доля верных, %")
    _append_header(sheet, headers)

    for row in storage.hardest_questions(attempt_ids):
        asked = row["asked"] or 0
        share = round((row["correct"] or 0) / asked * 100) if asked else 0
        sheet.append([row["question_text"], row["section"], asked, row["correct"], share])
        if share < 50:
            for column in range(1, len(headers) + 1):
                sheet.cell(row=sheet.max_row, column=column).fill = FAIL_FILL

    sheet.freeze_panes = "A2"
    _autosize(sheet)


# --------------------------------------------------------------------------
# Оформление
# --------------------------------------------------------------------------


def _append_header(sheet, headers) -> None:
    sheet.append(list(headers))
    for column in range(1, len(headers) + 1):
        cell = sheet.cell(row=sheet.max_row, column=column)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _autosize(sheet) -> None:
    for column in sheet.columns:
        longest = max(
            (len(str(cell.value)) for cell in column if cell.value is not None), default=0
        )
        letter = get_column_letter(column[0].column)
        sheet.column_dimensions[letter].width = max(MIN_WIDTH, min(MAX_WIDTH, longest + 2))


def _format_dt(value: str | None) -> str:
    if not value:
        return ""
    return value.replace("T", " ")[:16]


def _note(row: sqlite3.Row) -> str:
    notes = []
    if row["needs_review"]:
        notes.append("требует проверки")
    if row["finish_reason"] == "timeout":
        notes.append("время вышло")
    elif row["finish_reason"] == "aborted":
        notes.append("прервано")
    return ", ".join(notes)
