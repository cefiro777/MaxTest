"""Конструктор тестов.

Главная ловушка этого окна — сигналы Qt. При переключении вопроса форма
заполняется программно, и её сигналы ``textChanged``/``toggled`` успевают
записать значения в ПРЕДЫДУЩИЙ вопрос. От этого защищает флаг ``self.loading``
здесь и ``BaseQuestionEditor.loading()`` в редакторах типов.
"""

from __future__ import annotations

import copy
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...core.bundle import Bundle, BundleError
from ...core.enums import QuestionType
from ...core.models import MatchPair, Option, OrderItem, Question, Test, TextAnswer
from ...core.paths import tests_dir
from ...core.recent import RecentTests
from ...core.session import build_plan
from ...core.validator import validate
from ..widgets.growing_text import GrowingTextEdit
from ..widgets.question_view import QuestionView
from .editors import MatchingEditor, OptionsEditor, OrderingEditor, TextInputEditor
from .test_settings import TestSettingsDialog

FILE_FILTER = "Тесты MaxTest (*.qtest);;Все файлы (*)"
IMAGE_FILTER = "Изображения (*.png *.jpg *.jpeg *.bmp *.gif);;Все файлы (*)"

TYPE_LABELS = (
    (QuestionType.SINGLE, "Один правильный ответ"),
    (QuestionType.MULTI, "Несколько правильных ответов"),
    (QuestionType.TEXT, "Ввод текста"),
    (QuestionType.MATCHING, "Установление соответствия"),
    (QuestionType.ORDERING, "Упорядочивание"),
)

THUMB_HEIGHT = 120


