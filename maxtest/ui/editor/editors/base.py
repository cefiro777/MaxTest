"""Базовый класс редактора вопроса.

Общий для всех редакторов защитный механизм — флаг ``_loading``. Пока форма
заполняется программно, обработчики сигналов ничего не пишут в модель: иначе
``textChanged`` от ``setText()`` запишет значение в вопрос, который уже не
выбран. Это самый частый и самый неочевидный баг конструкторов на Qt.
"""

from __future__ import annotations

from contextlib import contextmanager

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget

from ....core.models import Question


class BaseQuestionEditor(QWidget):
    """Редактирует вопрос по месту и сообщает об изменениях сигналом."""

    changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._question: Question | None = None
        self._loading = False

    @property
    def question(self) -> Question | None:
        return self._question

    @contextmanager
    def loading(self):
        """Заполнение формы: сигналы виджетов игнорируются."""
        previous = self._loading
        self._loading = True
        try:
            yield
        finally:
            self._loading = previous

    def notify(self) -> None:
        if not self._loading:
            self.changed.emit()

    def load(self, question: Question | None) -> None:
        self._question = question
        with self.loading():
            self._fill(question)

    def _fill(self, question: Question | None) -> None:  # pragma: no cover - абстракт
        raise NotImplementedError
