"""Редактор вариантов ответа: типы «один ответ» и «несколько ответов».

Один виджет на два типа намеренно: отличие только в том, радиокнопки это или
флажки, а варианты при смене типа должны сохраняться — иначе пользователь
переключил тип и потерял всё, что набрал.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ....core.enums import QuestionType
from ....core.models import Option, Question
from .base import BaseQuestionEditor


class OptionRow(QWidget):
    def __init__(self, editor: "OptionsEditor", option: Option, single: bool) -> None:
        super().__init__()
        self.option = option
        self.editor = editor

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.correct = QRadioButton() if single else QCheckBox()
        self.correct.setToolTip("Отметить как правильный ответ")
        self.correct.setChecked(option.correct)
        self.correct.toggled.connect(self._on_correct)

        self.text = QLineEdit(option.text)
        self.text.setPlaceholderText("Текст варианта ответа")
        self.text.textChanged.connect(self._on_text)

        self.pin = QCheckBox("не перемешивать")
        self.pin.setToolTip(
            "Для вариантов вроде «Все перечисленное» — они должны остаться на месте"
        )
        self.pin.setChecked(option.no_shuffle)
        self.pin.toggled.connect(self._on_pin)

        self.remove = QPushButton("✕")
        self.remove.setProperty("class", "icon")
        self.remove.setToolTip("Удалить вариант")
        self.remove.clicked.connect(lambda: editor.remove_option(option.id))

        layout.addWidget(self.correct)
        layout.addWidget(self.text, 1)
        layout.addWidget(self.pin)
        layout.addWidget(self.remove)

    def _on_correct(self, checked: bool) -> None:
        if self.editor._loading:
            return
        self.option.correct = checked
        if checked and self.editor.is_single:
            # QRadioButton вне QButtonGroup не снимает остальные сам.
            for row in self.editor.rows:
                if row is not self and row.option.correct:
                    row.option.correct = False
                    with self.editor.loading():
                        row.correct.setChecked(False)
        self.editor.notify()

    def _on_text(self, value: str) -> None:
        if self.editor._loading:
            return
        self.option.text = value
        self.editor.notify()

    def _on_pin(self, checked: bool) -> None:
        if self.editor._loading:
            return
        self.option.no_shuffle = checked
        self.editor.notify()


class OptionsEditor(BaseQuestionEditor):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rows: list[OptionRow] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.hint = QLabel()
        self.hint.setObjectName("hint")
        layout.addWidget(self.hint)

        self.rows_host = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_host)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.rows_host)

        add = QPushButton("+ Вариант ответа")
        add.clicked.connect(self.add_option)
        add_row = QHBoxLayout()
        add_row.addWidget(add)
        add_row.addStretch(1)
        layout.addLayout(add_row)
        layout.addStretch(1)

    @property
    def is_single(self) -> bool:
        return self._question is not None and self._question.type is QuestionType.SINGLE

    def _fill(self, question: Question | None) -> None:
        for row in self.rows:
            row.setParent(None)
            row.deleteLater()
        self.rows.clear()

        if question is None:
            return

        self.hint.setText(
            "Отметьте один правильный ответ:"
            if self.is_single
            else "Отметьте все правильные ответы:"
        )
        for option in question.options:
            row = OptionRow(self, option, self.is_single)
            self.rows_layout.addWidget(row)
            self.rows.append(row)

    def add_option(self) -> None:
        if self._question is None:
            return
        self._question.options.append(Option())
        self.load(self._question)
        self.notify()

    def remove_option(self, option_id: str) -> None:
        if self._question is None:
            return
        self._question.options = [o for o in self._question.options if o.id != option_id]
        self.load(self._question)
        self.notify()
