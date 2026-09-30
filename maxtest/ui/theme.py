"""Оформление приложения: палитра, шрифты, единый QSS.

Все цвета и отступы задаются здесь, а не по месту в виджетах. Иначе через
полгода интерфейс превращается в лоскутное одеяло из ``setStyleSheet``, и
поменять один цвет становится невозможно.

Правила именования, на которые опирается таблица стилей:

* ``objectName`` — роль элемента: ``primaryButton``, ``dangerButton``,
  ``heroTitle``, ``card``, ``hint``, ``statusChip``;
* динамическое свойство ``class`` — вариант оформления там, где виджетов
  много и имена не подходят (например, крупные варианты ответа).
"""

from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QWidget

# --------------------------------------------------------------------------
# Палитра
# --------------------------------------------------------------------------

BG = "#F4F6F9"          # фон окна
SURFACE = "#FFFFFF"     # карточки, поля, таблицы
SURFACE_ALT = "#EFF2F6"  # чередование строк, наведение
BORDER = "#DDE2E9"
BORDER_STRONG = "#C3CBD6"

TEXT = "#1B2130"
TEXT_MUTED = "#6B7484"
TEXT_ON_ACCENT = "#FFFFFF"

ACCENT = "#2563EB"
ACCENT_HOVER = "#1D4FD8"
ACCENT_PRESSED = "#1A45BE"
ACCENT_SOFT = "#E8EFFD"

SUCCESS = "#15803D"
SUCCESS_SOFT = "#E6F4EA"
DANGER = "#B4232B"
DANGER_SOFT = "#FCEBEC"
WARNING = "#B45309"
WARNING_SOFT = "#FDF3E4"

RADIUS = 10
RADIUS_SMALL = 7

BASE_FONT_FAMILY = "Segoe UI"
BASE_FONT_SIZE = 10
#: Экран прохождения крупнее: тест проходят люди разного возраста и зрения,
#: промах мышью по мелкому варианту ответа стоит балла.
PLAYER_FONT_SIZE = 13


def apply(app: QApplication) -> None:
    """Ставит шрифт и таблицу стилей на всё приложение."""
    font = QFont(BASE_FONT_FAMILY, BASE_FONT_SIZE)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)
    app.setStyleSheet(stylesheet())


def mark(widget: QWidget, role: str) -> QWidget:
    """Помечает виджет ролью для QSS и возвращает его же (удобно в цепочках)."""
    widget.setProperty("class", role)
    return widget


def restyle(widget: QWidget) -> None:
    """Перечитывает стиль после смены свойства ``class`` у живого виджета."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def stylesheet() -> str:
    return f"""
/* ---------------------------------------------------------------- основа */
QWidget {{
    background: {BG};
    color: {TEXT};
}}
QMainWindow, QDialog {{ background: {BG}; }}

QLabel {{ background: transparent; }}
QLabel#heroTitle {{
    font-size: 30px;
    font-weight: 600;
    color: {TEXT};
}}
QLabel#heroSubtitle, QLabel#hint {{
    color: {TEXT_MUTED};
}}
QLabel#sectionTitle {{
    font-size: 15px;
    font-weight: 600;
    padding-top: 4px;
}}
QLabel#fieldLabel {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}
QLabel#footerNote {{
    color: {TEXT_MUTED};
    font-size: 11px;
}}
QLabel#warningNote {{ color: {WARNING}; }}
QLabel#imageError {{ color: {DANGER}; }}

/* --------------------------------------------------------------- карточки */
QFrame#card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
}}
QFrame#separator {{
    background: {BORDER};
    max-height: 1px;
    border: none;
}}

/* ---------------------------------------------------------------- кнопки */
QPushButton {{
    background: {SURFACE};
    border: 1px solid {BORDER_STRONG};
    border-radius: {RADIUS_SMALL}px;
    padding: 7px 16px;
    min-height: 20px;
}}
QPushButton:hover {{ background: {SURFACE_ALT}; border-color: {ACCENT}; }}
QPushButton:pressed {{ background: {ACCENT_SOFT}; }}
QPushButton:disabled {{
    color: {TEXT_MUTED};
    background: {SURFACE_ALT};
    border-color: {BORDER};
}}
QPushButton:focus {{ outline: none; border-color: {ACCENT}; }}

QPushButton#primaryButton, QPushButton[class="primary"] {{
    background: {ACCENT};
    color: {TEXT_ON_ACCENT};
    border: 1px solid {ACCENT};
    font-weight: 600;
}}
QPushButton#primaryButton:hover, QPushButton[class="primary"]:hover {{
    background: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}
QPushButton#primaryButton:pressed, QPushButton[class="primary"]:pressed {{
    background: {ACCENT_PRESSED};
}}
QPushButton#primaryButton:disabled, QPushButton[class="primary"]:disabled {{
    background: {BORDER};
    border-color: {BORDER};
    color: {TEXT_MUTED};
}}

