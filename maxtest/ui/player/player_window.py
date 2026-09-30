"""Прохождение теста: таймер, навигация, автосохранение прогресса."""

from __future__ import annotations

import time
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...core.bundle import Bundle
from ...core.enums import FinishReason
from ...core.grader import AttemptResult, grade_attempt
from ...core.progress import PendingAttempt, ProgressStore
from ...core.session import AttemptPlan
from ...core.storage import Storage
from .. import theme
from ..widgets.question_view import QuestionView

AUTOSAVE_MS = 15_000
#: За сколько секунд до конца подсвечивать таймер.
WARN_SECONDS = 300


class PlayerWindow(QMainWindow):
    def __init__(
        self,
        bundle: Bundle,
        plan: AttemptPlan,
        storage: Storage,
        employee_name: str,
        employee_id: int | None = None,
        show_result_dialog: bool = True,
        progress: ProgressStore | None = None,
        resume: PendingAttempt | None = None,
    ) -> None:
        super().__init__()
        self.bundle = bundle
        self.plan = plan
        self.storage = storage
        self.employee_name = employee_name
        self.employee_id = employee_id
        #: Модальный экран результата. Отключается в автотестах — ``exec()``
        #: без пользователя блокирует прогон навсегда.
        self.show_result_dialog = show_result_dialog
        self.progress = progress

        self.answers: dict[str, dict | None] = dict(resume.answers) if resume else {}
        self.index = resume.index if resume else 0
        self.started_at = (
            resume.started_at
            if resume
            else datetime.now().replace(microsecond=0).isoformat()
        )
        self._finished = False

        # Время считаем по monotonic: перевод системных часов не должен
        # ни продлевать, ни обрывать тест.
        self._elapsed_base = float(resume.elapsed_sec) if resume else 0.0
        self._started_monotonic = time.monotonic()
        self._question_started = self.elapsed
        self._warned = False

        self.pending = resume or PendingAttempt(
            test_path=str(bundle.path or ""),
            test_id=bundle.test.id,
            test_title=bundle.test.title,
            employee_name=employee_name,
            employee_id=employee_id,
            started_at=self.started_at,
            plan=plan.to_dict(),
        )

        self.setWindowTitle(f"MaxTest — {bundle.test.title}")
        self.resize(1000, 760)
        self._build_ui()
        self._setup_timers()
        self._show_current()

    # ------------------------------------------------------------------ время

    @property
    def elapsed(self) -> float:
        return self._elapsed_base + (time.monotonic() - self._started_monotonic)

    @property
    def time_left(self) -> float | None:
        limit = self.bundle.test.settings.time_limit_sec
        return None if not limit else max(0.0, limit - self.elapsed)

    # -------------------------------------------------------------- интерфейс

    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QWidget()
        header.setObjectName("playerHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(28, 14, 28, 14)
        header_layout.setSpacing(18)

        employee = QLabel(self.employee_name)
        employee.setObjectName("playerEmployee")
        self.counter = QLabel()
        self.counter.setObjectName("playerCounter")
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(len(self.plan.question_ids))
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMaximumWidth(340)
        self.clock = QLabel()
        self.clock.setObjectName("playerClock")

        header_layout.addWidget(employee)
        header_layout.addStretch(1)
        header_layout.addWidget(self.counter)
        header_layout.addWidget(self.progress_bar, 1)
        header_layout.addWidget(self.clock)
        layout.addWidget(header)

        # Вопрос — карточка по центру с ограничением ширины: длинная строка
        # во весь экран 24" читается плохо.
        self.view = QuestionView()
        self.view.setObjectName("questionCard")
        self.view.setMaximumWidth(1080)
        # Карточка по высоте — ровно по содержимому, а не во весь экран.
        self.view.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        holder = QWidget()
        holder_layout = QHBoxLayout(holder)
        holder_layout.setContentsMargins(28, 24, 28, 24)
        holder_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        holder_layout.addStretch(1)
        holder_layout.addWidget(self.view, 6)
        holder_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(holder)
        layout.addWidget(scroll, 1)

        footer = QWidget()
        footer.setObjectName("playerFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(28, 14, 28, 14)
        self.back_button = QPushButton("← Назад")
        self.back_button.setObjectName("playerBack")
        self.back_button.clicked.connect(self._on_back)
        self.back_button.setVisible(self.bundle.test.settings.allow_back)
        footer_layout.addWidget(self.back_button)

        footer_layout.addStretch(1)
        self.next_button = QPushButton("Далее →")
        self.next_button.setObjectName("playerNext")
        self.next_button.setProperty("class", "primary")
        self.next_button.setDefault(True)
        self.next_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_button.clicked.connect(self._on_next)
        footer_layout.addWidget(self.next_button)
        layout.addWidget(footer)

        self.setCentralWidget(central)

    def _setup_timers(self) -> None:
        self.tick_timer = QTimer(self)
        self.tick_timer.setInterval(1000)
        self.tick_timer.timeout.connect(self._on_tick)
        self.tick_timer.start()

        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(AUTOSAVE_MS)
        self.autosave_timer.timeout.connect(self.save_progress)
        if self.progress is not None:
            self.autosave_timer.start()

        self._update_clock()

    # ------------------------------------------------------------------ ход

    def _show_current(self) -> None:
        qid = self.plan.question_ids[self.index]
        question = self.bundle.test.question_by_id(qid)
        if question is None:  # вопрос удалили из теста между сохранениями
            self._advance()
            return

        self.view.set_question(
            question,
            option_order=self.plan.option_order.get(qid),
            item_order=self.plan.item_order.get(qid),
            image=self.bundle.get_image_bytes(question.image),
            answer=self.answers.get(qid),
        )
        total = len(self.plan.question_ids)
        self.counter.setText(f"Вопрос {self.index + 1} из {total}")
        self.progress_bar.setValue(self.index)
        self.next_button.setText("Завершить" if self.index == total - 1 else "Далее →")
        self.back_button.setEnabled(self.index > 0)
        self._question_started = self.elapsed

    def _capture_answer(self) -> None:
        self.answers[self.plan.question_ids[self.index]] = self.view.answer()

    def _on_next(self) -> None:
        # Блокируем кнопку: двойной клик иначе перескакивает вопрос.
        self.next_button.setEnabled(False)
        try:
            answer = self.view.answer()
            if answer is None and not self._confirm_skip():
                return
            self.answers[self.plan.question_ids[self.index]] = answer
            self._advance()
            # Сохраняем ПОСЛЕ перехода: иначе восстановление вернёт человека
            # на уже отвеченный вопрос. При завершении вызов ничего не делает —
            # файл прогресса к этому моменту уже удалён.
            self.save_progress()
        finally:
            self.next_button.setEnabled(True)

    def _on_back(self) -> None:
        if self.index == 0:
            return
        self._capture_answer()  # уходя, не теряем то, что уже отмечено
        self.index -= 1
        self._show_current()

    def _confirm_skip(self) -> bool:
        allow_back = self.bundle.test.settings.allow_back
        tail = (
            "Вы сможете вернуться к нему позже."
            if allow_back
            else "Вернуться к этому вопросу будет нельзя."
        )
        reply = QMessageBox.question(
            self,
            "Ответ не выбран",
            f"Вы не выбрали ответ. Перейти к следующему вопросу?\n{tail}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply is QMessageBox.StandardButton.Yes

    def _advance(self) -> None:
        if self.index + 1 >= len(self.plan.question_ids):
            if not self._confirm_finish():
                return
            self._finish(FinishReason.COMPLETED)
        else:
            self.index += 1
            self._show_current()

    def _confirm_finish(self) -> bool:
        """С навигацией назад стоит предупредить о пропущенных вопросах."""
        if not self.bundle.test.settings.allow_back:
            return True
        unanswered = sum(
            1 for qid in self.plan.question_ids if not self.answers.get(qid)
        )
        if not unanswered:
            return True
        reply = QMessageBox.question(
            self,
            "Есть вопросы без ответа",
            f"Без ответа осталось вопросов: {unanswered}.\n"
            "Завершить тест? Изменить ответы после завершения нельзя.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply is QMessageBox.StandardButton.Yes

    # ---------------------------------------------------------------- таймер

    def _on_tick(self) -> None:
        if self._finished:
            return
        self._update_clock()

        left = self.time_left
        if left is not None and left <= 0:
            self._capture_answer()
            self._finish(FinishReason.TIMEOUT)
            return

        per_question = self.bundle.test.settings.time_limit_per_question_sec
        if per_question and self.elapsed - self._question_started >= per_question:
            self._capture_answer()
            self._advance()

    def _update_clock(self) -> None:
        left = self.time_left
        if left is None:
            self.clock.setText(_format_time(self.elapsed))
            return

        self.clock.setText("Осталось " + _format_time(left))
        if left <= WARN_SECONDS and self.clock.property("state") != "warning":
            self.clock.setProperty("state", "warning")
            theme.restyle(self.clock)
        if left <= WARN_SECONDS:
            if not self._warned:
                self._warned = True
                self.statusBar().showMessage(
                    f"До конца теста осталось {int(left // 60) + 1} мин", 10_000
                )

    # ----------------------------------------------------------- автосохранение

    def save_progress(self) -> None:
        if self.progress is None or self._finished:
            return
        self.pending.index = self.index
        self.pending.answers = self.answers
        self.pending.elapsed_sec = int(self.elapsed)
        try:
            self.progress.save(self.pending)
        except OSError:
            # Не смогли записать прогресс — тест это прерывать не должно.
            pass

    # -------------------------------------------------------------- завершение

    def _finish(self, reason: FinishReason) -> None:
        if self._finished:
            return
        self._finished = True
        self.tick_timer.stop()
        self.autosave_timer.stop()

        result = grade_attempt(self.bundle.test, self.plan, self.answers)
        self.storage.save_attempt(
            self.bundle.test,
            self.plan,
            self.answers,
            result,
            employee_name=self.employee_name,
            employee_id=self.employee_id,
            started_at=self.started_at,
            finish_reason=reason,
        )
        if self.progress is not None:
            self.progress.delete(self.pending.id)

        self.result = result
        if reason is not FinishReason.ABORTED and self.show_result_dialog:
            ResultDialog(
                result,
                self.bundle.test.settings.show_result_to_user,
                timed_out=reason is FinishReason.TIMEOUT,
                parent=self,
            ).exec()
        self.close()

    def closeEvent(self, event) -> None:
        if self._finished:
            event.accept()
            return
        reply = QMessageBox.question(
            self,
            "Прервать тестирование",
            "Тест не завершён. Прервать? Попытка будет сохранена как прерванная.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply is QMessageBox.StandardButton.Yes:
            # Молча потерянная попытка — худший вариант: человек тест проходил,
            # а следов не осталось.
            self._capture_answer()
            self._finish(FinishReason.ABORTED)
            event.accept()
        else:
            event.ignore()


class ResultDialog(QDialog):
    def __init__(
        self,
        result: AttemptResult,
        show_details: bool,
        timed_out: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Результат")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        if timed_out:
            note = QLabel("Время вышло — тест завершён автоматически.")
            note.setAlignment(Qt.AlignmentFlag.AlignCenter)
            note.setObjectName("warningNote")
            layout.addWidget(note)

        if show_details:
            colour = "#1b7f3b" if result.passed else "#b00020"
            layout.addWidget(
                _big_label(f"<span style='color:{colour}'>{result.grade_label}</span>")
            )
            details = (
                f"Набрано баллов: {result.score:.2f} из {result.max_score:.2f}<br>"
                f"Результат: <b>{result.percent}%</b>"
            )
            if result.needs_review:
                details += "<br><i>Часть ответов требует проверки преподавателем</i>"
            layout.addWidget(QLabel(details))
        else:
            layout.addWidget(_big_label("Тест завершён"))
            layout.addWidget(QLabel("Результат передан администратору."))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


def _format_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _big_label(html: str) -> QLabel:
    label = QLabel(html)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    font = label.font()
    font.setPointSize(font.pointSize() + 6)
    font.setBold(True)
    label.setFont(font)
    return label
