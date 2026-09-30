"""Выбор теста и сотрудника: списки вместо ручного ввода."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from maxtest.core.bundle import Bundle, peek  # noqa: E402
from maxtest.core.enums import QuestionType  # noqa: E402
from maxtest.core.models import Option, Question, Test  # noqa: E402
from maxtest.core.recent import RecentTests  # noqa: E402
from maxtest.core.storage import Storage  # noqa: E402
from maxtest.ui.player.start_dialog import StartDialog  # noqa: E402
from maxtest.ui.player.test_picker import TestPickerDialog  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MAXTEST_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture(autouse=True)
def no_modal_dialogs(monkeypatch):
    for name in ("warning", "critical", "information"):
        monkeypatch.setattr(
            QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
        )


def make_test_file(path, title="Аттестация", questions=3) -> Bundle:
    bundle = Bundle.new(title)
    bundle.test.questions = [
        Question(
            type=QuestionType.SINGLE,
            text=f"Вопрос {i}",
            options=[Option(text="Да", correct=True), Option(text="Нет")],
        )
        for i in range(questions)
    ]
    bundle.save(path, bump_revision=False)
    return bundle


# ------------------------------------------------------------------ peek


def test_peek_reads_manifest_only(tmp_path):
    make_test_file(tmp_path / "t.qtest", "Охрана труда", questions=7)
    info = peek(tmp_path / "t.qtest")

    assert info is not None
    assert info.title == "Охрана труда"
    assert info.question_count == 7
    assert info.name == "t.qtest"


def test_peek_returns_none_for_alien_file(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("просто текст", encoding="utf-8")
    assert peek(path) is None
    assert peek(tmp_path / "нет-файла.qtest") is None


# ------------------------------------------------------------- недавние


def test_recent_keeps_order_without_duplicates(tmp_path, data_dir):
    first = tmp_path / "a.qtest"
    second = tmp_path / "b.qtest"
    make_test_file(first)
    make_test_file(second)

    recent = RecentTests()
    recent.add(first)
    recent.add(second)
    recent.add(first)  # повтор поднимает файл наверх, а не дублирует

    entries = recent.list()
    assert len(entries) == 2
    assert entries[0].name == "a.qtest"


def test_recent_skips_deleted_files(tmp_path, data_dir):
    path = tmp_path / "gone.qtest"
    make_test_file(path)
    recent = RecentTests()
    recent.add(path)
    path.unlink()

    assert recent.list() == []


def test_recent_survives_broken_file(data_dir):
    recent = RecentTests()
    recent.path.write_text("{сломано", encoding="utf-8")
    assert recent.list() == []


# ----------------------------------------------------------- выбор теста


def test_picker_lists_tests_from_folder(qapp, data_dir, tmp_path):
    from maxtest.core.paths import tests_dir

    make_test_file(tests_dir() / "ot.qtest", "Охрана труда", questions=5)
    make_test_file(tests_dir() / "eq.qtest", "Оборудование", questions=2)

    dialog = TestPickerDialog(RecentTests())
    assert dialog.table.rowCount() == 2
    titles = {dialog.table.item(row, 0).text() for row in range(2)}
    assert titles == {"Охрана труда", "Оборудование"}
    assert dialog.start_button.isEnabled() is True


def test_picker_includes_recent_from_other_folders(qapp, data_dir, tmp_path):
    outside = tmp_path / "флешка"
    outside.mkdir()
    make_test_file(outside / "внешний.qtest", "Тест с флешки")

    recent = RecentTests()
    recent.add(outside / "внешний.qtest")

    dialog = TestPickerDialog(recent)
    assert dialog.table.item(0, 0).text() == "Тест с флешки"


def test_picker_ignores_broken_files(qapp, data_dir):
    from maxtest.core.paths import tests_dir

    make_test_file(tests_dir() / "good.qtest", "Нормальный")
    (tests_dir() / "broken.qtest").write_bytes("не архив".encode("utf-8"))

    dialog = TestPickerDialog(RecentTests())
    assert dialog.table.rowCount() == 1


def test_picker_with_no_tests_disables_start(qapp, data_dir):
    dialog = TestPickerDialog(RecentTests())
    assert dialog.table.rowCount() == 0
    assert dialog.start_button.isEnabled() is False
    assert "не найдено" in dialog.hint.text()


def test_picker_selection_and_recent_update(qapp, data_dir):
    from maxtest.core.paths import tests_dir

    make_test_file(tests_dir() / "t.qtest", "Аттестация")
    recent = RecentTests()

    dialog = TestPickerDialog(recent)
    dialog.table.selectRow(0)
    dialog._on_accept()

    assert dialog.selected_path.name == "t.qtest"
    assert [p.name for p in recent.list()] == ["t.qtest"]


# ------------------------------------------------------- выбор сотрудника


def simple_test() -> Test:
    test = Test(title="Аттестация")
    test.questions = [Question(type=QuestionType.SINGLE, text="?")]
    return test


def test_start_dialog_lists_employees(qapp, data_dir, tmp_path):
    with Storage(tmp_path / "r.db") as storage:
        storage.add_employee("Иванов Иван Иванович", "Электромонтёр", "Цех 1")
        storage.add_employee("Петрова Анна Сергеевна")

        dialog = StartDialog(simple_test(), storage, 10)
        assert dialog.employees.count() == 2

        dialog.employees.setCurrentRow(0)
        assert dialog.start_button.isEnabled() is True
        assert "Иванов Иван Иванович" in dialog.status.text()


def test_start_dialog_search_filters(qapp, data_dir, tmp_path):
    with Storage(tmp_path / "r.db") as storage:
        storage.add_employee("Иванов Иван Иванович")
        storage.add_employee("Петрова Анна Сергеевна")

        dialog = StartDialog(simple_test(), storage, 10)
        dialog.search.setText("петр")

        hidden = [dialog.employees.item(i).isHidden() for i in range(2)]
        assert hidden.count(False) == 1
        visible = next(
            dialog.employees.item(i)
            for i in range(2)
            if not dialog.employees.item(i).isHidden()
        )
        assert "Петрова" in visible.text()


def test_start_dialog_search_ignores_yo(qapp, data_dir, tmp_path):
    with Storage(tmp_path / "r.db") as storage:
        storage.add_employee("Пётр Фёдорович")
        dialog = StartDialog(simple_test(), storage, 10)
        dialog.search.setText("петр")
        assert dialog.employees.item(0).isHidden() is False


def test_start_dialog_selecting_existing_employee(qapp, data_dir, tmp_path):
    with Storage(tmp_path / "r.db") as storage:
        employee_id = storage.add_employee("Иванов Иван Иванович")

        dialog = StartDialog(simple_test(), storage, 10)
        dialog.employees.setCurrentRow(0)
        dialog._on_accept()

        assert dialog.employee_name == "Иванов Иван Иванович"
        assert dialog.employee_id == employee_id
        assert len(storage.list_employees()) == 1  # дубля не завели


def test_start_dialog_new_employee(qapp, data_dir, tmp_path):
    with Storage(tmp_path / "r.db") as storage:
        dialog = StartDialog(simple_test(), storage, 10)
        assert dialog.employees.count() == 0
        assert "пуст" in dialog.status.text()

        dialog.new_name.setText("Сидоров Сидор")
        assert "Будет добавлен новый сотрудник" in dialog.status.text()
        dialog._on_accept()

        assert [e.full_name for e in storage.list_employees()] == ["Сидоров Сидор"]


def test_start_dialog_warns_about_existing_name(qapp, data_dir, tmp_path):
    """Ввод существующего имени не должен плодить второго «того же» человека."""
    with Storage(tmp_path / "r.db") as storage:
        employee_id = storage.add_employee("Иванов Иван Иванович")

        dialog = StartDialog(simple_test(), storage, 10)
        dialog.new_name.setText("иванов иван иванович")
        assert "уже есть в списке" in dialog.status.text()

        dialog._on_accept()
        assert dialog.employee_id == employee_id
        assert len(storage.list_employees()) == 1


def test_start_dialog_typing_clears_selection(qapp, data_dir, tmp_path):
    with Storage(tmp_path / "r.db") as storage:
        storage.add_employee("Иванов Иван Иванович")

        dialog = StartDialog(simple_test(), storage, 10)
        dialog.employees.setCurrentRow(0)
        dialog.new_name.setText("Новый Сотрудник")

        assert dialog.employees.selectedItems() == []
        assert dialog._current_name() == "Новый Сотрудник"


def test_start_dialog_requires_a_choice(qapp, data_dir, tmp_path):
    with Storage(tmp_path / "r.db") as storage:
        storage.add_employee("Иванов Иван Иванович")
        dialog = StartDialog(simple_test(), storage, 10)

        dialog.employees.clearSelection()
        assert dialog.start_button.isEnabled() is False
