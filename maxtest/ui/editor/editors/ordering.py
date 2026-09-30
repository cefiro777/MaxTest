"""Редактор вопроса «упорядочивание».

Порядок пунктов в списке = правильный порядок. При прохождении список
перемешивается, поэтому автору не нужно ничего задавать отдельно.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ....core.models import OrderItem, Question
from .base import BaseQuestionEditor


class OrderingEditor(BaseQuestionEditor):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        hint = QLabel(
            "Пункты в правильном порядке (сверху вниз). "
            "Двойной клик — изменить текст, перетаскивание — поменять местами:"
        )
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        layout.addWidget(hint)

        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.itemChanged.connect(self._on_item_changed)
        self.list.model().rowsMoved.connect(self._on_rows_moved)
        layout.addWidget(self.list)

        buttons = QHBoxLayout()
        add = QPushButton("+ Пункт")
        add.clicked.connect(self.add_item)
        remove = QPushButton("Удалить пункт")
        remove.clicked.connect(self.remove_item)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addStretch(1)

    def _fill(self, question: Question | None) -> None:
        self.list.clear()
        if question is None:
            return
        if question.order is None:
            question.order = []

        for item in question.order:
            widget_item = QListWidgetItem(item.text)
            widget_item.setFlags(widget_item.flags() | Qt.ItemFlag.ItemIsEditable)
            widget_item.setData(Qt.ItemDataRole.UserRole, item.id)
            self.list.addItem(widget_item)

    def add_item(self) -> None:
        if self._question is None:
            return
        if self._question.order is None:
            self._question.order = []
        self._question.order.append(OrderItem(text="Новый пункт"))
        self.load(self._question)
        self.notify()

    def remove_item(self) -> None:
        if self._question is None or not self._question.order:
            return
        row = self.list.currentRow()
        if row < 0 or row >= len(self._question.order):
            return
        del self._question.order[row]
        self.load(self._question)
        self.notify()

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if self._loading or self._question is None or not self._question.order:
            return
        item_id = item.data(Qt.ItemDataRole.UserRole)
        for entry in self._question.order:
            if entry.id == item_id:
                entry.text = item.text()
                break
        self.notify()

    def _on_rows_moved(self, *args) -> None:
        """Перетаскивание меняет порядок — пересобираем список по id виджетов."""
        if self._loading or self._question is None or not self._question.order:
            return
        by_id = {i.id: i for i in self._question.order}
        new_order = []
        for row in range(self.list.count()):
            item_id = self.list.item(row).data(Qt.ItemDataRole.UserRole)
            if item_id in by_id:
                new_order.append(by_id.pop(item_id))
        new_order.extend(by_id.values())
        self._question.order = new_order
        self.notify()
