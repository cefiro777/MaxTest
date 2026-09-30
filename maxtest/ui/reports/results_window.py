"""Результаты тестирования: фильтры, разбор попытки, выгрузка в Excel."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
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

from ...core.paths import data_dir
from ...core.storage import Storage
from ...report.excel import export_attempts, stats_of
from .attempt_dialog import AttemptDialog

COLUMNS = ("Сотрудник", "Тест", "Дата", "Баллы", "%", "Оценка", "Итог", "Примечание")


class ResultsWindow(QDialog):
    def __init__(self, storage: Storage, parent=None) -> None:
        super().__init__(parent)
        self.storage = storage
        self.rows: list = []
        self.setWindowTitle("Результаты тестирования")
        self.resize(1080, 640)

        layout = QVBoxLayout(self)
        layout.addLayout(self._build_filters())

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.doubleClicked.connect(self.show_attempt)
        layout.addWidget(self.table, 1)

        self.summary = QLabel()
        layout.addWidget(self.summary)
        layout.addLayout(self._build_buttons())

        self.reload()

    # --------------------------------------------------------------- фильтры

    def _build_filters(self) -> QHBoxLayout:
        row = QHBoxLayout()

        self.test_filter = QComboBox()
        self.test_filter.addItem("Все тесты", None)
        for test in self.storage.list_tests():
            self.test_filter.addItem(
                f"{test['test_title']} ({test['attempts']})", test["test_id"]
            )
        self.test_filter.currentIndexChanged.connect(self.reload)

        self.employee_filter = QComboBox()
        self.employee_filter.addItem("Все сотрудники", None)
        for employee in self.storage.list_employees(active_only=False):
            self.employee_filter.addItem(employee.full_name, employee.id)
        self.employee_filter.currentIndexChanged.connect(self.reload)

        self.date_from = QDateEdit(QDate(date.today().year, 1, 1))
        self.date_to = QDateEdit(QDate.currentDate())
        for widget in (self.date_from, self.date_to):
            widget.setCalendarPopup(True)
            widget.setDisplayFormat("dd.MM.yyyy")
            widget.dateChanged.connect(self.reload)

        self.only_failed = QCheckBox("Только не сдавшие")
        self.only_failed.toggled.connect(self.reload)

        row.addWidget(QLabel("Тест:"))
        row.addWidget(self.test_filter, 2)
        row.addWidget(QLabel("Сотрудник:"))
        row.addWidget(self.employee_filter, 1)
        row.addWidget(QLabel("с"))
        row.addWidget(self.date_from)
        row.addWidget(QLabel("по"))
        row.addWidget(self.date_to)
        row.addWidget(self.only_failed)
        return row

    def _build_buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        for text, slot in (
            ("Разбор попытки", self.show_attempt),
            ("Выгрузить в Excel", self.export_excel),
            ("Удалить попытку", self.delete_attempt),
            ("Резервная копия базы", self.backup_database),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            row.addWidget(button)
        row.addStretch(1)
        close = QPushButton("Закрыть")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        return row

    # ----------------------------------------------------------------- данные

    def reload(self) -> None:
        self.rows = self.storage.list_attempts(
            test_id=self.test_filter.currentData(),
            employee_id=self.employee_filter.currentData(),
            date_from=self.date_from.date().toString("yyyy-MM-dd"),
            date_to=self.date_to.date().toString("yyyy-MM-dd"),
            only_failed=self.only_failed.isChecked(),
        )

        self.table.setRowCount(len(self.rows))
        for index, row in enumerate(self.rows):
            notes = []
            if row["needs_review"]:
                notes.append("требует проверки")
            if row["finish_reason"] == "timeout":
                notes.append("время вышло")
            elif row["finish_reason"] == "aborted":
                notes.append("прервано")

            values = (
                row["employee_name"],
                row["test_title"],
                (row["started_at"] or "").replace("T", " ")[:16],
                f"{row['score']:.2f} / {row['max_score']:.2f}",
                str(row["percent"]),
                row["grade_label"] or "",
                "Сдал" if row["passed"] else "Не сдал",
                ", ".join(notes),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row["id"])
                if not row["passed"]:
                    item.setForeground(Qt.GlobalColor.darkRed)
                self.table.setItem(index, column, item)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )

        stats = stats_of(self.rows)
        self.summary.setText(
            f"Попыток: {stats.attempts} · сдали: {stats.passed} · "
            f"не сдали: {stats.failed} · средний результат: {stats.average_percent}%"
        )

    @property
    def selected_attempt_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    # --------------------------------------------------------------- действия

    def show_attempt(self) -> None:
        attempt_id = self.selected_attempt_id
        if attempt_id is None:
            QMessageBox.information(self, "Разбор", "Выберите попытку в списке.")
            return
        AttemptDialog(self.storage, attempt_id, self).exec()

    def export_excel(self) -> None:
        if not self.rows:
            QMessageBox.information(self, "Выгрузка", "Нечего выгружать: список пуст.")
            return

        suggested = data_dir() / f"результаты_{date.today():%Y-%m-%d}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить отчёт", str(suggested), "Книга Excel (*.xlsx)"
        )
        if not path:
            return
        try:
            saved = export_attempts(self.storage, self.rows, Path(path))
        except OSError as exc:
            # Типичный случай: файл открыт в Excel и заблокирован.
            QMessageBox.critical(
                self, "Не удалось сохранить",
                f"{exc}\n\nЗакройте файл в Excel и повторите.",
            )
            return
        QMessageBox.information(self, "Готово", f"Отчёт сохранён:\n{saved}")

    def delete_attempt(self) -> None:
        attempt_id = self.selected_attempt_id
        if attempt_id is None:
            return
        attempt = self.storage.get_attempt(attempt_id)
        reply = QMessageBox.question(
            self,
            "Удалить попытку",
            f"Удалить попытку «{attempt['employee_name']} — {attempt['test_title']}»?\n"
            "Восстановить её можно будет только из резервной копии базы.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply is not QMessageBox.StandardButton.Yes:
            return
        self.storage.delete_attempt(attempt_id)
        self.reload()

    def backup_database(self) -> None:
        try:
            path = self.storage.backup(force=True)
        except OSError as exc:
            QMessageBox.critical(self, "Резервная копия", str(exc))
            return
        QMessageBox.information(
            self, "Резервная копия", f"Копия базы результатов:\n{path}"
        )
