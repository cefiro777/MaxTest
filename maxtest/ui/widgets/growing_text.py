"""Многострочное поле ввода, которое растёт по высоте под текст.

Причина появления: обычный ``QLineEdit`` физически однострочный — длинный
ответ уходит вправо под горизонтальный ползунок, и человек видит только хвост
своей фразы. А ``QPlainTextEdit`` с фиксированной высотой при переполнении даёт
внутренний вертикальный ползунок, что тоже неудобно.

Это поле:
* переносит текст по ширине виджета (``LineWrapMode.WidgetWidth``), а ширина
  задаётся раскладкой родителя — то есть подстраивается под размер окна;
* растёт по высоте под содержимое от ``min_lines`` до ``max_lines`` строк;
* по достижении потолка включает вертикальный ползунок, чтобы очень длинный
  ответ не растянул окно до бесконечности;
* Enter вставляет перенос строки — как в любом текстовом редакторе.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPlainTextEdit, QWidget


class GrowingTextEdit(QPlainTextEdit):
    def __init__(
        self,
        text: str = "",
        min_lines: int = 2,
        max_lines: int = 16,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._min_lines = max(1, min_lines)
        self._max_lines = max(self._min_lines, max_lines)

        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setSizeAdjustPolicy(
            QPlainTextEdit.SizeAdjustPolicy.AdjustToContents
        )
        if text:
            self.setPlainText(text)

        # Пересчёт высоты и при вводе, и при переносе (перенос меняет число
        # строк без изменения текста, поэтому одного textChanged мало).
        self.textChanged.connect(self._adjust_height)
        self.document().documentLayout().documentSizeChanged.connect(
            lambda _size: self._adjust_height()
        )
        self._adjust_height()

    def _chrome(self) -> int:
        """Всё, что занимает место помимо самих строк текста."""
        margins = int(self.document().documentMargin() * 2)
        frame = self.frameWidth() * 2
        content = self.contentsMargins()
        return margins + frame + content.top() + content.bottom()

    def _visual_lines(self) -> int:
        """Число строк на экране с учётом переноса длинных строк.

        Считаем по блокам, а не через ``documentSize()``: у plain-text-раскладки
        Qt высота документа выражается то в строках, то в пикселях в зависимости
        от платформы, а ``layout().lineCount()`` одинаково даёт число визуальных
        строк — включая перенесённые по ширине.
        """
        total = 0
        block = self.document().firstBlock()
        while block.isValid():
            count = block.layout().lineCount()
            total += count if count > 0 else 1
            block = block.next()
        return max(1, total)

    def _adjust_height(self) -> None:
        line = self.fontMetrics().lineSpacing()
        lines = max(self._min_lines, min(self._max_lines, self._visual_lines()))
        self.setFixedHeight(int(lines * line + self._chrome()))

    def resizeEvent(self, event) -> None:
        # Смена ширины меняет перенос — высоту нужно пересчитать. Делать это
        # прямо в resizeEvent нельзя (рекурсия по геометрии), поэтому откладываем.
        super().resizeEvent(event)
        from PyQt6.QtCore import QTimer

        QTimer.singleShot(0, self._adjust_height)
