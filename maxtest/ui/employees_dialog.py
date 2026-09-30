"""Справочник сотрудников.

Сотрудники не удаляются, а скрываются: удалённая запись унесла бы историю
аттестаций за прошлые годы.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..core.storage import Employee, Storage


class EmployeeDialog(QDialog):
    """Карточка одного сотрудника."""

    def __init__(self, employee: Employee | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Сотрудник")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.full_name = QLineEdit(employee.full_name if employee else "")
        self.full_name.setPlaceholderText("Иванов Иван Иванович")
        self.position = QLineEdit(employee.position if employee else "")
        self.department = QLineEdit(employee.department if employee else "")
        form.addRow("ФИО:", self.full_name)
        form.addRow("Должность:", self.position)
        form.addRow("Подразделение:", self.department)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        if len(" ".join(self.full_name.text().split())) < 3:
            QMessageBox.warning(self, "ФИО", "Укажите ФИО сотрудника.")
            return
        self.accept()

    @property
    def values(self) -> tuple[str, str, str]:
        return (
            " ".join(self.full_name.text().split()),
            self.position.text().strip(),
            self.department.text().strip(),
        )


class EmployeesDialog(QDialog):
    COLUMNS = ("ФИО", "Должность", "Подразделение")

    def __init__(self, storage: Storage, parent=None) -> None:
        super().__init__(parent)
        self.storage = storage
        self.setWindowTitle("Сотрудники")
        self.resize(720, 480)

        layout = QVBoxLayout(self)

        self.show_hidden = QCheckBox("Показывать скрытых")
        self.show_hidden.toggled.connect(self.reload)
        layout.addWidget(self.show_hidden)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.doubleClicked.connect(self.edit_employee)
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        for text, slot in (
            ("Добавить", self.add_employee),
            ("Изменить", self.edit_employee),
            ("Скрыть / вернуть", self.toggle_active),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch(1)
        close = QPushButton("Закрыть")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self.hint = QLabel("Сотрудники не удаляются, а скрываются — история аттестаций сохраняется.")
        self.hint.setObjectName("hint")
        layout.addWidget(self.hint)

        self.reload()

    # ------------------------------------------------------------------ данные

    def reload(self) -> None:
        employees = self.storage.list_employees(active_only=not self.show_hidden.isChecked())
        self.table.setRowCount(len(employees))
        for row, employee in enumerate(employees):
            active = self.storage.is_employee_active(employee.id)
            name = QTableWidgetItem(employee.full_name + ("" if active else "  (скрыт)"))
            name.setData(Qt.ItemDataRole.UserRole, employee.id)
            if not active:
                name.setForeground(Qt.GlobalColor.gray)
            self.table.setItem(row, 0, name)
            self.table.setItem(row, 1, QTableWidgetItem(employee.position))
            self.table.setItem(row, 2, QTableWidgetItem(employee.department))

    @property
    def selected_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selected_employee(self) -> Employee | None:
        employee_id = self.selected_id
        if employee_id is None:
            return None
        return next(
            (
                e
                for e in self.storage.list_employees(active_only=False)
                if e.id == employee_id
            ),
            None,
        )

    # ---------------------------------------------------------------- действия

    def add_employee(self) -> None:
        dialog = EmployeeDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, position, department = dialog.values
        if self.storage.find_employee(name) is not None:
            QMessageBox.warning(self, "Сотрудник", "Такой сотрудник уже есть в списке.")
            return
        self.storage.add_employee(name, position, department)
        self.reload()

    def edit_employee(self) -> None:
        employee = self._selected_employee()
        if employee is None:
            return
        dialog = EmployeeDialog(employee, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, position, department = dialog.values
        duplicate = self.storage.find_employee(name)
        if duplicate is not None and duplicate.id != employee.id:
            QMessageBox.warning(self, "Сотрудник", "Такой сотрудник уже есть в списке.")
            return
        self.storage.update_employee(employee.id, name, position, department)
        self.reload()

    def toggle_active(self) -> None:
        employee_id = self.selected_id
        if employee_id is None:
            return
        active = self.storage.is_employee_active(employee_id)
        self.storage.set_employee_active(employee_id, not active)
        self.reload()
