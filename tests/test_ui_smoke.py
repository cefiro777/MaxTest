"""Сквозной прогон вертикального среза без единого клика мышью.

Тест гоняет реальные виджеты в режиме ``offscreen``: создать тест в
конструкторе → пройти его в проигрывателе → получить балл → увидеть попытку
в базе. Это дешёвая страховка от того, что окно перестанет открываться после
рефакторинга ядра.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import QDate, QEvent, Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from maxtest.core.bundle import Bundle  # noqa: E402
from maxtest.core.enums import FinishReason, QuestionType, SelectionMode  # noqa: E402
from maxtest.core.models import Option, Question  # noqa: E402
from maxtest.core.progress import PendingAttempt, ProgressStore  # noqa: E402
from maxtest.core.session import build_plan  # noqa: E402
from maxtest.core.storage import Storage  # noqa: E402
from maxtest.report.excel import export_attempts  # noqa: E402
from maxtest.ui.editor.editor_window import EditorWindow, PreviewDialog  # noqa: E402
from maxtest.ui.editor.test_settings import TestSettingsDialog  # noqa: E402
from maxtest.ui.player.player_window import PlayerWindow  # noqa: E402
from maxtest.ui.widgets.question_view import QuestionView  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MAXTEST_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture(autouse=True)
def no_modal_dialogs(monkeypatch):
    """Модальные окна без пользователя вешают прогон навсегда."""
    from PyQt6.QtWidgets import QMessageBox

    for name in ("warning", "critical", "information"):
        monkeypatch.setattr(
            QMessageBox, name,
            staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok),
        )
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )


def make_bundle() -> Bundle:
    bundle = Bundle.new("Смоук-тест")
    bundle.test.settings.shuffle_questions = False
    bundle.test.questions = [
        Question(
            id=f"q{i}",
            type=QuestionType.SINGLE,
            text=f"Вопрос {i}",
            options=[Option(id=f"a{i}", text="Верно", correct=True), Option(id=f"b{i}", text="Неверно")],
        )
        for i in range(4)
    ]
    return bundle


# ------------------------------------------------------------- QuestionView


def test_question_view_returns_answer_by_id(qapp):
    q = make_bundle().test.questions[0]
    view = QuestionView()
    view.set_question(q, option_order=["b0", "a0"])  # намеренно перемешанный порядок

    view._buttons["a0"].setChecked(True)
    assert view.answer() == {"option_id": "a0"}  # id, а не позиция на экране


def test_question_view_multi_answer(qapp):
    q = Question(
        type=QuestionType.MULTI,
        text="?",
        options=[Option(id="x", correct=True), Option(id="y", correct=True), Option(id="z")],
    )
    view = QuestionView()
    view.set_question(q)
    view._buttons["x"].setChecked(True)
    view._buttons["z"].setChecked(True)
    assert set(view.answer()["option_ids"]) == {"x", "z"}


def test_question_view_no_answer_is_none(qapp):
    view = QuestionView()
    view.set_question(make_bundle().test.questions[0])
    assert view.answer() is None


# ------------------------------------------------------------------ конструктор


def options_editor(editor: EditorWindow):
    return editor.editors[editor.current_question.type]


def test_editor_creates_and_saves_test(qapp, data_dir, tmp_path):
    editor = EditorWindow()
    editor.add_question()
    editor.question_text.setPlainText("Сколько будет 2 + 2?")
    rows = options_editor(editor).rows
    rows[0].text.setText("4")
    rows[0].correct.setChecked(True)
    rows[1].text.setText("5")

    path = tmp_path / "created.qtest"
    assert editor._save_to(path) is True

    loaded = Bundle.load(path)
    q = loaded.test.questions[0]
    assert q.text == "Сколько будет 2 + 2?"
    assert [o.text for o in q.options] == ["4", "5"]
    assert q.correct_option_ids() == {q.options[0].id}


def test_editor_single_keeps_one_correct_option(qapp, data_dir):
    """Радиокнопки вне QButtonGroup сами друг друга не снимают."""
    editor = EditorWindow()
    editor.add_question()
    rows = options_editor(editor).rows
    rows[0].correct.setChecked(True)
    rows[1].correct.setChecked(True)
    assert len(editor.current_question.correct_option_ids()) == 1


def test_editor_type_switch_keeps_options(qapp, data_dir):
    """Переключение типа туда-обратно не должно терять набранное."""
    editor = EditorWindow()
    editor.add_question()
    options_editor(editor).rows[0].text.setText("Вариант А")

    editor.type_combo.setCurrentIndex(editor.type_combo.findData(QuestionType.MATCHING))
    assert editor.current_question.type is QuestionType.MATCHING
    assert len(editor.current_question.pairs) >= 2  # заготовка пар создана

    editor.type_combo.setCurrentIndex(editor.type_combo.findData(QuestionType.SINGLE))
    assert editor.current_question.options[0].text == "Вариант А"


def test_editor_duplicate_makes_new_ids(qapp, data_dir):
    """Копия с теми же id привязала бы оценку к чужим вариантам."""
    editor = EditorWindow()
    editor.add_question()
    editor.question_text.setPlainText("Оригинал")
    editor.duplicate_question()

    first, second = editor.bundle.test.questions
    assert second.text == "Оригинал"
    assert first.id != second.id
    assert {o.id for o in first.options}.isdisjoint({o.id for o in second.options})


def test_editor_all_question_types_round_trip(qapp, data_dir, tmp_path):
    editor = EditorWindow()
    for question_type in (
        QuestionType.SINGLE, QuestionType.MULTI, QuestionType.TEXT,
        QuestionType.MATCHING, QuestionType.ORDERING,
    ):
        editor.add_question()
        editor.type_combo.setCurrentIndex(editor.type_combo.findData(question_type))
        editor.question_text.setPlainText(f"Вопрос типа {question_type}")

    path = tmp_path / "all_types.qtest"
    assert editor._save_to(path) is True
    loaded = Bundle.load(path)
    assert [q.type for q in loaded.test.questions] == [
        QuestionType.SINGLE, QuestionType.MULTI, QuestionType.TEXT,
        QuestionType.MATCHING, QuestionType.ORDERING,
    ]


def test_editor_image_insert_resizes_and_saves(qapp, data_dir, tmp_path):
    Image = pytest.importorskip("PIL.Image")
    src = tmp_path / "photo.png"
    Image.new("RGB", (2400, 1600), "green").save(src)

    editor = EditorWindow()
    editor.add_question()
    editor.current_question.image = editor.bundle.add_image(src)
    editor._update_thumb(editor.current_question)

    path = tmp_path / "with_image.qtest"
    editor._save_to(path)

    loaded = Bundle.load(path)
    blob = loaded.get_image_bytes(loaded.test.questions[0].image)
    assert blob and len(blob) < src.stat().st_size
    assert loaded.missing_media == []


def test_editor_prunes_orphan_images_on_save(qapp, data_dir, tmp_path):
    Image = pytest.importorskip("PIL.Image")
    src = tmp_path / "p.png"
    Image.new("RGB", (100, 100), "blue").save(src)

    editor = EditorWindow()
    editor.add_question()
    editor.current_question.image = editor.bundle.add_image(src)
    editor.clear_image()
    editor._save_to(tmp_path / "clean.qtest")

    assert Bundle.load(tmp_path / "clean.qtest").media == {}


def test_editor_switching_questions_does_not_leak_values(qapp, data_dir):
    """Классика Qt: заполнение формы пишет значения в ПРЕДЫДУЩИЙ вопрос."""
    editor = EditorWindow()
    editor.add_question()
    editor.question_text.setPlainText("Первый")
    editor.add_question()
    editor.question_text.setPlainText("Второй")

    editor.question_list.setCurrentRow(0)
    editor.question_list.setCurrentRow(1)
    editor.question_list.setCurrentRow(0)

    assert [q.text for q in editor.bundle.test.questions] == ["Первый", "Второй"]


def test_editor_dirty_flag(qapp, data_dir, tmp_path):
    editor = EditorWindow()
    assert editor._dirty is False
    editor.add_question()
    assert editor._dirty is True
    editor._save_to(tmp_path / "d.qtest")
    assert editor._dirty is False


def test_editor_problems_panel(qapp, data_dir):
    editor = EditorWindow()
    editor.add_question()  # пустой текст, нет правильного ответа
    texts = [
        editor.problems_list.item(i).text() for i in range(editor.problems_list.count())
    ]
    assert any("не отмечен ни один правильный ответ" in t for t in texts)
    assert any("не задан текст вопроса" in t for t in texts)


def test_problem_click_jumps_to_question(qapp, data_dir):
    editor = EditorWindow()
    editor.add_question()
    editor.question_text.setPlainText("Нормальный вопрос")
    editor.add_question()  # второй — сломанный

    editor.question_list.setCurrentRow(0)
    broken = next(
        editor.problems_list.item(i)
        for i in range(editor.problems_list.count())
        if editor.problems_list.item(i).data(Qt.ItemDataRole.UserRole) == 2
    )
    editor._on_problem_activated(broken)
    assert editor.question_list.currentRow() == 1


def test_preview_dialog_builds(qapp, data_dir):
    editor = EditorWindow()
    editor.add_question()
    editor.type_combo.setCurrentIndex(editor.type_combo.findData(QuestionType.ORDERING))
    dialog = PreviewDialog(editor.bundle, editor.current_question)
    assert dialog is not None  # рендерер не падает ни на одном типе


def test_settings_dialog_applies(qapp, data_dir):
    editor = EditorWindow()
    editor.add_question()
    dialog = TestSettingsDialog(editor.bundle.test)
    dialog.shuffle_questions.setChecked(False)
    dialog.time_limit.setValue(30)
    dialog._add_section_row()
    dialog._on_accept()

    settings = editor.bundle.test.settings
    assert settings.shuffle_questions is False
    assert settings.time_limit_sec == 1800
    assert len(editor.bundle.test.sections) == 1


def test_settings_dialog_rejects_scale_without_zero(qapp, data_dir):
    editor = EditorWindow()
    dialog = TestSettingsDialog(editor.bundle.test)
    dialog.thresholds.setRowCount(0)
    dialog._add_threshold_row()
    dialog.thresholds.item(0, 0).setText("50")
    assert dialog._collect_thresholds() is None  # порога от 0 % нет


def test_deleting_section_keeps_questions(qapp, data_dir):
    editor = EditorWindow()
    editor.add_question()
    test = editor.bundle.test

    dialog = TestSettingsDialog(test)
    dialog._add_section_row()
    dialog._on_accept()
    test.questions[0].section_id = test.sections[0].id

    dialog = TestSettingsDialog(test)
    dialog.sections.setCurrentCell(0, 0)
    dialog._remove_section_row()
    dialog._on_accept()

    assert test.sections == []
    assert len(test.questions) == 1
    assert test.questions[0].section_id is None


# ---------------------------------------------------------------- проигрыватель


def test_full_attempt_end_to_end(qapp, data_dir, tmp_path):
    bundle = make_bundle()
    plan = build_plan(bundle.test, seed=1)

    with Storage(tmp_path / "results.db") as storage:
        player = PlayerWindow(bundle, plan, storage, "Иванов И.И.", show_result_dialog=False)

        # Отвечаем верно на 3 вопроса из 4, на последний — неверно.
        for index in range(len(plan.question_ids)):
            qid = plan.question_ids[index]
            correct = index < 3
            option_id = f"a{qid[1:]}" if correct else f"b{qid[1:]}"
            player.view._buttons[option_id].setChecked(True)
            player._on_next()

        assert player._finished is True

        attempt = storage.list_attempts()[0]
        assert attempt["employee_name"] == "Иванов И.И."
        assert attempt["percent"] == 75
        assert attempt["finish_reason"] == "completed"
        assert len(storage.get_answers(attempt["id"])) == 4


def answer_correctly(view, question) -> None:
    """Отвечает верно на вопрос любого типа через настоящие виджеты."""
    if question.type is QuestionType.SINGLE:
        view._buttons[next(iter(question.correct_option_ids()))].setChecked(True)
    elif question.type is QuestionType.MULTI:
        for option_id in question.correct_option_ids():
            view._buttons[option_id].setChecked(True)
    elif question.type is QuestionType.TEXT:
        view._text_area.setPlainText(question.answer_text.accepted[0])
    elif question.type is QuestionType.MATCHING:
        for pair in question.pairs:
            combo = view._match_boxes[pair.id]
            combo.setCurrentIndex(combo.findData(pair.id))
    elif question.type is QuestionType.ORDERING:
        widget = view._order_list
        for target, item in enumerate(question.order):
            for row in range(widget.count()):
                if widget.item(row).data(Qt.ItemDataRole.UserRole) == item.id:
                    widget.insertItem(target, widget.takeItem(row))
                    break


def test_all_types_played_end_to_end(qapp, data_dir, tmp_path):
    """Все пять типов проходятся и оцениваются на 100 %."""
    from tools.make_demo import build as build_demo

    bundle = build_demo()
    bundle.test.settings.selection_mode = SelectionMode.ALL
    plan = build_plan(bundle.test, seed=3)

    with Storage(tmp_path / "results.db") as storage:
        player = PlayerWindow(bundle, plan, storage, "Демо Д.Д.", show_result_dialog=False)
        for qid in plan.question_ids:
            answer_correctly(player.view, bundle.test.question_by_id(qid))
            player._on_next()

        attempt = storage.list_attempts()[0]
        assert attempt["percent"] == 100
        assert attempt["passed"] == 1


def test_ordering_answer_is_shuffled_at_start(qapp, data_dir):
    """Стартовый порядок не должен совпадать с правильным — иначе ответ виден."""
    from tools.make_demo import build as build_demo

    bundle = build_demo()
    question = next(q for q in bundle.test.questions if q.type is QuestionType.ORDERING)
    for seed in range(20):
        plan = build_plan(bundle.test, seed=seed)
        assert plan.item_order[question.id] != [i.id for i in question.order]


def test_timer_finishes_attempt_on_timeout(qapp, data_dir, tmp_path):
    """Время вышло — попытка сдаётся автоматически с тем, что успели ответить."""
    bundle = make_bundle()
    bundle.test.settings.time_limit_sec = 60
    plan = build_plan(bundle.test, seed=1)

    with Storage(tmp_path / "results.db") as storage:
        player = PlayerWindow(bundle, plan, storage, "Иванов", show_result_dialog=False)
        answer_correctly(player.view, bundle.test.question_by_id(plan.question_ids[0]))

        # Отматываем секундомер на минуту назад — системные часы не трогаем.
        player._started_monotonic -= 61
        player._on_tick()

        assert player._finished is True
        attempt = storage.list_attempts()[0]
        assert attempt["finish_reason"] == "timeout"
        assert attempt["percent"] == 25  # ответ на первый вопрос засчитан


def test_timer_uses_monotonic_not_wall_clock(qapp, data_dir, tmp_path, monkeypatch):
    """Перевод системных часов не должен ни продлевать, ни обрывать тест."""
    import datetime as dt

    bundle = make_bundle()
    bundle.test.settings.time_limit_sec = 600
    plan = build_plan(bundle.test, seed=1)

    with Storage(tmp_path / "results.db") as storage:
        player = PlayerWindow(bundle, plan, storage, "Иванов", show_result_dialog=False)

        class FutureDate(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return dt.datetime(2030, 1, 1)

        monkeypatch.setattr(dt, "datetime", FutureDate)
        player._on_tick()
        assert player._finished is False


def test_per_question_time_limit_advances(qapp, data_dir, tmp_path):
    bundle = make_bundle()
    bundle.test.settings.time_limit_per_question_sec = 30
    plan = build_plan(bundle.test, seed=1)

    with Storage(tmp_path / "results.db") as storage:
        player = PlayerWindow(bundle, plan, storage, "Иванов", show_result_dialog=False)
        assert player.index == 0
        player._question_started -= 31
        player._on_tick()
        assert player.index == 1


def test_back_navigation_keeps_answers(qapp, data_dir, tmp_path):
    bundle = make_bundle()
    bundle.test.settings.allow_back = True
    plan = build_plan(bundle.test, seed=1)

    with Storage(tmp_path / "results.db") as storage:
        player = PlayerWindow(bundle, plan, storage, "Иванов", show_result_dialog=False)
        first_qid = plan.question_ids[0]
        answer_correctly(player.view, bundle.test.question_by_id(first_qid))
        player._on_next()

        player._on_back()
        assert player.index == 0
        # Ответ восстановлен в виджете, а не потерян.
        assert player.view.answer() == player.answers[first_qid]

        # Меняем ответ на неверный и снова идём вперёд.
        wrong = f"b{first_qid[1:]}"
        player.view._buttons[wrong].setChecked(True)
        player._on_next()
        assert player.answers[first_qid] == {"option_id": wrong}


def test_back_button_hidden_when_disallowed(qapp, data_dir, tmp_path):
    bundle = make_bundle()  # allow_back по умолчанию False
    plan = build_plan(bundle.test, seed=1)
    with Storage(tmp_path / "results.db") as storage:
        player = PlayerWindow(bundle, plan, storage, "Иванов", show_result_dialog=False)
        assert player.back_button.isVisible() is False


def test_progress_saved_and_cleared(qapp, data_dir, tmp_path):
    bundle = make_bundle()
    bundle.path = tmp_path / "saved.qtest"
    bundle.save(bundle.path)
    plan = build_plan(bundle.test, seed=1)
    store = ProgressStore(tmp_path / "progress")

    with Storage(tmp_path / "results.db") as storage:
        player = PlayerWindow(
            bundle, plan, storage, "Иванов", show_result_dialog=False, progress=store
        )
        answer_correctly(player.view, bundle.test.question_by_id(plan.question_ids[0]))
        player._on_next()

        pending = store.list_pending()
        assert len(pending) == 1
        assert pending[0].index == 1
        assert pending[0].answered_count == 1

        for _ in range(len(plan.question_ids) - 1):
            answer_correctly(
                player.view, bundle.test.question_by_id(plan.question_ids[player.index])
            )
            player._on_next()

        # Тест завершён — файл прогресса не должен остаться висеть.
        assert store.list_pending() == []


def test_resume_restores_answers_and_time(qapp, data_dir, tmp_path):
    bundle = make_bundle()
    plan = build_plan(bundle.test, seed=1)
    store = ProgressStore(tmp_path / "progress")

    with Storage(tmp_path / "results.db") as storage:
        first = PlayerWindow(
            bundle, plan, storage, "Иванов", show_result_dialog=False, progress=store
        )
        answer_correctly(first.view, bundle.test.question_by_id(plan.question_ids[0]))
        first._on_next()
        first._elapsed_base = 120
        first.save_progress()

        pending = store.list_pending()[0]
        second = PlayerWindow(
            bundle, plan, storage, "Иванов",
            show_result_dialog=False, progress=store, resume=pending,
        )

        assert second.index == 1
        assert second.answers == first.answers
        assert second.elapsed >= 120  # секундомер продолжился, а не начался заново
        assert second.pending.id == pending.id  # тот же файл, а не второй


def test_app_window_recovers_pending_attempt(qapp, data_dir, tmp_path):
    """После вылета программа предлагает продолжить с того же места."""
    from maxtest.ui.app_window import AppWindow

    bundle = make_bundle()
    path = tmp_path / "recover.qtest"
    bundle.save(path, bump_revision=False)
    plan = build_plan(bundle.test, seed=1)
    store = ProgressStore(tmp_path / "progress")

    with Storage(tmp_path / "results.db") as storage:
        crashed = PlayerWindow(
            Bundle.load(path), plan, storage, "Иванов",
            show_result_dialog=False, progress=store,
        )
        answer_correctly(crashed.view, bundle.test.question_by_id(plan.question_ids[0]))
        crashed._on_next()
        # Программа «упала»: файл прогресса остался, попытка в БД не записана.
        assert storage.list_attempts() == []

        app = AppWindow(storage, progress=store)
        app.check_pending_attempts()  # QMessageBox.question замокан на «Да»

        resumed = app._windows[-1]
        assert isinstance(resumed, PlayerWindow)
        assert resumed.index == 1
        assert resumed.answers == crashed.answers


def test_recovery_drops_pending_when_test_file_gone(qapp, data_dir, tmp_path):
    from maxtest.ui.app_window import AppWindow

    store = ProgressStore(tmp_path / "progress")
    pending = PendingAttempt(
        test_path=str(tmp_path / "нет-такого.qtest"),
        test_id="t_1",
        test_title="Пропавший тест",
        employee_name="Иванов",
        plan={"seed": 1, "question_ids": ["q0"]},
    )
    store.save(pending)

    with Storage(tmp_path / "results.db") as storage:
        app = AppWindow(storage, progress=store)
        app.check_pending_attempts()

    assert store.list_pending() == []  # висящая запись не остаётся навсегда


def test_review_dialog_accepts_answer(qapp, data_dir, tmp_path):
    """Проверяющий засчитывает текстовый ответ — попытка уходит из очереди."""
    from maxtest.ui.app_window import AppWindow
    from maxtest.ui.reports.review_dialog import ReviewDialog

    from .test_review import make_test, save_attempt

    with Storage(tmp_path / "results.db") as storage:
        save_attempt(storage)
        app = AppWindow(storage, progress=ProgressStore(tmp_path / "progress"))
        assert "(1)" in app.review_button.text()

        dialog = ReviewDialog(storage)
        assert dialog.attempts.count() == 1
        assert dialog.table.rowCount() == 1  # только текстовый ответ

        dialog.table.setCurrentCell(0, 0)
        dialog.review(accepted=True)

        assert dialog.attempts.count() == 0
        assert storage.count_attempts_to_review() == 0
        assert storage.list_attempts()[0]["percent"] == 67

        app.refresh_review_button()
        assert app.review_button.isEnabled() is False


def test_results_window_filters_and_export(qapp, data_dir, tmp_path):
    from maxtest.ui.reports.results_window import ResultsWindow

    from .test_reports import save_attempt

    with Storage(tmp_path / "results.db") as storage:
        save_attempt(storage, "Иванов И.И.", right=4, started_at="2026-03-10T09:00:00")
        save_attempt(storage, "Петров П.П.", right=1, started_at="2026-03-11T09:00:00")

        window = ResultsWindow(storage)
        window.date_from.setDate(QDate(2026, 1, 1))
        window.date_to.setDate(QDate(2026, 12, 31))
        window.reload()
        assert window.table.rowCount() == 2
        assert "средний результат" in window.summary.text()

        window.only_failed.setChecked(True)
        assert window.table.rowCount() == 1
        assert window.table.item(0, 0).text() == "Петров П.П."

        window.only_failed.setChecked(False)
        path = export_attempts(storage, window.rows, tmp_path / "отчёт.xlsx")
        assert path.exists()


def test_attempt_dialog_shows_review(qapp, data_dir, tmp_path):
    from maxtest.ui.reports.attempt_dialog import AttemptDialog

    from .test_reports import save_attempt

    with Storage(tmp_path / "results.db") as storage:
        attempt_id = save_attempt(storage, "Иванов И.И.", right=2)
        dialog = AttemptDialog(storage, attempt_id)

        assert dialog.table.rowCount() == 4
        verdicts = [dialog.table.item(row, 6).text() for row in range(4)]
        assert verdicts.count("верно") == 2
        assert verdicts.count("неверно") == 2

        dialog.table.setCurrentCell(0, 0)
        assert "Пояснение" in dialog.explanation.text()


def test_closing_app_after_attempt_does_not_touch_closed_db(qapp, data_dir, tmp_path):
    """Регрессия: при закрытии главного окна вылетала sqlite3.ProgrammingError.

    Qt уничтожает дочерние окна уже после выхода из app.exec(), когда база
    закрыта, и обработчик обновления счётчика падал на закрытом соединении.
    """
    from maxtest.ui.app_window import AppWindow

    bundle = make_bundle()
    plan = build_plan(bundle.test, seed=1)
    storage = Storage(tmp_path / "results.db")
    app = AppWindow(storage, progress=ProgressStore(tmp_path / "progress"))

    player = PlayerWindow(
        bundle, plan, storage, "Иванов", show_result_dialog=False, progress=app.progress
    )
    app._windows.append(player)
    for _ in plan.question_ids:
        answer_correctly(player.view, bundle.test.question_by_id(plan.question_ids[player.index]))
        player._on_next()

    # Порядок как при выходе из программы.
    app.shutdown()
    storage.close()

    assert storage.is_open is False
    app.refresh_review_button()  # не должно бросать исключение
    player.deleteLater()
    qapp.processEvents()  # здесь Qt и уничтожает окна


def test_review_counter_updates_on_window_activation(qapp, data_dir, tmp_path):
    from maxtest.ui.app_window import AppWindow

    from .test_review import save_attempt

    with Storage(tmp_path / "results.db") as storage:
        app = AppWindow(storage, progress=ProgressStore(tmp_path / "progress"))
        assert "(" not in app.review_button.text()

        save_attempt(storage)  # попытка с текстовым ответом на проверку
        app.event(QEvent(QEvent.Type.WindowActivate))
        assert "(1)" in app.review_button.text()


def test_storage_close_is_idempotent(tmp_path):
    storage = Storage(tmp_path / "results.db")
    storage.close()
    storage.close()  # повторное закрытие не должно падать
    assert storage.is_open is False


def test_employees_dialog_add_edit_hide(qapp, data_dir, tmp_path):
    from maxtest.ui.employees_dialog import EmployeesDialog

    with Storage(tmp_path / "results.db") as storage:
        storage.add_employee("Иванов И.И.", "Электромонтёр", "Цех 1")
        dialog = EmployeesDialog(storage)
        assert dialog.table.rowCount() == 1

        employee_id = storage.list_employees()[0].id
        storage.update_employee(employee_id, "Иванов Иван Иванович", "Мастер", "Цех 2")
        dialog.reload()
        assert dialog.table.item(0, 1).text() == "Мастер"

        storage.set_employee_active(employee_id, False)
        dialog.reload()
        assert dialog.table.rowCount() == 0  # скрытые не показываются

        dialog.show_hidden.setChecked(True)
        assert dialog.table.rowCount() == 1
        assert "(скрыт)" in dialog.table.item(0, 0).text()


def test_aborted_attempt_is_saved(qapp, data_dir, tmp_path):
    bundle = make_bundle()
    plan = build_plan(bundle.test, seed=1)

    with Storage(tmp_path / "results.db") as storage:
        player = PlayerWindow(bundle, plan, storage, "Петров П.П.", show_result_dialog=False)
        player.view._buttons[f"a{plan.question_ids[0][1:]}"].setChecked(True)
        player._on_next()
        player._finish(FinishReason.ABORTED)  # как при закрытии окна крестиком

        attempt = storage.list_attempts()[0]
        assert attempt["finish_reason"] == "aborted"
        assert attempt["percent"] == 25  # один верный из четырёх показанных
