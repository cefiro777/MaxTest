"""Разбор одной попытки: что спросили, что ответили, что было верно.

Всё берётся из снимков в базе, а не из файла ``.qtest``: тест мог измениться
или вовсе исчезнуть, а протокол обязан показывать то, что человек видел.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ...core.storage import Storage

COLUMNS = ("№", "Раздел", "Вопрос", "Ответ сотрудника", "Правильный ответ", "Балл", "Итог")


class AttemptDialog(QDialog):
    def __init__(self, storage: Storage, attempt_id: int, parent=None) -> None:
        super().__init__(parent)
        self.storage = storage
        self.attempt_id = attempt_id
        self.setWindowTitle("Разбор попытки")
        self.resize(1100, 660)

        layout = QVBoxLayout(self)

        attempt = storage.get_attempt(attempt_id)
        header = QLabel(
            f"<h3>{attempt['employee_name']}</h3>"
            f"{attempt['test_title']} (ред. {attempt['test_revision']}) · "
            f"{(attempt['started_at'] or '').replace('T', ' ')[:16]}<br>"
            f"Баллы: <b>{attempt['score']:.2f}</b> из {attempt['max_score']:.2f} · "
            f"Результат: <b>{attempt['percent']}%</b> · "
            f"Оценка: <b>{attempt['grade_label']}</b>"
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        sections = storage.section_totals(attempt_id)
        if len(sections) > 1:
            parts = []
            for row in sections:
                max_score = row["max_score"] or 0
                percent = round((row["score"] or 0) / max_score * 100) if max_score else 0
                parts.append(f"{row['section']}: {percent}%")
            by_section = QLabel("По разделам — " + " · ".join(parts))
            by_section.setWordWrap(True)
            by_section.setObjectName("hint")
            layout.addWidget(by_section)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setWordWrap(True)
        layout.addWidget(self.table, 1)

        self.explanation = QLabel()
        self.explanation.setWordWrap(True)
        self.explanation.setObjectName("hint")
        layout.addWidget(self.explanation)
        self.table.currentCellChanged.connect(self._on_row_changed)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton("Закрыть")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self._load()

    def _load(self) -> None:
        self.answers = self.storage.get_answers(self.attempt_id)
        self.table.setRowCount(len(self.answers))

        for row, answer in enumerate(self.answers):
            if answer["is_correct"] is None:
                verdict = "ждёт проверки"
            elif answer["is_correct"]:
                verdict = "верно"
            elif (answer["score"] or 0) > 0:
                verdict = "частично"
            else:
                verdict = "неверно"

            values = (
                str(answer["shown_index"] or row + 1),
                answer["section_title"] or "",
                answer["question_text"],
                answer["given_answer"] or "— нет ответа —",
                answer["correct_answer"] or "",
                f"{answer['score']:.2f} / {answer['max_score']:.2f}",
                verdict,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if answer["is_correct"] == 0:
                    item.setForeground(Qt.GlobalColor.darkRed)
                elif answer["is_correct"] == 1:
                    item.setForeground(Qt.GlobalColor.darkGreen)
                self.table.setItem(row, column, item)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        if self.answers:
            self.table.setCurrentCell(0, 0)

    def _on_row_changed(self, row: int, *args) -> None:
        if 0 <= row < len(self.answers):
            explanation = self.answers[row]["explanation"] or ""
            self.explanation.setText(f"Пояснение: {explanation}" if explanation else "")