class EditorWindow(QMainWindow):
    def __init__(self, bundle: Bundle | None = None) -> None:
        super().__init__()
        self.bundle = bundle or Bundle.new()
        self.loading = False
        self._dirty = False

        self.setWindowTitle("MaxTest — конструктор")
        self.resize(1240, 820)
        self._build_ui()
        self._build_menu()
        self._reload_question_list()
        self._update_title()

    # -------------------------------------------------------------- интерфейс

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([340, 900])

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter, 1)
        layout.addWidget(self._build_problems_panel())
        self.setCentralWidget(central)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)

        layout.addWidget(self._field_label("Название теста"))
        self.title_edit = QLineEdit(self.bundle.test.title)
        self.title_edit.setPlaceholderText("Например: Аттестация электромонтёров")
        self.title_edit.textChanged.connect(self._on_title_changed)
        layout.addWidget(self.title_edit)

        self.question_list = QListWidget()
        self.question_list.currentRowChanged.connect(self._on_question_selected)
        layout.addWidget(self.question_list, 1)

        buttons = QHBoxLayout()
        for text, tip, slot in (
            ("+ Вопрос", "Добавить вопрос", self.add_question),
            ("Дубль", "Дублировать вопрос", self.duplicate_question),
            ("✕", "Удалить вопрос", self.remove_question),
            ("↑", "Переместить вверх", lambda: self.move_question(-1)),
            ("↓", "Переместить вниз", lambda: self.move_question(+1)),
        ):
            button = QPushButton(text)
            button.setToolTip(tip)
            if len(text) <= 2:  # ✕, ↑, ↓ — компактные кнопки-значки
                button.setProperty("class", "icon")
            button.clicked.connect(slot)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        return panel

    def _build_right_panel(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)

        # --- шапка вопроса: тип, вес, раздел
        head = QHBoxLayout()
        self.type_combo = QComboBox()
        for question_type, label in TYPE_LABELS:
            self.type_combo.addItem(label, question_type)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)

        self.weight_spin = QDoubleSpinBox()
        self.weight_spin.setRange(0.0, 100.0)
        self.weight_spin.setSingleStep(0.5)
        self.weight_spin.setDecimals(1)
        self.weight_spin.setToolTip("Сколько баллов стоит вопрос")
        self.weight_spin.valueChanged.connect(self._on_weight_changed)

        self.section_combo = QComboBox()
        self.section_combo.currentIndexChanged.connect(self._on_section_changed)

        head.addWidget(QLabel("Тип:"))
        head.addWidget(self.type_combo, 2)
        head.addWidget(QLabel("Вес:"))
        head.addWidget(self.weight_spin)
        head.addWidget(QLabel("Раздел:"))
        head.addWidget(self.section_combo, 1)
        layout.addLayout(head)

        # --- текст вопроса (растёт под длинный вопрос, переносит по ширине)
        layout.addWidget(self._field_label("Текст вопроса"))
        self.question_text = GrowingTextEdit(min_lines=2, max_lines=10)
        self.question_text.setPlaceholderText("Например: Что делать при обнаружении…")
        self.question_text.textChanged.connect(self._on_question_text_changed)
        layout.addWidget(self.question_text)

        # --- картинка
        image_row = QHBoxLayout()
        self.image_thumb = QLabel("без картинки")
        self.image_thumb.setFixedHeight(THUMB_HEIGHT)
        self.image_thumb.setMinimumWidth(180)
        self.image_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_thumb.setObjectName("imageThumb")

        pick = QPushButton("Выбрать картинку…")
        pick.clicked.connect(self.pick_image)
        drop = QPushButton("Убрать картинку")
        drop.clicked.connect(self.clear_image)

        image_buttons = QVBoxLayout()
        image_buttons.addWidget(pick)
        image_buttons.addWidget(drop)
        image_buttons.addStretch(1)

        image_row.addWidget(self.image_thumb)
        image_row.addLayout(image_buttons)
        image_row.addStretch(1)
        layout.addLayout(image_row)

        # --- редактор под тип вопроса
        self.editors: dict[QuestionType, object] = {
            QuestionType.SINGLE: OptionsEditor(),
            QuestionType.MULTI: OptionsEditor(),
            QuestionType.TEXT: TextInputEditor(),
            QuestionType.MATCHING: MatchingEditor(),
            QuestionType.ORDERING: OrderingEditor(),
        }
        self.editor_stack = QStackedWidget()
        self._editor_index: dict[QuestionType, int] = {}
        for question_type, editor in self.editors.items():
            editor.changed.connect(self._on_editor_changed)
            self._editor_index[question_type] = self.editor_stack.addWidget(editor)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.editor_stack)
        layout.addWidget(scroll, 1)

        # --- пояснение
        layout.addWidget(self._field_label("Пояснение (показывается в разборе ошибок)"))
        self.explanation = QLineEdit()
        self.explanation.setPlaceholderText("Например: ПОТЭЭ, п. 3.2")
        self.explanation.textChanged.connect(self._on_explanation_changed)
        layout.addWidget(self.explanation)

        preview = QPushButton("Предпросмотр — как увидит сотрудник")
        preview.clicked.connect(self.preview_question)
        layout.addWidget(preview)

        return page

    def _build_problems_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 0, 8, 8)

        self.problems_header = QLabel("Проверка теста")
        self.problems_header.setObjectName("problemsHeader")
        layout.addWidget(self.problems_header)

        self.problems_list = QListWidget()
        self.problems_list.setMaximumHeight(120)
        self.problems_list.itemActivated.connect(self._on_problem_activated)
        self.problems_list.itemClicked.connect(self._on_problem_activated)
        layout.addWidget(self.problems_list)
        return panel

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&Файл")
        for title, shortcut, slot in (
            ("&Новый", QKeySequence.StandardKey.New, self.new_test),
            ("&Открыть…", QKeySequence.StandardKey.Open, self.open_test),
            ("&Сохранить", QKeySequence.StandardKey.Save, self.save_test),
            ("Сохранить &как…", QKeySequence.StandardKey.SaveAs, self.save_test_as),
        ):
            action = QAction(title, self)
            action.setShortcut(shortcut)
            action.triggered.connect(slot)
            file_menu.addAction(action)
        file_menu.addSeparator()
        close_action = QAction("Закрыть", self)
        close_action.triggered.connect(self.close)
        file_menu.addAction(close_action)

        test_menu = self.menuBar().addMenu("&Тест")
        settings_action = QAction("&Настройки теста…", self)
        settings_action.triggered.connect(self.open_settings)
        test_menu.addAction(settings_action)
        preview_action = QAction("&Предпросмотр вопроса", self)
        preview_action.setShortcut("F5")
        preview_action.triggered.connect(self.preview_question)
        test_menu.addAction(preview_action)

    # ------------------------------------------------------------ «грязный» флаг

    def mark_dirty(self) -> None:
        self._dirty = True
        self._update_title()
        self.refresh_problems()

    def _update_title(self) -> None:
        name = self.bundle.path.name if self.bundle.path else "новый тест"
        star = " *" if self._dirty else ""
        self.setWindowTitle(f"MaxTest — конструктор — {name}{star}")

    def refresh_problems(self) -> None:
        """Валидация предупреждающая: показываем проблемы, но работать не мешаем."""
        problems = validate(self.bundle.test, known_media=set(self.bundle.media))
        self.problems_list.clear()
        for problem in problems:
            item = QListWidgetItem(("⛔ " if problem.is_error else "⚠ ") + problem.text)
            item.setData(Qt.ItemDataRole.UserRole, problem.question_index)
            item.setForeground(
                Qt.GlobalColor.darkRed if problem.is_error else Qt.GlobalColor.darkYellow
            )
            self.problems_list.addItem(item)

        errors = sum(1 for p in problems if p.is_error)
        warnings = len(problems) - errors
        # Пустой белый прямоугольник внизу окна выглядит как недоделка —
        # список показываем, только когда есть что показать.
        self.problems_list.setVisible(bool(problems))
        if not problems:
            self.problems_header.setText("✓ Проверка теста: замечаний нет")
        else:
            self.problems_header.setText(
                f"Проверка теста: ошибок — {errors}, предупреждений — {warnings} "
                "(клик по строке — перейти к вопросу)"
            )

    def _on_problem_activated(self, item: QListWidgetItem) -> None:
        index = item.data(Qt.ItemDataRole.UserRole)
        if index:
            self.question_list.setCurrentRow(index - 1)

    # --------------------------------------------------------------- вопросы

    @property
    def current_question(self) -> Question | None:
        row = self.question_list.currentRow()
        questions = self.bundle.test.questions
        return questions[row] if 0 <= row < len(questions) else None

    def _question_caption(self, index: int, q: Question) -> str:
        label = dict(TYPE_LABELS)[q.type]
        preview = (q.text.strip().splitlines() or [""])[0][:55] or "(без текста)"
        mark = "🖼 " if q.image else ""
        return f"{index}. {mark}{preview}  ·  {label}"

    def _reload_question_list(self, select: int | None = None) -> None:
        self.loading = True
        self.question_list.clear()
        for index, q in enumerate(self.bundle.test.questions, start=1):
            self.question_list.addItem(QListWidgetItem(self._question_caption(index, q)))
        self._reload_sections_combo()
        self.loading = False

        questions = self.bundle.test.questions
        if questions:
            target = 0 if select is None else max(0, min(select, len(questions) - 1))
            self.question_list.setCurrentRow(target)
            self._load_question(questions[target])
        else:
            self._load_question(None)
        self.refresh_problems()

    def _reload_sections_combo(self) -> None:
        previous = self.section_combo.currentData()
        self.section_combo.clear()
        self.section_combo.addItem("— вне разделов —", None)
        for section in self.bundle.test.sections:
            self.section_combo.addItem(section.title, section.id)
        index = self.section_combo.findData(previous)
        if index >= 0:
            self.section_combo.setCurrentIndex(index)

    def refresh_current_list_item(self) -> None:
        row = self.question_list.currentRow()
        q = self.current_question
        if q is None or row < 0:
            return
        self.question_list.item(row).setText(self._question_caption(row + 1, q))

    def _on_question_selected(self, row: int) -> None:
        if self.loading:
            return
        self._load_question(self.current_question)

    def _load_question(self, q: Question | None) -> None:
        # Флаг поднят на всё время заполнения формы.
        self.loading = True
        try:
            enabled = q is not None
            for widget in (
                self.type_combo, self.weight_spin, self.section_combo,
                self.question_text, self.explanation,
            ):
                widget.setEnabled(enabled)

            self.question_text.setPlainText(q.text if q else "")
            self.explanation.setText(q.explanation if q else "")
            self.weight_spin.setValue(q.weight if q else 1.0)
            self.type_combo.setCurrentIndex(
                self.type_combo.findData(q.type) if q else 0
            )
            self.section_combo.setCurrentIndex(
                max(0, self.section_combo.findData(q.section_id)) if q else 0
            )
            self._update_thumb(q)

            if q is not None:
                self.editor_stack.setCurrentIndex(self._editor_index[q.type])
                self.editors[q.type].load(q)
                if q.type is QuestionType.TEXT:
                    self.editors[q.type].set_test_default(
                        self.bundle.test.grading.text_manual_review
                    )
        finally:
            self.loading = False

    def add_question(self) -> None:
        q = Question(type=QuestionType.SINGLE, text="")
        q.options = [Option(), Option()]
        self.bundle.test.questions.append(q)
        self.mark_dirty()
        self._reload_question_list(select=len(self.bundle.test.questions) - 1)

    def duplicate_question(self) -> None:
        """Копия вопроса с новыми id — иначе оценка привяжется к чужим вариантам."""
        q = self.current_question
        if q is None:
            return
        clone = copy.deepcopy(q)
        clone.id = Question().id
        for option in clone.options:
            option.id = Option().id
        for pair in clone.pairs or []:
            pair.id = MatchPair().id
        for item in clone.order or []:
            item.id = OrderItem().id

        row = self.question_list.currentRow()
        self.bundle.test.questions.insert(row + 1, clone)
        self.mark_dirty()
        self._reload_question_list(select=row + 1)

    def remove_question(self) -> None:
        row = self.question_list.currentRow()
        if row < 0:
            return
        answer = QMessageBox.question(
            self, "Удалить вопрос", "Удалить выбранный вопрос?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer is not QMessageBox.StandardButton.Yes:
            return
        del self.bundle.test.questions[row]
        self.mark_dirty()
        self._reload_question_list(select=row)

    def move_question(self, delta: int) -> None:
        row = self.question_list.currentRow()
        questions = self.bundle.test.questions
        target = row + delta
        if row < 0 or not (0 <= target < len(questions)):
            return
        questions[row], questions[target] = questions[target], questions[row]
        self.mark_dirty()
        self._reload_question_list(select=target)

    # ---------------------------------------------------------------- картинка

    def pick_image(self) -> None:
        q = self.current_question
        if q is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите картинку", str(Path.home()), IMAGE_FILTER
        )
        if not path:
            return
        try:
            # Картинка ужимается при вставке: фото с телефона иначе раздувают
            # тест до сотен мегабайт и вешают превью.
            q.image = self.bundle.add_image(path)
        except BundleError as exc:
            QMessageBox.critical(self, "Не удалось вставить картинку", str(exc))
            return
        self._update_thumb(q)
        self.refresh_current_list_item()
        self.mark_dirty()

    def clear_image(self) -> None:
        q = self.current_question
        if q is None or not q.image:
            return
        q.image = None
        self._update_thumb(q)
        self.refresh_current_list_item()
        self.mark_dirty()

    def _update_thumb(self, q: Question | None) -> None:
        blob = self.bundle.get_image_bytes(q.image) if q else None
        if not blob:
            self.image_thumb.clear()
            self.image_thumb.setText(
                "картинка потеряна" if (q and q.image) else "без картинки"
            )
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(blob):
            self.image_thumb.setText("формат не поддержан")
            return
        self.image_thumb.setPixmap(
            pixmap.scaledToHeight(THUMB_HEIGHT, Qt.TransformationMode.SmoothTransformation)
        )

    # ------------------------------------------------------------ обработчики

    def _on_title_changed(self, value: str) -> None:
        if self.loading:
            return
        self.bundle.test.title = value
        self.mark_dirty()

    def _on_question_text_changed(self) -> None:
        if self.loading:
            return
        q = self.current_question
        if q is None:
            return
        q.text = self.question_text.toPlainText()
        self.refresh_current_list_item()
        self.mark_dirty()

    def _on_explanation_changed(self, value: str) -> None:
        if self.loading:
            return
        q = self.current_question
        if q is not None:
            q.explanation = value
            self.mark_dirty()

    def _on_weight_changed(self, value: float) -> None:
        if self.loading:
            return
        q = self.current_question
        if q is not None:
            q.weight = value
            self.mark_dirty()

    def _on_section_changed(self) -> None:
        if self.loading:
            return
        q = self.current_question
        if q is not None:
            q.section_id = self.section_combo.currentData()
            self.mark_dirty()

    def _on_editor_changed(self) -> None:
        if self.loading:
            return
        self.mark_dirty()

    def _on_type_changed(self) -> None:
        if self.loading:
            return
        q = self.current_question
        if q is None:
            return
        new_type = self.type_combo.currentData()
        if new_type is q.type:
            return

        q.type = new_type
        # Данные прежнего типа не удаляем: пользователь может вернуть тип назад
        # и найти свои варианты на месте.
        self._ensure_type_defaults(q)
        self._load_question(q)
        self.refresh_current_list_item()
        self.mark_dirty()

    @staticmethod
    def _ensure_type_defaults(q: Question) -> None:
        if q.type in (QuestionType.SINGLE, QuestionType.MULTI):
            while len(q.options) < 2:
                q.options.append(Option())
            if q.type is QuestionType.SINGLE and len(q.correct_option_ids()) > 1:
                # «Один ответ» не терпит нескольких правильных — оставляем первый.
                seen = False
                for option in q.options:
                    if option.correct and seen:
                        option.correct = False
                    elif option.correct:
                        seen = True
        elif q.type is QuestionType.TEXT and q.answer_text is None:
            q.answer_text = TextAnswer()
        elif q.type is QuestionType.MATCHING:
            q.pairs = q.pairs or []
            while len(q.pairs) < 2:
                q.pairs.append(MatchPair())
        elif q.type is QuestionType.ORDERING:
            q.order = q.order or []
            while len(q.order) < 2:
                q.order.append(OrderItem(text=f"Пункт {len(q.order) + 1}"))

    # --------------------------------------------------------------- действия

    def open_settings(self) -> None:
        dialog = TestSettingsDialog(self.bundle.test, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.mark_dirty()
            row = self.question_list.currentRow()
            self._reload_question_list(select=row)

    def preview_question(self) -> None:
        q = self.current_question
        if q is None:
            return
        PreviewDialog(self.bundle, q, self).exec()

    # ----------------------------------------------------------------- файлы

    def new_test(self) -> None:
        if not self._confirm_discard():
            return
        self._set_bundle(Bundle.new())

    def open_test(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Открыть тест", str(tests_dir()), FILE_FILTER
        )
        if not path:
            return
        try:
            bundle = Bundle.load(path)
        except BundleError as exc:
            QMessageBox.critical(self, "Не удалось открыть", str(exc))
            return

        if bundle.missing_media:
            QMessageBox.warning(
                self, "Отсутствуют картинки",
                "В файле не хватает изображений:\n" + "\n".join(bundle.missing_media),
            )
        self._set_bundle(bundle)

    def _set_bundle(self, bundle: Bundle) -> None:
        self.bundle = bundle
        self._dirty = False
        self.loading = True
        self.title_edit.setText(bundle.test.title)
        self.loading = False
        self._reload_question_list()
        self._update_title()

    def save_test(self) -> bool:
        if self.bundle.path is None:
            return self.save_test_as()
        return self._save_to(self.bundle.path)

    def save_test_as(self) -> bool:
        suggested = str(tests_dir() / f"{self.bundle.test.title or 'тест'}.qtest")
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить тест", suggested, FILE_FILTER)
        if not path:
            return False
        return self._save_to(Path(path))

    def _save_to(self, path: Path) -> bool:
        # Картинки удалённых вопросов не тащим в файл.
        self.bundle.prune_media()
        try:
            self.bundle.save(path)
        except BundleError as exc:
            QMessageBox.critical(self, "Не удалось сохранить", str(exc))
            return False
        self._dirty = False
        self._update_title()
        # Чтобы тест сразу появился в списке выбора, даже если сохранён не в
        # папку тестов, а, например, на флешку.
        RecentTests().add(path)
        self.statusBar().showMessage(f"Сохранено: {path}", 5000)
        return True

    def _confirm_discard(self) -> bool:
        """Диалог «сохранить перед выходом» — без него однажды теряется полчаса работы."""
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Несохранённые изменения",
            "Тест изменён. Сохранить перед продолжением?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if answer is QMessageBox.StandardButton.Save:
            return self.save_test()
        return answer is QMessageBox.StandardButton.Discard

    def closeEvent(self, event) -> None:
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()


class PreviewDialog(QDialog):
    """Вопрос ровно в том виде, в каком его увидит сотрудник."""

    def __init__(self, bundle: Bundle, question: Question, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Предпросмотр вопроса")
        self.resize(820, 620)

        # План строим настоящим движком: так превью показывает и перемешивание,
        # и закреплённые варианты — ровно как при прохождении.
        temp_test = Test(settings=bundle.test.settings, questions=[question])
        plan = build_plan(temp_test)

        view = QuestionView()
        view.set_question(
            question,
            option_order=plan.option_order.get(question.id),
            item_order=plan.item_order.get(question.id),
            image=bundle.get_image_bytes(question.image),
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(view)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll, 1)

        close = QPushButton("Закрыть")
        close.clicked.connect(self.accept)
        layout.addWidget(close)
