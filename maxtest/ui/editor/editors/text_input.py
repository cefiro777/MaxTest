"""Редактор вопроса с вводом текста."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ....core.enums import TextMatch
from ....core.models import Question, TextAnswer
from .base import BaseQuestionEditor

MATCH_LABELS = (
    (TextMatch.NORMALIZED, "Без учёта регистра, пробелов и «ё» (рекомендуется)"),
    (TextMatch.CONTAINS, "Ответ содержит эталон (для развёрнутых ответов)"),
    (TextMatch.EXACT, "Точное совпадение символ в символ"),
)


class TextInputEditor(BaseQuestionEditor):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._test_default = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        hint = QLabel(
            "Правильные ответы. Каждая строка — отдельный допустимый вариант, "
            "а не продолжение предыдущего:"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.accepted = QPlainTextEdit()
        self.accepted.setPlaceholderText("220\n220 В\n220 вольт")
        self.accepted.setMaximumHeight(140)
        self.accepted.textChanged.connect(self._on_accepted_changed)
        layout.addWidget(self.accepted)

        layout.addWidget(QLabel("Как сравнивать ответ:"))
        self.match = QComboBox()
        for mode, label in MATCH_LABELS:
            self.match.addItem(label, mode)
        self.match.currentIndexChanged.connect(self._on_match_changed)
        layout.addWidget(self.match)

        self.multiline = QCheckBox(
            "Развёрнутый ответ — поле ввода на несколько строк"
        )
        self.multiline.setToolTip(
            "Для коротких ответов («220 В») — одна строка, для описаний "
            "порядка действий — многострочное поле"
        )
        self.multiline.toggled.connect(self._on_multiline_changed)
        layout.addWidget(self.multiline)

        self.warning = QCheckBox("Проверять ответ на этот вопрос вручную")
        self.warning.setToolTip(
            "Развёрнутый ответ автомат оценивает грубо — его стоит прочитать "
            "глазами. Для короткого ответа вроде «220» проверка не нужна."
        )
        self.warning.toggled.connect(self._on_manual_review_changed)
        layout.addWidget(self.warning)

        self.manual_source = QLabel()
        self.manual_source.setObjectName("hint")
        layout.addWidget(self.manual_source)

        note = QLabel(
            "Совет: перечислите все разумные формы ответа. Незасчитанный верный "
            "ответ подрывает доверие ко всему тесту сильнее, чем засчитанный лишний."
        )
        note.setWordWrap(True)
        note.setObjectName("hint")
        layout.addWidget(note)
        layout.addStretch(1)

    def _fill(self, question: Question | None) -> None:
        if question is None:
            self.accepted.setPlainText("")
            return
        if question.answer_text is None:
            question.answer_text = TextAnswer()

        self.accepted.setPlainText("\n".join(question.answer_text.accepted))
        index = self.match.findData(question.answer_text.match)
        self.match.setCurrentIndex(max(0, index))
        self.multiline.setChecked(question.answer_text.multiline)
        self._refresh_manual_review()

    def set_test_default(self, enabled: bool) -> None:
        """Значение из настроек теста — используется, пока у вопроса нет своего."""
        self._test_default = enabled
        self._refresh_manual_review()

    def _refresh_manual_review(self) -> None:
        question = self._question
        with self.loading():
            if question is None:
                self.warning.setChecked(self._test_default)
                self.manual_source.setText("")
                return

            self.warning.setChecked(question.needs_manual_review(self._test_default))
            if question.manual_review is None:
                default = "включена" if self._test_default else "выключена"
                self.manual_source.setText(
                    f"Сейчас как в настройках теста (там ручная проверка {default})"
                )
            else:
                self.manual_source.setText("Задано для этого вопроса отдельно")

    def _on_manual_review_changed(self, checked: bool) -> None:
        if self._loading or self._question is None:
            return
        self._question.manual_review = checked
        self._refresh_manual_review()
        self.notify()

    def _on_accepted_changed(self) -> None:
        if self._loading or self._question is None:
            return
        if self._question.answer_text is None:
            self._question.answer_text = TextAnswer()
        lines = [line.strip() for line in self.accepted.toPlainText().splitlines()]
        self._question.answer_text.accepted = [line for line in lines if line]
        self.notify()

    def _on_multiline_changed(self, checked: bool) -> None:
        if self._loading or self._question is None:
            return
        if self._question.answer_text is None:
            self._question.answer_text = TextAnswer()
        self._question.answer_text.multiline = checked
        self.notify()

    def _on_match_changed(self) -> None:
        if self._loading or self._question is None:
            return
        if self._question.answer_text is None:
            self._question.answer_text = TextAnswer()
        self._question.answer_text.match = self.match.currentData()
        self.notify()
