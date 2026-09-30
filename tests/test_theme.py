"""Стражи оформления.

Тема не проверяется глазами при каждом изменении, поэтому здесь закреплены
вещи, которые ломаются молча: незакрытые фигурные скобки в QSS (Qt просто
игнорирует такой блок), точечные ``setStyleSheet`` в обход темы и флаг
``WA_StyledBackground`` у карточки вопроса.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from maxtest.ui import theme  # noqa: E402
from maxtest.ui.widgets.question_view import QuestionView  # noqa: E402
from maxtest.ui.widgets.tile import Tile  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_stylesheet_is_balanced():
    css = theme.stylesheet()
    assert css.count("{") == css.count("}")
    assert "{ACCENT}" not in css  # незаподставленное поле f-строки


def test_apply_sets_font_and_stylesheet(qapp):
    theme.apply(qapp)
    assert qapp.styleSheet()
    assert qapp.font().family() == theme.BASE_FONT_FAMILY


def test_no_inline_styles_outside_theme():
    """Точечные setStyleSheet превращают интерфейс в лоскутное одеяло."""
    offenders = []
    for path in (ROOT / "maxtest" / "ui").rglob("*.py"):
        if path.name == "theme.py":
            continue
        if "setStyleSheet" in path.read_text(encoding="utf-8"):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


def test_question_view_paints_background(qapp):
    """Без WA_StyledBackground подкласс QWidget игнорирует фон из QSS."""
    view = QuestionView()
    assert view.testAttribute(Qt.WidgetAttribute.WA_StyledBackground)


def test_tile_behaves_like_button(qapp):
    tile = Tile("Заголовок", "Пояснение")
    assert "Заголовок" in tile.text() and "Пояснение" in tile.text()

    fired = []
    tile.clicked.connect(lambda: fired.append(1))
    tile.setEnabled(False)
    assert tile.isEnabled() is False

    tile.setText("Новый заголовок")
    assert tile.text() == "Новый заголовок"


def test_player_uses_larger_font_than_base():
    assert theme.PLAYER_FONT_SIZE > theme.BASE_FONT_SIZE
