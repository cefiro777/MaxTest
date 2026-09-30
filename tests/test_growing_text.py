"""Растущее текстовое поле: перенос по ширине и рост высоты."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from maxtest.ui.widgets.growing_text import GrowingTextEdit  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_wraps_by_width_not_horizontal_scroll(qapp):
    """Длинный текст переносится, а не уходит под горизонтальный ползунок."""
    field = GrowingTextEdit(min_lines=2, max_lines=10)
    assert field.lineWrapMode() == GrowingTextEdit.LineWrapMode.WidgetWidth
    assert (
        field.horizontalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )


def test_grows_with_more_text(qapp):
    field = GrowingTextEdit(min_lines=2, max_lines=12)
    field.resize(300, 100)
    field.show()  # без показа документ не раскладывается

    one_line = field.height()
    field.setPlainText("\n".join(f"строка {i}" for i in range(6)))
    qapp.processEvents()
    assert field.height() > one_line
    field.hide()


def test_respects_min_lines(qapp):
    small = GrowingTextEdit(min_lines=1, max_lines=10)
    big = GrowingTextEdit(min_lines=5, max_lines=10)
    assert big.height() > small.height()


def test_caps_at_max_lines(qapp):
    field = GrowingTextEdit(min_lines=2, max_lines=4)
    field.resize(300, 100)
    field.show()
    field.setPlainText("\n".join(f"строка {i}" for i in range(40)))
    qapp.processEvents()

    line = field.fontMetrics().lineSpacing()
    # Высота не должна расти бесконечно: потолок ~ max_lines строк плюс рамки.
    assert field.height() <= 4 * line + field._chrome() + 2
    field.hide()


def test_enter_inserts_newline(qapp):
    """В многострочном поле Enter добавляет перенос, а не отправляет форму."""
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import QEvent

    field = GrowingTextEdit()
    field.setPlainText("первая")
    field.moveCursor(field.textCursor().MoveOperation.End)
    event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier, "\r"
    )
    field.keyPressEvent(event)
    field.insertPlainText("вторая")
    assert field.toPlainText().count("\n") == 1


def test_reflow_on_resize_changes_height(qapp):
    """Сужение поля увеличивает число строк, значит и высоту."""
    field = GrowingTextEdit(min_lines=1, max_lines=20)
    field.show()
    field.resize(600, 80)
    field.setPlainText(
        "довольно длинная строка текста, которая на широком поле уместится "
        "в одну строку, а на узком переносится на несколько"
    )
    qapp.processEvents()
    wide = field.height()

    field.resize(220, 80)
    qapp.processEvents()
    qapp.processEvents()  # resizeEvent откладывает пересчёт через singleShot
    assert field.height() >= wide
    field.hide()
