"""Диалоги PIN-кода: ввод и установка."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..core.security import MIN_LENGTH, PinError, PinStore

#: После скольких неудач диалог закрывается. Не «блокировка навсегда» —
#: администратор не должен остаться заперт из-за опечаток, но и подбирать
#: код бесконечными попытками не даём.
MAX_ATTEMPTS = 5


class PinDialog(QDialog):
    """Запрос PIN перед входом в защищённый раздел."""

    def __init__(self, store: PinStore, section: str = "", parent=None) -> None:
        super().__init__(parent)
        self.store = store
        self.attempts = 0
        self.setWindowTitle("Требуется PIN-код")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        title = QLabel(f"Раздел «{section}» защищён PIN-кодом" if section
                       else "Раздел защищён PIN-кодом")
        title.setObjectName("sectionTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        self.pin = QLineEdit()
        self.pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin.setPlaceholderText("PIN-код администратора")
        self.pin.returnPressed.connect(self._on_accept)
        layout.addWidget(self.pin)

        self.error = QLabel()
        self.error.setObjectName("warningNote")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Войти")
        ok.setProperty("class", "primary")
        ok.setDefault(True)
        ok.clicked.connect(self._on_accept)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        layout.addLayout(buttons)

        self.pin.setFocus()

    def _on_accept(self) -> None:
        if self.store.verify(self.pin.text()):
            self.accept()
            return

        self.attempts += 1
        self.pin.clear()
        if self.attempts >= MAX_ATTEMPTS:
            QMessageBox.warning(
                self, "Неверный PIN",
                "Слишком много неудачных попыток. Попробуйте ещё раз позже.",
            )
            self.reject()
            return
        self.error.setText(
            f"Неверный PIN-код. Осталось попыток: {MAX_ATTEMPTS - self.attempts}"
        )


class SetPinDialog(QDialog):
    """Установка или смена PIN-кода."""

    def __init__(self, store: PinStore, parent=None) -> None:
        super().__init__(parent)
        self.store = store
        self.changing = store.is_set()
        self.setWindowTitle("Смена PIN-кода" if self.changing else "Установка PIN-кода")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.current = QLineEdit()
        self.current.setEchoMode(QLineEdit.EchoMode.Password)
        if self.changing:
            form.addRow("Текущий PIN:", self.current)

        self.new_pin = QLineEdit()
        self.new_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.repeat = QLineEdit()
        self.repeat.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Новый PIN:", self.new_pin)
        form.addRow("Повторите:", self.repeat)
        layout.addLayout(form)

        note = QLabel(
            f"Не короче {MIN_LENGTH} символов. PIN закрывает конструктор, "
            "результаты, проверку ответов и справочник сотрудников — то, что "
            "сотруднику видеть не нужно.\n\n"
            "Забытый PIN восстановить нельзя: снимается только удалением файла "
            "security.json из папки данных."
        )
        note.setObjectName("hint")
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QHBoxLayout()
        if self.changing:
            remove = QPushButton("Снять защиту")
            remove.setProperty("class", "danger")
            remove.clicked.connect(self._on_remove)
            buttons.addWidget(remove)
        buttons.addStretch(1)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Сохранить")
        ok.setProperty("class", "primary")
        ok.setDefault(True)
        ok.clicked.connect(self._on_accept)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        layout.addLayout(buttons)

    def _check_current(self) -> bool:
        if not self.changing:
            return True
        if self.store.verify(self.current.text()):
            return True
        QMessageBox.warning(self, "PIN-код", "Текущий PIN указан неверно.")
        return False

    def _on_accept(self) -> None:
        if not self._check_current():
            return
        if self.new_pin.text() != self.repeat.text():
            QMessageBox.warning(self, "PIN-код", "Введённые коды не совпадают.")
            return
        try:
            self.store.set_pin(self.new_pin.text())
        except PinError as exc:
            QMessageBox.warning(self, "PIN-код", str(exc))
            return
        except OSError as exc:
            QMessageBox.critical(self, "PIN-код", f"Не удалось сохранить: {exc}")
            return
        self.accept()

    def _on_remove(self) -> None:
        if not self._check_current():
            return
        confirm = QMessageBox.question(
            self,
            "Снять защиту",
            "Убрать PIN-код? Все разделы станут доступны без ввода кода.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm is QMessageBox.StandardButton.Yes:
            self.store.clear()
            self.accept()
