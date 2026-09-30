"""Редактор вопроса «установление соответствия».

Автор вводит пары в правильном виде (левая ↔ правая), а перемешивание правых
частей происходит при прохождении. В файле теста порядок всегда правильный —
так вопрос читается глазами при отладке.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ....core.models import MatchPair, Question
from .base import BaseQuestionEditor


class MatchingEditor(BaseQuestionEditor):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        hint = QLabel("Пары «вопрос — ответ». При прохождении правая колонка перемешивается:")
        hint.setObjectName("hint")
        layout.addWidget(hint)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Левая часть", "Правая часть"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table)

        buttons = QHBoxLayout()
        add = QPushButton("+ Пара")
        add.clicked.connect(self.add_pair)
        remove = QPushButton("Удалить пару")
        remove.clicked.connect(self.remove_pair)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addStretch(1)

    def _fill(self, question: Question | None) -> None:
        self.table.setRowCount(0)
        if question is None:
            return
        if question.pairs is None:
            question.pairs = []

        self.table.setRowCount(len(question.pairs))
        for row, pair in enumerate(question.pairs):
            self.table.setItem(row, 0, QTableWidgetItem(pair.left))
            self.table.setItem(row, 1, QTableWidgetItem(pair.right))

    def add_pair(self) -> None:
        if self._question is None:
            return
        if self._question.pairs is None:
            self._question.pairs = []
        self._question.pairs.append(MatchPair())
        self.load(self._question)
        self.notify()

    def remove_pair(self) -> None:
        if self._question is None or not self._question.pairs:
            return
        row = self.table.currentRow()
        if row < 0 or row >= len(self._question.pairs):
            return
        del self._question.pairs[row]
        self.load(self._question)
        self.notify()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading or self._question is None or not self._question.pairs:
            return
        if item.row() >= len(self._question.pairs):
            return
        pair = self._question.pairs[item.row()]
        if item.column() == 0:
            pair.left = item.text()
        else:
            pair.right = item.text()
        self.notify()
