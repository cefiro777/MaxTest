"""Отображение вопроса — общий виджет для проигрывателя и превью в конструкторе.

Держим рендеринг в одном месте намеренно: два отдельных набора кода для
«как выглядит вопрос» неизбежно разъезжаются, и сотрудник видит не то, что
автор проверял в превью.

Ответ всегда собирается по стабильным ``id``, а не по позиции виджета на
экране: варианты и пункты перемешиваются, позиции «поедут».
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ...core.enums import QuestionType
from ...core.models import Question
from .growing_text import GrowingTextEdit

IMAGE_MAX_HEIGHT = 420


class QuestionView(QWidget):
    """Показывает вопрос и собирает ответ в формате движка оценки."""

    answer_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._question: Question | None = None
        self._buttons: dict[str, QRadioButton | QCheckBox] = {}
        self._group: QButtonGroup | None = None
        self._text_area: GrowingTextEdit | None = None
        self._match_boxes: dict[str, QComboBox] = {}
        self._order_list: QListWidget | None = None

        # Без этого флага подкласс QWidget игнорирует фон и рамку из QSS —
        # карточка вопроса осталась бы прозрачной.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(32, 30, 32, 30)
        self._layout.setSpacing(14)

    # ------------------------------------------------------------------ view

    def set_question(
        self,
        question: Question,
        option_order: list[str] | None = None,
        item_order: list[str] | None = None,
        image: bytes | None = None,
        answer: dict | None = None,
    ) -> None:
        self._clear()
        self._question = question

        if image:
            self._layout.addWidget(self._make_image(image))

        text = QLabel(question.text or "(текст вопроса не задан)")
        text.setObjectName("questionText")
        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._layout.addWidget(text)

        if question.type is QuestionType.MULTI:
            hint = QLabel("Можно выбрать несколько ответов")
            hint.setObjectName("questionHint")
            self._layout.addWidget(hint)

        if question.type in (QuestionType.SINGLE, QuestionType.MULTI):
            self._build_options(question, option_order, answer)
        elif question.type is QuestionType.TEXT:
            self._build_text_input(question, answer)
        elif question.type is QuestionType.MATCHING:
            self._build_matching(question, item_order, answer)
        elif question.type is QuestionType.ORDERING:
            self._build_ordering(question, item_order, answer)

        # Лишнюю высоту забирает распорка внизу, иначе Qt растащит её в
        # промежутки между текстом вопроса и вариантами ответа.
        self._layout.addStretch(1)

    def _make_image(self, blob: bytes) -> QLabel:
        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap()
        if not pixmap.loadFromData(blob):
            # Чаще всего это отсутствующий плагин imageformats в сборке PyInstaller.
            label.setText("[не удалось отобразить изображение]")
            label.setObjectName("imageError")
            return label
        if pixmap.height() > IMAGE_MAX_HEIGHT:
            pixmap = pixmap.scaledToHeight(
                IMAGE_MAX_HEIGHT, Qt.TransformationMode.SmoothTransformation
            )
        label.setPixmap(pixmap)
        return label

    # ------------------------------------------------------- варианты ответа

    def _build_options(
        self,
        question: Question,
        option_order: list[str] | None,
        answer: dict | None,
    ) -> None:
        order = option_order or [o.id for o in question.options]
        single = question.type is QuestionType.SINGLE

        if single:
            self._group = QButtonGroup(self)
            self._group.setExclusive(True)

        chosen: set[str] = set()
        if answer:
            if single and answer.get("option_id"):
                chosen = {answer["option_id"]}
            else:
                chosen = set(answer.get("option_ids") or [])

        for option_id in order:
            option = question.option_by_id(option_id)
            if option is None:
                continue  # вопрос отредактировали после начала попытки
            box = QRadioButton(option.text) if single else QCheckBox(option.text)
            box.setProperty("class", "answer")  # крупная «карточка» ответа
            box.setCursor(Qt.CursorShape.PointingHandCursor)
            box.setChecked(option_id in chosen)
            if self._group is not None:
                self._group.addButton(box)
            box.toggled.connect(self.answer_changed)
            self._layout.addWidget(box)
            self._buttons[option_id] = box

    # ------------------------------------------------------------ ввод текста

    def _build_text_input(self, question: Question, answer: dict | None) -> None:
        saved = (answer or {}).get("text", "")
        multiline = bool(question.answer_text and question.answer_text.multiline)

        # Поле всегда с переносом и ростом по высоте. Разница «развёрнутого»
        # ответа только в стартовой высоте: под описание сразу видно больше
        # места, под короткий ответ поле компактнее, но длинную фразу всё
        # равно переносит, а не прячет вправо.
        self._text_area = GrowingTextEdit(
            saved,
            min_lines=4 if multiline else 2,
            max_lines=16 if multiline else 10,
        )
        self._text_area.setProperty("class", "answer")
        self._text_area.setPlaceholderText(
            "Введите развёрнутый ответ" if multiline else "Введите ответ"
        )
        self._text_area.textChanged.connect(self.answer_changed)
        self._layout.addWidget(self._text_area)

    # ------------------------------------------------------------ соответствие

    def _build_matching(
        self, question: Question, item_order: list[str] | None, answer: dict | None
    ) -> None:
        pairs = question.pairs or []
        by_id = {p.id: p for p in pairs}
        rights = [by_id[i] for i in (item_order or []) if i in by_id]
        for p in pairs:  # правые части, которых не было в плане
            if p not in rights:
                rights.append(p)

        saved = (answer or {}).get("pairs") or {}

        for pair in pairs:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)

            left = QLabel(pair.left)
            left.setProperty("class", "answerLeft")
            left.setWordWrap(True)
            left.setMinimumWidth(220)

            combo = QComboBox()
            combo.setProperty("class", "answer")
            combo.setCursor(Qt.CursorShape.PointingHandCursor)
            combo.addItem("— выберите —", None)
            for right in rights:
                combo.addItem(right.right, right.id)
            chosen = saved.get(pair.id)
            if chosen:
                index = combo.findData(chosen)
                if index >= 0:
                    combo.setCurrentIndex(index)
            combo.currentIndexChanged.connect(self.answer_changed)

            row_layout.addWidget(left, 1)
            row_layout.addWidget(QLabel("→"))
            row_layout.addWidget(combo, 1)
            self._layout.addWidget(row)
            self._match_boxes[pair.id] = combo

    # ----------------------------------------------------------- упорядочивание

    def _build_ordering(
        self, question: Question, item_order: list[str] | None, answer: dict | None
    ) -> None:
        items = question.order or []
        by_id = {i.id: i for i in items}

        saved = (answer or {}).get("order") or item_order or [i.id for i in items]
        ordered = [by_id[i] for i in saved if i in by_id]
        for item in items:
            if item not in ordered:
                ordered.append(item)

        hint = QLabel("Расставьте пункты в правильном порядке — перетащите мышью")
        hint.setObjectName("questionHint")
        self._layout.addWidget(hint)

        self._order_list = QListWidget()
        self._order_list.setProperty("class", "answer")
        self._order_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._order_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        for item in ordered:
            widget_item = QListWidgetItem(item.text)
            widget_item.setData(Qt.ItemDataRole.UserRole, item.id)
            self._order_list.addItem(widget_item)
        self._order_list.model().rowsMoved.connect(self.answer_changed)

        # Высота ровно по содержимому: растянутый на весь экран список из трёх
        # пунктов выглядит как ошибка вёрстки.
        rows = sum(
            self._order_list.sizeHintForRow(row) for row in range(self._order_list.count())
        )
        self._order_list.setFixedHeight(min(560, rows + 2 * self._order_list.frameWidth() + 10))
        self._layout.addWidget(self._order_list)

        buttons = QWidget()
        buttons_layout = QHBoxLayout(buttons)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        for label, delta in (("↑ Выше", -1), ("↓ Ниже", +1)):
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, d=delta: self._move_order_item(d))
            buttons_layout.addWidget(button)
        buttons_layout.addStretch(1)
        self._layout.addWidget(buttons)

    def _move_order_item(self, delta: int) -> None:
        widget = self._order_list
        if widget is None:
            return
        row = widget.currentRow()
        target = row + delta
        if row < 0 or not (0 <= target < widget.count()):
            return
        item = widget.takeItem(row)
        widget.insertItem(target, item)
        widget.setCurrentRow(target)
        self.answer_changed.emit()

    # ----------------------------------------------------------------- сброс

    def _clear(self) -> None:
        self._buttons.clear()
        self._match_boxes.clear()
        self._group = None
        self._text_area = None
        self._order_list = None
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # setParent(None) убирает виджет с экрана сразу; один
                # deleteLater() отрабатывает асинхронно, и при смене вопроса
                # старые варианты успевают мигнуть поверх новых.
                widget.setParent(None)
                widget.deleteLater()

    # ---------------------------------------------------------------- answer

    def answer(self) -> dict | None:
        """Ответ в формате движка оценки. Всегда по ``id``, не по позиции."""
        q = self._question
        if q is None:
            return None

        if q.type is QuestionType.SINGLE:
            chosen = [oid for oid, box in self._buttons.items() if box.isChecked()]
            return {"option_id": chosen[0]} if chosen else None

        if q.type is QuestionType.MULTI:
            chosen = [oid for oid, box in self._buttons.items() if box.isChecked()]
            return {"option_ids": chosen} if chosen else None

        if q.type is QuestionType.TEXT:
            value = self._text_area.toPlainText().strip() if self._text_area else ""
            return {"text": value} if value else None

        if q.type is QuestionType.MATCHING:
            mapping = {
                pair_id: combo.currentData()
                for pair_id, combo in self._match_boxes.items()
                if combo.currentData()
            }
            return {"pairs": mapping} if mapping else None

        if q.type is QuestionType.ORDERING:
            widget = self._order_list
            if widget is None:
                return None
            order = [
                widget.item(row).data(Qt.ItemDataRole.UserRole)
                for row in range(widget.count())
            ]
            return {"order": order} if order else None

        return None

    def has_answer(self) -> bool:
        return self.answer() is not None

    def set_read_only(self, read_only: bool) -> None:
        """Режим превью в конструкторе: видно, но не кликается."""
        for box in self._buttons.values():
            box.setEnabled(not read_only)
        for combo in self._match_boxes.values():
            combo.setEnabled(not read_only)
        if self._text_area is not None:
            self._text_area.setReadOnly(read_only)
        if self._order_list is not None:
            self._order_list.setEnabled(not read_only)