/* Кнопка по умолчанию в диалогах («ОК», «Начать») — акцентная. */
QDialogButtonBox QPushButton:default {{
    background: {ACCENT};
    color: {TEXT_ON_ACCENT};
    border-color: {ACCENT};
    font-weight: 600;
}}
QDialogButtonBox QPushButton:default:hover {{ background: {ACCENT_HOVER}; }}

QPushButton[class="danger"] {{ color: {DANGER}; }}
QPushButton[class="danger"]:hover {{
    background: {DANGER_SOFT};
    border-color: {DANGER};
}}
QPushButton[class="success"] {{ color: {SUCCESS}; }}
QPushButton[class="success"]:hover {{
    background: {SUCCESS_SOFT};
    border-color: {SUCCESS};
}}
QPushButton[class="icon"] {{
    padding: 6px 10px;
    min-width: 34px;
    font-size: 13px;
}}

/* ------------------------------------------------------- поля ввода и т.п. */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox {{
    background: {SURFACE};
    border: 1px solid {BORDER_STRONG};
    border-radius: {RADIUS_SMALL}px;
    padding: 6px 10px;
    selection-background-color: {ACCENT};
    selection-color: {TEXT_ON_ACCENT};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QDateEdit:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}
QLineEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
    background: {SURFACE_ALT};
    color: {TEXT_MUTED};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE};
    border: 1px solid {BORDER_STRONG};
    selection-background-color: {ACCENT_SOFT};
    selection-color: {TEXT};
    outline: none;
}}

/* --------------------------------------------------- флажки и переключатели */
QCheckBox, QRadioButton {{ background: transparent; spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 17px;
    height: 17px;
    border: 1px solid {BORDER_STRONG};
    background: {SURFACE};
}}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    image: none;
}}
/* Точка внутри кольца. Толстая рамка вместо градиента даёт скруглённый
   квадрат: QSS применяет border-radius только к внешнему краю рамки. */
QRadioButton::indicator:checked {{
    border: 1px solid {ACCENT};
    border-radius: 9px;
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
        stop:0 {ACCENT}, stop:0.45 {ACCENT}, stop:0.5 {SURFACE}, stop:1 {SURFACE});
}}

/* ------------------------------------------------------- списки и таблицы */
QListWidget, QTreeWidget, QTableWidget, QTableView {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SMALL}px;
    alternate-background-color: {SURFACE_ALT};
    outline: none;
}}
QListWidget::item {{ padding: 7px 8px; border-radius: {RADIUS_SMALL}px; }}
QListWidget::item:hover {{ background: {SURFACE_ALT}; }}
QListWidget::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
QTableWidget::item {{ padding: 6px; }}
QTableWidget::item:selected, QTableView::item:selected {{
    background: {ACCENT_SOFT};
    color: {TEXT};
}}
QHeaderView::section {{
    background: {SURFACE_ALT};
    color: {TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    border-right: 1px solid {BORDER};
    padding: 7px 8px;
    font-weight: 600;
}}
QTableCornerButton::section {{ background: {SURFACE_ALT}; border: none; }}

/* ------------------------------------------------------------- прочее */
QProgressBar {{
    background: {SURFACE_ALT};
    border: none;
    border-radius: 5px;
    height: 8px;
    text-align: center;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 5px; }}

QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SMALL}px;
    background: {SURFACE};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_MUTED};
    padding: 8px 18px;
    border: 1px solid transparent;
    border-top-left-radius: {RADIUS_SMALL}px;
    border-top-right-radius: {RADIUS_SMALL}px;
}}
QTabBar::tab:selected {{
    background: {SURFACE};
    color: {TEXT};
    border-color: {BORDER};
    border-bottom-color: {SURFACE};
    font-weight: 600;
}}
QTabBar::tab:hover:!selected {{ color: {TEXT}; }}

QMenuBar {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; }}
QMenuBar::item {{ padding: 7px 12px; background: transparent; }}
QMenuBar::item:selected {{ background: {ACCENT_SOFT}; }}
QMenu {{ background: {SURFACE}; border: 1px solid {BORDER_STRONG}; padding: 4px; }}
QMenu::item {{ padding: 7px 24px 7px 16px; border-radius: {RADIUS_SMALL}px; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; }}

QSplitter::handle {{ background: transparent; width: 6px; }}
QStatusBar {{ background: {SURFACE}; border-top: 1px solid {BORDER}; color: {TEXT_MUTED}; }}
QToolTip {{
    background: {TEXT};
    color: {SURFACE};
    border: none;
    padding: 6px 9px;
    border-radius: {RADIUS_SMALL}px;
}}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: {BORDER_STRONG};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {TEXT_MUTED}; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{
    background: {BORDER_STRONG};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* =================================================== экран прохождения ==== */
QWidget#playerHeader {{
    background: {SURFACE};
    border-bottom: 1px solid {BORDER};
}}
QWidget#playerFooter {{
    background: {SURFACE};
    border-top: 1px solid {BORDER};
}}
QLabel#playerEmployee {{ font-size: 14px; font-weight: 600; }}
QLabel#playerCounter {{ color: {TEXT_MUTED}; font-size: 13px; }}
QLabel#playerClock {{
    font-size: 15px;
    font-weight: 600;
    color: {TEXT};
    background: {SURFACE_ALT};
    border-radius: {RADIUS_SMALL}px;
    padding: 5px 12px;
}}
QLabel#playerClock[state="warning"] {{
    color: {DANGER};
    background: {DANGER_SOFT};
}}

