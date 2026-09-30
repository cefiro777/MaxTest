"""Крупная плитка действия для главного экрана.

Не ``QPushButton``: у кнопки текст не переносится, а обрезается многоточием —
пояснение под заголовком просто не помещалось. Здесь заголовок и пояснение —
отдельные QLabel с переносом строк.

Внешне и по API ведёт себя как кнопка: ``clicked``, ``setEnabled``, ``text``.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class Tile(QFrame):
    clicked = pyqtSignal()

    def __init__(
        self,
        caption: str,
        hint: str = "",
        primary: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("class", "tilePrimary" if primary else "tile")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(78)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(3)

        self._caption = QLabel(caption)
        self._caption.setProperty("class", "tileCaption")
        self._caption.setWordWrap(True)
        self._hint = QLabel(hint)
        self._hint.setProperty("class", "tileHint")
        self._hint.setWordWrap(True)
        self._hint.setVisible(bool(hint))

        layout.addWidget(self._caption)
        layout.addWidget(self._hint)

    # Поведение кнопки -----------------------------------------------------

    def mouseReleaseEvent(self, event) -> None:
        if self.isEnabled() and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def setText(self, caption: str, hint: str = "") -> None:
        self._caption.setText(caption)
        self._hint.setText(hint)
        self._hint.setVisible(bool(hint))

    def text(self) -> str:
        return f"{self._caption.text()}\n{self._hint.text()}".strip()

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ArrowCursor
        )
