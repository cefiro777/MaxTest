"""Настройки теста: прохождение, оценивание, разделы.

Изменения применяются только по кнопке «ОК» — диалог правит копии значений,
а не модель напрямую, чтобы «Отмена» действительно отменяла.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...core.enums import MultiMode, ScaleType, SelectionMode
from ...core.models import Scale, Section, Test, Threshold

SELECTION_LABELS = (
    (SelectionMode.ALL, "Все вопросы теста"),
    (SelectionMode.RANDOM, "Случайные N вопросов из банка"),
    (SelectionMode.BY_SECTION, "По N вопросов из каждого раздела"),
)

MULTI_LABELS = (
    (MultiMode.PARTIAL, "Частичный балл за частично верный ответ"),
    (MultiMode.ALL_OR_NOTHING, "Всё или ничего: балл только за полностью верный"),
)

SCALE_PRESETS = (
    (ScaleType.PASS_FAIL, "Зачёт / незачёт"),
    (ScaleType.FIVE_POINT, "Пятибалльная"),
    (ScaleType.CUSTOM, "Своя шкала"),
)


class TestSettingsDialog(QDialog):
    # Имя начинается с Test — иначе pytest пытается собрать класс как тест.
    __test__ = False

    def __init__(self, test: Test, parent=None) -> None:
        super().__init__(parent)
        self.test = test
        self.setWindowTitle("Настройки теста")
        self.resize(680, 560)

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._build_run_tab(), "Прохождение")
        tabs.addTab(self._build_grading_tab(), "Оценивание")
        tabs.addTab(self._build_sections_tab(), "Разделы")
        layout.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load()

    # ------------------------------------------------------------- вкладки

    def _build_run_tab(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)

        self.shuffle_questions = QCheckBox("Перемешивать вопросы")
        self.shuffle_options = QCheckBox("Перемешивать варианты ответа")
        form.addRow(self.shuffle_questions)
        form.addRow(self.shuffle_options)

        self.selection = QComboBox()
        for mode, label in SELECTION_LABELS:
            self.selection.addItem(label, mode)
        self.selection.currentIndexChanged.connect(self._update_enabled)
        form.addRow("Какие вопросы задавать:", self.selection)

        self.questions_to_ask = QSpinBox()
        self.questions_to_ask.setRange(1, 999)
        form.addRow("Сколько вопросов задавать:", self.questions_to_ask)

        self.time_limit = QSpinBox()
        self.time_limit.setRange(0, 600)
        self.time_limit.setSuffix(" мин")
        self.time_limit.setSpecialValueText("без ограничения")
        form.addRow("Время на весь тест:", self.time_limit)

        self.allow_back = QCheckBox("Разрешить возвращаться к предыдущим вопросам")
        self.show_result = QCheckBox("Показывать сотруднику его результат")
        self.show_review = QCheckBox("Показывать сотруднику разбор ошибок")
        form.addRow(self.allow_back)
        form.addRow(self.show_result)
        form.addRow(self.show_review)

        return page

    def _build_grading_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()

        self.multi_mode = QComboBox()
        for mode, label in MULTI_LABELS:
            self.multi_mode.addItem(label, mode)
        form.addRow("Вопросы с несколькими ответами:", self.multi_mode)

        self.partial_penalty = QCheckBox("Вычитать за лишние выбранные варианты")
        self.partial_penalty.setToolTip(
            "Без штрафа выгодно отмечать все варианты подряд"
        )
        form.addRow(self.partial_penalty)

        self.manual_review = QCheckBox(
            "Текстовые ответы помечать для ручной проверки"
        )
        form.addRow(self.manual_review)
        layout.addLayout(form)

        layout.addWidget(QLabel("Шкала оценивания:"))
        self.scale_preset = QComboBox()
        for scale_type, label in SCALE_PRESETS:
            self.scale_preset.addItem(label, scale_type)
        self.scale_preset.currentIndexChanged.connect(self._on_preset_changed)
        layout.addWidget(self.scale_preset)

        self.thresholds = QTableWidget(0, 3)
        self.thresholds.setHorizontalHeaderLabels(["От, %", "Название оценки", "Зачёт"])
        self.thresholds.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.thresholds.verticalHeader().setVisible(False)
        self.thresholds.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.thresholds)

        buttons = QHBoxLayout()
        add = QPushButton("+ Порог")
        add.clicked.connect(self._add_threshold_row)
        remove = QPushButton("Удалить порог")
        remove.clicked.connect(self._remove_threshold_row)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        note = QLabel(
            "Пороги задаются целыми процентами. Оценка выбирается по наибольшему "
            "порогу, который не превышает результат."
        )
        note.setWordWrap(True)
        note.setObjectName("hint")
        layout.addWidget(note)

        return page

    def _build_sections_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        layout.addWidget(
            QLabel("Разделы нужны для отбора вопросов и подсчёта по темам:")
        )
        self.sections = QTableWidget(0, 2)
        self.sections.setHorizontalHeaderLabels(["Название раздела", "Брать вопросов"])
        self.sections.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.sections.verticalHeader().setVisible(False)
        self.sections.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.sections)

        buttons = QHBoxLayout()
        add = QPushButton("+ Раздел")
        add.clicked.connect(self._add_section_row)
        remove = QPushButton("Удалить раздел")
        remove.clicked.connect(self._remove_section_row)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        note = QLabel(
            "Удаление раздела не удаляет вопросы — они станут «вне разделов»."
        )
        note.setWordWrap(True)
        note.setObjectName("hint")
        layout.addWidget(note)

        return page

    # -------------------------------------------------------------- загрузка

    def _load(self) -> None:
        settings = self.test.settings
        self.shuffle_questions.setChecked(settings.shuffle_questions)
        self.shuffle_options.setChecked(settings.shuffle_options)
        self.selection.setCurrentIndex(
            max(0, self.selection.findData(settings.selection_mode))
        )
        self.questions_to_ask.setValue(
            settings.questions_to_ask or max(1, len(self.test.questions))
        )
        self.time_limit.setValue((settings.time_limit_sec or 0) // 60)
        self.allow_back.setChecked(settings.allow_back)
        self.show_result.setChecked(settings.show_result_to_user)
        self.show_review.setChecked(settings.show_review_to_user)

        grading = self.test.grading
        self.multi_mode.setCurrentIndex(max(0, self.multi_mode.findData(grading.multi_mode)))
        self.partial_penalty.setChecked(grading.partial_penalty)
        self.manual_review.setChecked(grading.text_manual_review)
        self.scale_preset.setCurrentIndex(
            max(0, self.scale_preset.findData(grading.scale.type))
        )
        self._fill_thresholds(grading.scale.thresholds)

        self.sections.setRowCount(len(self.test.sections))
        for row, section in enumerate(self.test.sections):
            self.sections.setItem(row, 0, QTableWidgetItem(section.title))
            take = QTableWidgetItem("" if section.take_count is None else str(section.take_count))
            self.sections.setItem(row, 1, take)
            self.sections.item(row, 0).setData(Qt.ItemDataRole.UserRole, section.id)

        self._update_enabled()

    def _fill_thresholds(self, thresholds: list[Threshold]) -> None:
        ordered = sorted(thresholds, key=lambda t: t.min_percent, reverse=True)
        self.thresholds.setRowCount(len(ordered))
        for row, threshold in enumerate(ordered):
            self.thresholds.setItem(row, 0, QTableWidgetItem(str(threshold.min_percent)))
            self.thresholds.setItem(row, 1, QTableWidgetItem(threshold.label))
            passed = QTableWidgetItem()
            passed.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
            )
            passed.setCheckState(
                Qt.CheckState.Checked if threshold.passed else Qt.CheckState.Unchecked
            )
            self.thresholds.setItem(row, 2, passed)

    def _update_enabled(self) -> None:
        mode = self.selection.currentData()
        self.questions_to_ask.setEnabled(mode is SelectionMode.RANDOM)

    def _on_preset_changed(self) -> None:
        preset = self.scale_preset.currentData()
        if preset is ScaleType.PASS_FAIL:
            self._fill_thresholds(Scale.default_pass_fail().thresholds)
        elif preset is ScaleType.FIVE_POINT:
            self._fill_thresholds(Scale.default_five_point().thresholds)
        self.thresholds.setEnabled(True)

    # ------------------------------------------------------------- таблицы

    def _add_threshold_row(self) -> None:
        row = self.thresholds.rowCount()
        self.thresholds.insertRow(row)
        self.thresholds.setItem(row, 0, QTableWidgetItem("0"))
        self.thresholds.setItem(row, 1, QTableWidgetItem("Оценка"))
        passed = QTableWidgetItem()
        passed.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        passed.setCheckState(Qt.CheckState.Unchecked)
        self.thresholds.setItem(row, 2, passed)
        self.scale_preset.setCurrentIndex(self.scale_preset.findData(ScaleType.CUSTOM))

    def _remove_threshold_row(self) -> None:
        row = self.thresholds.currentRow()
        if row >= 0:
            self.thresholds.removeRow(row)
            self.scale_preset.setCurrentIndex(self.scale_preset.findData(ScaleType.CUSTOM))

    def _add_section_row(self) -> None:
        row = self.sections.rowCount()
        self.sections.insertRow(row)
        title = QTableWidgetItem("Новый раздел")
        title.setData(Qt.ItemDataRole.UserRole, None)  # новый раздел — id создастся при ОК
        self.sections.setItem(row, 0, title)
        self.sections.setItem(row, 1, QTableWidgetItem(""))

    def _remove_section_row(self) -> None:
        row = self.sections.currentRow()
        if row >= 0:
            self.sections.removeRow(row)

    # -------------------------------------------------------------- принятие

    def _on_accept(self) -> None:
        thresholds = self._collect_thresholds()
        if thresholds is None:
            return

        settings = self.test.settings
        settings.shuffle_questions = self.shuffle_questions.isChecked()
        settings.shuffle_options = self.shuffle_options.isChecked()
        settings.selection_mode = self.selection.currentData()
        settings.questions_to_ask = (
            self.questions_to_ask.value()
            if settings.selection_mode is SelectionMode.RANDOM
            else None
        )
        minutes = self.time_limit.value()
        settings.time_limit_sec = minutes * 60 if minutes else None
        settings.allow_back = self.allow_back.isChecked()
        settings.show_result_to_user = self.show_result.isChecked()
        settings.show_review_to_user = self.show_review.isChecked()

        grading = self.test.grading
        grading.multi_mode = self.multi_mode.currentData()
        grading.partial_penalty = self.partial_penalty.isChecked()
        grading.text_manual_review = self.manual_review.isChecked()
        grading.scale = Scale(type=self.scale_preset.currentData(), thresholds=thresholds)

        self._apply_sections()
        self.accept()

    def _collect_thresholds(self) -> list[Threshold] | None:
        thresholds: list[Threshold] = []
        for row in range(self.thresholds.rowCount()):
            raw = (self.thresholds.item(row, 0).text() if self.thresholds.item(row, 0) else "").strip()
            try:
                percent = int(raw)
            except ValueError:
                QMessageBox.warning(
                    self, "Шкала",
                    f"Строка {row + 1}: процент должен быть целым числом.",
                )
                return None
            if not 0 <= percent <= 100:
                QMessageBox.warning(
                    self, "Шкала", f"Строка {row + 1}: процент вне диапазона 0–100."
                )
                return None
            label_item = self.thresholds.item(row, 1)
            passed_item = self.thresholds.item(row, 2)
            thresholds.append(
                Threshold(
                    min_percent=percent,
                    label=(label_item.text().strip() if label_item else "") or "Без названия",
                    passed=bool(
                        passed_item and passed_item.checkState() is Qt.CheckState.Checked
                    ),
                )
            )

        if not thresholds:
            QMessageBox.warning(self, "Шкала", "Нужен хотя бы один порог оценки.")
            return None
        if not any(t.min_percent == 0 for t in thresholds):
            QMessageBox.warning(
                self, "Шкала",
                "Нужен порог от 0 % — иначе низкий балл не получит никакой оценки.",
            )
            return None
        return thresholds

    def _apply_sections(self) -> None:
        kept: list[Section] = []
        by_id = {s.id: s for s in self.test.sections}

        for row in range(self.sections.rowCount()):
            title_item = self.sections.item(row, 0)
            if title_item is None:
                continue
            section_id = title_item.data(Qt.ItemDataRole.UserRole)
            section = by_id.get(section_id) or Section()
            section.title = title_item.text().strip() or "Без названия"

            take_item = self.sections.item(row, 1)
            take_raw = take_item.text().strip() if take_item else ""
            section.take_count = int(take_raw) if take_raw.isdigit() else None
            kept.append(section)

        # Вопросы удалённых разделов не теряем — просто выносим «вне разделов».
        alive = {s.id for s in kept}
        for question in self.test.questions:
            if question.section_id and question.section_id not in alive:
                question.section_id = None

        self.test.sections = kept
