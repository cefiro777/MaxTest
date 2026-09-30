"""Выбор теста для прохождения.

Раньше здесь открывался системный диалог выбора файла: администратор каждый
раз искал нужный `.qtest` по папкам. Теперь программа сама показывает готовые
тесты — из своей папки и из недавно открытых, — а файловый диалог остаётся
запасным путём.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ...core.bundle import TestInfo, peek
from ...core.paths import tests_dir
from ...core.recent import RecentTests

FILE_FILTER = "Тесты MaxTest (*.qtest);;Все файлы (*)"
COLUMNS = ("Название теста", "Вопросов", "Файл", "Изменён")


class TestPickerDialog(QDialog):
    # Имя начинается с Test — иначе pytest пытается собрать класс как тест.
    __test__ = False

    def __init__(self, recent: RecentTests | None = None, parent=None) -> None:
        super().__init__(parent)
        self.recent = recent or RecentTests()
        self.selected_path: Path | None = None
        self.setWindowTitle("Выбор теста")
        self.resize(820, 480)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Выберите тест для прохождения:"))

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.doubleClicked.connect(self._on_accept)
        layout.addWidget(self.table, 1)

        self.hint = QLabel(
            f"Тесты берутся из папки {tests_dir()} и из недавно открытых. "
            "Файл из другого места можно выбрать кнопкой «Открыть файл…»."
        )
        self.hint.setObjectName("hint")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

        buttons = QHBoxLayout()
        browse = QPushButton("Открыть файл…")
        browse.clicked.connect(self.browse)
        buttons.addWidget(browse)
        buttons.addStretch(1)

        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        self.start_button = QPushButton("Начать тест")
        self.start_button.setProperty("class", "primary")
        self.start_button.setDefault(True)
        self.start_button.clicked.connect(self._on_accept)
        buttons.addWidget(cancel)
        buttons.addWidget(self.start_button)
        layout.addLayout(buttons)

        self.reload()

    # ------------------------------------------------------------------ данные

    def find_tests(self) -> list[TestInfo]:
        """Тесты из рабочей папки плюс недавно открытые, без повторов."""
        seen: set[Path] = set()
        found: list[TestInfo] = []

        for path in sorted(tests_dir().glob("*.qtest")) + self.recent.list():
            resolved = path.resolve()
            if resolved in seen or not path.exists():
                continue
            seen.add(resolved)
            info = peek(path)
            if info is not None:  # битые и чужие файлы просто не показываем
                found.append(info)
        return found

    def reload(self) -> None:
        self.tests = self.find_tests()
        self.table.setRowCount(len(self.tests))
        for row, info in enumerate(self.tests):
            values = (
                info.title,
                str(info.question_count),
                info.name,
                (info.modified_at or "").replace("T", " ")[:16],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, str(info.path))
                    if info.description:
                        item.setToolTip(info.description)
                self.table.setItem(row, column, item)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        empty = not self.tests
        self.start_button.setEnabled(not empty)
        if empty:
            self.hint.setText(
                f"Готовых тестов не найдено. Положите файлы .qtest в папку "
                f"{tests_dir()} или выберите файл кнопкой «Открыть файл…»."
            )
        else:
            self.table.selectRow(0)

    # ---------------------------------------------------------------- действия

    def browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите тест", str(tests_dir()), FILE_FILTER
        )
        if not path:
            return
        if peek(path) is None:
            QMessageBox.warning(
                self, "Не файл теста",
                "Этот файл не похож на тест MaxTest — внутри нет manifest.json.",
            )
            return
        self.selected_path = Path(path)
        self.recent.add(path)
        self.accept()

    def _on_accept(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.tests):
            return
        self.selected_path = self.tests[row].path
        self.recent.add(self.selected_path)
        self.accept()
