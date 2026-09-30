"""Диалог перед началом теста: кто проходит и что именно.

Сотрудник выбирается из списка, а не вводится с клавиатуры: за год человек
успевает забыть, как записывал себя в прошлый раз, и в базе появляются
«Иванов И.И.», «Иванов Иван» и «иванов и и» — три разных человека в отчёте.
Ввод нового имени остаётся, но это отдельное осознанное действие.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ...core.models import Test
from ...core.storage import Storage


class StartDialog(QDialog):
    def __init__(self, test: Test, storage: Storage, question_count: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Начало тестирования")
        self.resize(560, 620)
        self._storage = storage
        self.employee_name = ""
        self.employee_id: int | None = None

        layout = QVBoxLayout(self)

        header = QLabel(f"<h3>{test.title}</h3>")
        header.setWordWrap(True)
        layout.addWidget(header)

        if test.description:
            description = QLabel(test.description)
            description.setObjectName("hint")
            description.setWordWrap(True)
            layout.addWidget(description)

        form = QFormLayout()
        form.addRow("Вопросов в тесте:", QLabel(str(question_count)))
        limit = test.settings.time_limit_sec
        form.addRow("Ограничение времени:", QLabel(f"{limit // 60} мин" if limit else "нет"))
        layout.addLayout(form)

        layout.addWidget(QLabel("Выберите себя в списке:"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по фамилии…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        layout.addWidget(self.search)

        self.employees = QListWidget()
        self.employees.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.employees.itemSelectionChanged.connect(self._on_selection_changed)
        self.employees.itemDoubleClicked.connect(lambda _: self._on_accept())
        layout.addWidget(self.employees, 1)

        new_row = QHBoxLayout()
        self.new_name = QLineEdit()
        self.new_name.setPlaceholderText("Нет в списке — введите ФИО")
        self.new_name.textChanged.connect(self._on_new_name_changed)
        new_row.addWidget(self.new_name, 1)
        layout.addLayout(new_row)

        self.status = QLabel()
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        self.start_button = QPushButton("Начать")
        self.start_button.setProperty("class", "primary")
        self.start_button.setDefault(True)
        self.start_button.clicked.connect(self._on_accept)
        buttons.addWidget(cancel)
        buttons.addWidget(self.start_button)
        layout.addLayout(buttons)

        self._load_employees()

    # ------------------------------------------------------------------ данные

    def _load_employees(self) -> None:
        self.employees.clear()
        for employee in self._storage.list_employees():
            details = " · ".join(x for x in (employee.position, employee.department) if x)
            item = QListWidgetItem(
                f"{employee.full_name}\n{details}" if details else employee.full_name
            )
            item.setData(Qt.ItemDataRole.UserRole, employee.id)
            item.setData(Qt.ItemDataRole.UserRole + 1, employee.full_name)
            self.employees.addItem(item)

        if self.employees.count() == 0:
            self.status.setText(
                "Список сотрудников пуст. Введите ФИО ниже — человек добавится "
                "в справочник и в следующий раз будет в списке."
            )
            self.new_name.setFocus()
        else:
            self._update_state()

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().casefold().replace("ё", "е")
        for row in range(self.employees.count()):
            item = self.employees.item(row)
            name = item.data(Qt.ItemDataRole.UserRole + 1).casefold().replace("ё", "е")
            item.setHidden(bool(needle) and needle not in name)

    # --------------------------------------------------------------- состояние

    def _on_selection_changed(self) -> None:
        if self.employees.selectedItems() and self.new_name.text().strip():
            # Выбор из списка отменяет начатый ввод нового имени, иначе
            # непонятно, кто именно сейчас будет проходить тест.
            self.new_name.blockSignals(True)
            self.new_name.clear()
            self.new_name.blockSignals(False)
        self._update_state()

    def _on_new_name_changed(self, text: str) -> None:
        if text.strip():
            self.employees.clearSelection()
        self._update_state()

    def _current_name(self) -> str:
        typed = " ".join(self.new_name.text().split())
        if typed:
            return typed
        items = self.employees.selectedItems()
        return items[0].data(Qt.ItemDataRole.UserRole + 1) if items else ""

    def _update_state(self) -> None:
        name = self._current_name()
        self.start_button.setEnabled(len(name) >= 3)

        if not name:
            if self.employees.count():
                self.status.setText("Выберите себя в списке или введите новое ФИО.")
            return

        if self.new_name.text().strip():
            existing = self._storage.find_employee(name)
            self.status.setText(
                f"Этот сотрудник уже есть в списке: {existing.full_name}"
                if existing
                else f"Будет добавлен новый сотрудник: {name}"
            )
        else:
            self.status.setText(f"Тест будет проходить: {name}")

    # ---------------------------------------------------------------- действия

    def _on_accept(self) -> None:
        name = self._current_name()
        if len(name) < 3:
            QMessageBox.warning(
                self, "Укажите ФИО", "Выберите сотрудника из списка или введите ФИО."
            )
            return
        self.employee_name = name
        # Дубли по регистру и «ё» отсекает name_key в хранилище.
        self.employee_id = self._storage.get_or_create_employee(name)
        self.accept()