QWidget#questionCard {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
}}
QLabel#questionText {{
    font-size: {PLAYER_FONT_SIZE + 5}px;
    font-weight: 600;
    line-height: 140%;
}}
QLabel#questionHint {{ color: {TEXT_MUTED}; font-size: {PLAYER_FONT_SIZE}px; }}

/* Крупные варианты ответа: удобно попасть мышью и видно издалека. */
QRadioButton[class="answer"], QCheckBox[class="answer"] {{
    font-size: {PLAYER_FONT_SIZE + 1}px;
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SMALL}px;
    padding: 13px 16px;
    spacing: 12px;
}}
QRadioButton[class="answer"]:hover, QCheckBox[class="answer"]:hover {{
    border-color: {ACCENT};
    background: {ACCENT_SOFT};
}}
QRadioButton[class="answer"]:checked, QCheckBox[class="answer"]:checked {{
    border-color: {ACCENT};
    background: {ACCENT_SOFT};
    font-weight: 600;
}}
QRadioButton[class="answer"]::indicator, QCheckBox[class="answer"]::indicator {{
    width: 21px;
    height: 21px;
}}
QCheckBox[class="answer"]::indicator {{ border-radius: 5px; }}
QRadioButton[class="answer"]::indicator {{ border-radius: 11px; }}
QRadioButton[class="answer"]::indicator:checked {{
    border: 1px solid {ACCENT};
    border-radius: 11px;
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
        stop:0 {ACCENT}, stop:0.5 {ACCENT}, stop:0.55 {SURFACE}, stop:1 {SURFACE});
}}

QLineEdit[class="answer"], QComboBox[class="answer"],
QPlainTextEdit[class="answer"] {{
    font-size: {PLAYER_FONT_SIZE + 1}px;
    padding: 11px 14px;
}}
QListWidget[class="answer"] {{ font-size: {PLAYER_FONT_SIZE + 1}px; }}
QListWidget[class="answer"]::item {{
    padding: 12px 14px;
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SMALL}px;
    margin: 3px 2px;
    background: {SURFACE};
}}
QListWidget[class="answer"]::item:selected {{
    background: {ACCENT_SOFT};
    border-color: {ACCENT};
    color: {TEXT};
}}
QLabel[class="answerLeft"] {{ font-size: {PLAYER_FONT_SIZE + 1}px; }}

QPushButton#playerNext {{
    font-size: {PLAYER_FONT_SIZE + 1}px;
    padding: 12px 30px;
    min-width: 190px;
}}
QPushButton#playerBack {{
    font-size: {PLAYER_FONT_SIZE}px;
    padding: 12px 22px;
}}

/* ======================================================== главное окно ==== */
QFrame[class="tile"] {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
}}
QFrame[class="tile"]:hover {{ border-color: {ACCENT}; background: {ACCENT_SOFT}; }}
QFrame[class="tile"]:disabled {{ background: {SURFACE_ALT}; }}

QFrame[class="tilePrimary"] {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    border-radius: {RADIUS}px;
}}
QFrame[class="tilePrimary"]:hover {{ background: {ACCENT_HOVER}; }}

QFrame[class="tile"] QLabel[class="tileCaption"] {{ font-size: 15px; font-weight: 600; }}
QFrame[class="tile"] QLabel[class="tileHint"] {{ color: {TEXT_MUTED}; font-size: 12px; }}
QFrame[class="tile"]:disabled QLabel {{ color: {TEXT_MUTED}; }}

QFrame[class="tilePrimary"] QLabel[class="tileCaption"] {{
    font-size: 15px;
    font-weight: 600;
    color: {TEXT_ON_ACCENT};
}}
QFrame[class="tilePrimary"] QLabel[class="tileHint"] {{
    color: #DCE7FF;
    font-size: 12px;
}}

QLabel[class="statChip"] {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SMALL}px;
    padding: 9px 14px;
    color: {TEXT_MUTED};
}}
QLabel[class="statChipAccent"] {{
    background: {WARNING_SOFT};
    border: 1px solid #F0D8B0;
    border-radius: {RADIUS_SMALL}px;
    padding: 9px 14px;
    color: {WARNING};
    font-weight: 600;
}}

/* ========================================================== конструктор === */
QLabel#problemsHeader {{ font-weight: 600; }}
QLabel#imageThumb {{
    background: {SURFACE};
    border: 1px dashed {BORDER_STRONG};
    border-radius: {RADIUS_SMALL}px;
    color: {TEXT_MUTED};
}}
"""
