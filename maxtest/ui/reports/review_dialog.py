"""Ручная проверка текстовых ответов.

Слева — попытки, ожидающие проверки, справа — ответы этой попытки. Решение
проверяющего сразу пересчитывает балл, процент и оценку: попытка с 90 % и
меткой «Не сдал» — типичный результат забытого пересчёта.
"""

from __future__ import annotations

import json

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.storage import Storage

COLUMNS = ("Вопрос", "Ответ сотрудника", "Эталон", "Балл", "Решение")


class ReviewDialog(QDialog):
    def __init__(self, storage: Storage, parent=None) -> None:
        super().__init__(parent)
        self.storage = storage
        self.setWindowTitle("Проверка ответов")
        self.resize(1100, 620)

        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Попытки, ожидающие проверки:"))
        self.attempts = QListWidget()
        self.attempts.currentRowChanged.connect(self._on_attempt_selected)
        left_layout.addWidget(self.attempts)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.summary = QLabel("Выберите попытку слева")
        self.summary.setObjectName("sectionTitle")
        right_layout.addWidget(self.summary)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        right_layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        accept = QPushButton("✓ Засчитать")
        accept.setProperty("class", "success")
        accept.clicked.connect(lambda: self.review(True))
        reject = QPushButton("✗ Не засчитывать")
        reject.setProperty("class", "danger")
        reject.clicked.connect(lambda: self.review(False))
        buttons.addWidget(accept)
        buttons.addWidget(reject)
        buttons.addStretch(1)
        close = QPushButton("Закрыть")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        right_layout.addLayout(buttons)

        splitter.addWidget(right)
        splitter.setSizes([320, 780])
        layout.addWidget(splitter)

        self.reload_attempts()

    # ------------------------------------------------------------------ данные

    def reload_attempts(self) -> None:
        self.attempts.clear()
        rows = self.storage.list_attempts_to_review()
        for row in rows:
            item = QListWidgetItem(
                f"{row['employee_name']}\n{row['test_title']} · "
                f"{(row['started_at'] or '').replace('T', ' ')}"
            )
            item.setData(Qt.ItemDataRole.UserRole, row["id"])
            self.attempts.addItem(item)

        if rows:
            self.attempts.setCurrentRow(0)
        else:
            self.table.setRowCount(0)
            self.summary.setText("Непроверенных ответов нет")

    @property
    def current_attempt_id(self) -> int | None:
        item = self.attempts.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_attempt_selected(self, row: int) -> None:
        attempt_id = self.current_attempt_id
        if attempt_id is None:
            return
        self._load_answers(attempt_id)

    def _load_answers(self, attempt_id: int) -> None:
        attempt = self.storage.get_attempt(attempt_id)
        answers = [a for a in self.storage.get_answers(attempt_id) if a["is_correct"] is None
                   or a["manual_override"]]

        self.summary.setText(
            f"{attempt['employee_name']} · {attempt['test_title']} · "
            f"{attempt['score']:.2f} из {attempt['max_score']:.2f} · "
            f"{attempt['percent']}% · {attempt['grade_label']}"
        )

        self.table.setRowCount(len(answers))
        for row, answer in enumerate(answers):
            given = ""
            if answer["raw_answer"]:
                try:
                    given = json.loads(answer["raw_answer"]).get("text", "")
                except (ValueError, AttributeError):
                    given = answer["raw_answer"]

            verdict = "ждёт проверки"
            if answer["is_correct"] is not None:
                verdict = "засчитан" if answer["is_correct"] else "не засчитан"
                if answer["manual_override"]:
                    verdict += " (вручную)"

            values = (
                answer["question_text"],
                given or "— нет ответа —",
                answer["correct_answer"] or "",
                f"{answer['score']:.2f} / {answer['max_score']:.2f}",
                verdict,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, answer["id"])
                self.table.setItem(row, column, item)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )

    # ---------------------------------------------------------------- действия

    def review(self, accepted: bool) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        if item is None:
            return
        answer_id = item.data(Qt.ItemDataRole.UserRole)
        attempt_id = self.storage.review_answer(answer_id, accepted)

        # Пока в попытке остаются непроверенные ответы, она остаётся в списке.
        still_pending = any(
            a["is_correct"] is None for a in self.storage.get_answers(attempt_id)
        )
        self._load_answers(attempt_id)
        if not still_pending:
            self.reload_attempts()
