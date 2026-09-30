"""Стартовое окно: конструктор, прохождение теста, результаты."""

from __future__ import annotations

import time

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.bundle import Bundle, BundleError
from ..core.grader import SUPPORTED_TYPES
from ..core.paths import data_dir
from ..core.progress import PendingAttempt, ProgressStore
from ..core.recent import RecentTests
from ..core.security import PinStore
from ..core.session import AttemptPlan, build_plan
from ..core.storage import Storage
from .editor.editor_window import EditorWindow
from .employees_dialog import EmployeesDialog
from .player.player_window import PlayerWindow
from .donate_dialog import DonateDialog
from .pin_dialog import PinDialog, SetPinDialog
from .player.start_dialog import StartDialog
from .player.test_picker import TestPickerDialog
from .reports.results_window import ResultsWindow
from .reports.review_dialog import ReviewDialog
from .widgets.tile import Tile

#: Сколько минут разделы остаются открытыми после верного ввода PIN.
UNLOCK_MINUTES = 15


class AppWindow(QMainWindow):
    def __init__(self, storage: Storage, progress: ProgressStore | None = None) -> None:
        super().__init__()
        self.storage = storage
        self.progress = progress or ProgressStore()
        self.recent = RecentTests()
        self.pin = PinStore()
        self._unlocked_until = 0.0
        # Ссылки на окна нужны, иначе Python соберёт их сборщиком мусора
        # сразу после показа и окно молча исчезнет.
        self._windows: list[QMainWindow] = []

        self.setWindowTitle("MaxTest")
        self.setMinimumSize(520, 380)
        self._build_ui()

    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(40, 34, 40, 26)
        layout.setSpacing(18)

        title = QLabel("MaxTest")
        title.setObjectName("heroTitle")
        layout.addWidget(title)

        subtitle = QLabel(
            "Аттестация сотрудников · данные хранятся только на этом компьютере"
        )
        subtitle.setObjectName("heroSubtitle")
        layout.addWidget(subtitle)

        layout.addLayout(self._build_stats())

        # Плитки: заголовок действия и пояснение под ним — понятно без обучения.
        tiles = QGridLayout()
        tiles.setSpacing(12)
        actions = (
            ("Пройти тест", "Запустить тестирование сотрудника", self.run_test, True),
            ("Конструктор тестов", "Создать или изменить тест", self.open_editor, False),
            ("Результаты", "Отчёты, разбор попыток, выгрузка в Excel", self.show_results, False),
            ("Сотрудники", "Список тех, кто проходит аттестацию", self.show_employees, False),
        )
        for index, (caption, hint, slot, primary) in enumerate(actions):
            tile = Tile(caption, hint, primary)
            tile.clicked.connect(slot)
            tiles.addWidget(tile, index // 2, index % 2)

        self.review_button = Tile("Проверка ответов")
        self.review_button.clicked.connect(self.show_review)
        tiles.addWidget(self.review_button, 2, 0, 1, 2)
        layout.addLayout(tiles)

        layout.addStretch(1)
        layout.addLayout(self._build_security_row())

        footer = QLabel(f"Папка данных: {data_dir()}")
        footer.setObjectName("footerNote")
        footer.setWordWrap(True)
        layout.addWidget(footer)

        self.setCentralWidget(central)
        self.refresh_review_button()
        self.refresh_stats()
        self.refresh_security()

    def _build_security_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.security_label = QLabel()
        self.security_label.setObjectName("hint")
        self.pin_button = QPushButton()
        self.pin_button.clicked.connect(self.change_pin)
        self.lock_button = QPushButton("Заблокировать")
        self.lock_button.setToolTip(
            "Закрыть административные разделы до следующего ввода PIN-кода"
        )
        self.lock_button.clicked.connect(self.lock)

        self.donate_button = QPushButton("♥ Поддержать проект")
        self.donate_button.setToolTip("Перевод через СБП по QR-коду — по желанию")
        self.donate_button.clicked.connect(self.show_donate)

        row.addWidget(self.security_label, 1)
        row.addWidget(self.donate_button)
        row.addWidget(self.lock_button)
        row.addWidget(self.pin_button)
        return row

    def show_donate(self) -> None:
        DonateDialog(self).exec()

    def _build_stats(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        self.stat_attempts = QLabel()
        self.stat_attempts.setProperty("class", "statChip")
        self.stat_employees = QLabel()
        self.stat_employees.setProperty("class", "statChip")
        self.stat_review = QLabel()
        self.stat_review.setProperty("class", "statChipAccent")
        for widget in (self.stat_attempts, self.stat_employees, self.stat_review):
            row.addWidget(widget)
        row.addStretch(1)
        return row

    def refresh_stats(self) -> None:
        if not self.storage.is_open:
            return
        attempts = len(self.storage.list_attempts(limit=100_000))
        employees = len(self.storage.list_employees())
        pending = self.storage.count_attempts_to_review()

        self.stat_attempts.setText(f"Попыток в базе: {attempts}")
        self.stat_employees.setText(f"Сотрудников: {employees}")
        self.stat_review.setText(f"Ждут проверки: {pending}")
        self.stat_review.setVisible(bool(pending))

    def shutdown(self) -> None:
        """Закрывает дочерние окна до закрытия базы.

        Порядок важен: сначала окна, потом соединение с SQLite, иначе
        обработчики умирающих окон обращаются к закрытой базе.
        """
        for window in self._windows:
            window.close()
        self._windows.clear()

    # ------------------------------------------------------------- защита

    def require_pin(self, section: str) -> bool:
        """Пускает в защищённый раздел. ``True`` — можно продолжать.

        После верного ввода раздел остаётся открытым ``UNLOCK_MINUTES`` минут:
        спрашивать код при каждом переходе между конструктором и отчётами —
        это гарантия того, что администратор снимет защиту совсем.
        """
        if not self.pin.is_set():
            return True
        if time.monotonic() < self._unlocked_until:
            self._unlocked_until = time.monotonic() + UNLOCK_MINUTES * 60
            return True

        dialog = PinDialog(self.pin, section, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        self._unlocked_until = time.monotonic() + UNLOCK_MINUTES * 60
        self.refresh_security()
        return True

    @property
    def unlocked(self) -> bool:
        return self.pin.is_set() and time.monotonic() < self._unlocked_until

    def lock(self) -> None:
        self._unlocked_until = 0.0
        self.refresh_security()

    def change_pin(self) -> None:
        # Смена кода — сама по себе защищённое действие.
        if self.pin.is_set() and not self.require_pin("Настройка защиты"):
            return
        if SetPinDialog(self.pin, self).exec() == QDialog.DialogCode.Accepted:
            self._unlocked_until = time.monotonic() + UNLOCK_MINUTES * 60
        self.refresh_security()

    def refresh_security(self) -> None:
        if self.pin.is_set():
            state = "разделы открыты" if self.unlocked else "разделы закрыты"
            self.security_label.setText(f"🔒 PIN-код задан · {state}")
            self.pin_button.setText("Изменить PIN")
        else:
            self.security_label.setText("🔓 PIN-код не задан — разделы открыты всем")
            self.pin_button.setText("Задать PIN")
        self.lock_button.setVisible(self.unlocked)

    # ------------------------------------------------------------ конструктор

    def open_editor(self) -> None:
        if not self.require_pin("Конструктор тестов"):
            return
        window = EditorWindow()
        window.show()
        self._windows.append(window)

    # -------------------------------------------------------------- тестирование

    def run_test(self) -> None:
        picker = TestPickerDialog(self.recent, self)
        if picker.exec() != QDialog.DialogCode.Accepted or picker.selected_path is None:
            return
        path = picker.selected_path

        try:
            bundle = Bundle.load(path)
        except BundleError as exc:
            QMessageBox.critical(self, "Не удалось открыть тест", str(exc))
            return

        plan = build_plan(bundle.test)
        plan, skipped = self._drop_unsupported(bundle, plan)

        if not plan.question_ids:
            QMessageBox.warning(
                self, "Тест пуст",
                "В тесте нет вопросов, которые эта версия умеет оценивать.",
            )
            return

        if skipped:
            QMessageBox.information(
                self, "Часть вопросов пропущена",
                f"Пропущено вопросов неподдерживаемых типов: {skipped}.\n"
                "Они появятся в следующей версии программы.",
            )

        dialog = StartDialog(bundle.test, self.storage, len(plan.question_ids), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self._start_player(bundle, plan, dialog.employee_name, dialog.employee_id)

    def _start_player(
        self,
        bundle: Bundle,
        plan,
        employee_name: str,
        employee_id: int | None,
        resume: PendingAttempt | None = None,
    ) -> None:
        window = PlayerWindow(
            bundle,
            plan,
            self.storage,
            employee_name,
            employee_id,
            progress=self.progress,
            resume=resume,
        )
        # За компьютер садится сотрудник — административные разделы
        # закрываем сразу, не дожидаясь истечения времени разблокировки.
        self.lock()
        window.showMaximized()
        self._windows.append(window)

    @staticmethod
    def _drop_unsupported(bundle: Bundle, plan) -> tuple:
        """Выбрасывает из плана вопросы, которые движок пока не оценивает."""
        kept = []
        for qid in plan.question_ids:
            q = bundle.test.question_by_id(qid)
            if q is not None and q.type in SUPPORTED_TYPES:
                kept.append(qid)
        skipped = len(plan.question_ids) - len(kept)
        plan.question_ids = kept
        plan.option_order = {k: v for k, v in plan.option_order.items() if k in kept}
        return plan, skipped

    # ------------------------------------------------- восстановление после сбоя

    def check_pending_attempts(self) -> None:
        """Незавершённые попытки после вылета или отключения питания."""
        for pending in self.progress.list_pending():
            self._offer_recovery(pending)

    def _offer_recovery(self, pending: PendingAttempt) -> None:
        answer = QMessageBox.question(
            self,
            "Незавершённое тестирование",
            f"Найдена прерванная попытка:\n\n"
            f"Сотрудник: {pending.employee_name}\n"
            f"Тест: {pending.test_title}\n"
            f"Отвечено вопросов: {pending.answered_count} из {pending.total_count}\n"
            f"Прервано: {pending.saved_at.replace('T', ' ')}\n\n"
            "Продолжить с того же места?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer is not QMessageBox.StandardButton.Yes:
            self.progress.delete(pending.id)
            return

        try:
            bundle = Bundle.load(pending.test_path)
        except BundleError as exc:
            QMessageBox.warning(
                self,
                "Файл теста не найден",
                f"Продолжить не удалось: {exc}\n\nЗапись о попытке удалена.",
            )
            self.progress.delete(pending.id)
            return

        if bundle.test.id != pending.test_id:
            QMessageBox.warning(
                self,
                "Тест изменился",
                "Файл теста по этому пути — уже другой тест. Продолжить нельзя.",
            )
            self.progress.delete(pending.id)
            return

        self._start_player(
            bundle,
            AttemptPlan.from_dict(pending.plan),
            pending.employee_name,
            pending.employee_id,
            resume=pending,
        )

    # ---------------------------------------------------------------- результаты

    def show_results(self) -> None:
        if not self.require_pin("Результаты"):
            return
        ResultsWindow(self.storage, self).exec()
        self.refresh_review_button()

    def show_employees(self) -> None:
        if not self.require_pin("Сотрудники"):
            return
        EmployeesDialog(self.storage, self).exec()
        self.refresh_stats()

    def show_review(self) -> None:
        if not self.require_pin("Проверка ответов"):
            return
        ReviewDialog(self.storage, self).exec()
        self.refresh_review_button()

    def event(self, event):
        """Счётчик обновляем при возврате в главное окно.

        Раньше он обновлялся по сигналу ``destroyed`` окна прохождения — но Qt
        уничтожает окна уже ПОСЛЕ выхода из ``app.exec()``, когда база закрыта,
        и при выходе из программы вылетала ``sqlite3.ProgrammingError``.
        """
        if event.type() == QEvent.Type.WindowActivate:
            self.refresh_review_button()
            self.refresh_stats()
            self.refresh_security()  # время разблокировки могло истечь
        return super().event(event)

    def refresh_review_button(self) -> None:
        if not self.storage.is_open:
            return  # приложение закрывается, окна ещё живы, база — уже нет
        pending = self.storage.count_attempts_to_review()
        if pending:
            self.review_button.setText(
                f"Проверка ответов ({pending})",
                "Развёрнутые текстовые ответы, которые нужно оценить вручную",
            )
        else:
            self.review_button.setText(
                "Проверка ответов",
                "Появится, когда сотрудник ответит на вопрос с вводом текста",
            )
        self.review_button.setEnabled(bool(pending))
