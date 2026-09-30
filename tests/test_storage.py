"""Тесты хранилища результатов."""

from __future__ import annotations

import json

import pytest

from maxtest.core.enums import FinishReason, QuestionType
from maxtest.core.grader import grade_attempt
from maxtest.core.models import Option, Question, Test
from maxtest.core.session import build_plan
from maxtest.core.storage import Storage


@pytest.fixture()
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("MAXTEST_DATA_DIR", str(tmp_path))
    with Storage(tmp_path / "results.db") as st:
        yield st


def make_test() -> Test:
    return Test(
        title="Аттестация 2026",
        questions=[
            Question(
                id=f"q{i}",
                type=QuestionType.SINGLE,
                text=f"Вопрос {i}",
                options=[Option(id=f"a{i}", correct=True), Option(id=f"b{i}")],
            )
            for i in range(4)
        ],
    )


def save_one(storage: Storage, name: str, right: int = 4) -> int:
    test = make_test()
    plan = build_plan(test, seed=1)
    answers = {f"q{i}": {"option_id": f"a{i}"} for i in range(right)}
    result = grade_attempt(test, plan, answers)
    return storage.save_attempt(test, plan, answers, result, employee_name=name)


# ------------------------------------------------------------------ схема


def test_schema_created(storage):
    tables = {
        r["name"]
        for r in storage.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"employees", "attempts", "answers", "meta"} <= tables


def test_reopen_existing_db_is_safe(tmp_path):
    path = tmp_path / "results.db"
    with Storage(path) as st:
        save_one(st, "Иванов И.И.")
    with Storage(path) as st:  # повторный запуск не должен ронять схему
        assert len(st.list_attempts()) == 1


# ------------------------------------------------------------- сотрудники


def test_employee_crud(storage):
    eid = storage.add_employee("Петров П.П.", "Электромонтёр", "Цех 1")
    assert [e.full_name for e in storage.list_employees()] == ["Петров П.П."]
    assert storage.find_employee("петров п.п.").id == eid  # регистр не важен

    storage.deactivate_employee(eid)
    assert storage.list_employees() == []
    assert storage.list_employees(active_only=False)[0].id == eid  # история цела


def test_get_or_create_employee_is_idempotent(storage):
    first = storage.get_or_create_employee("Сидоров С.С.")
    assert storage.get_or_create_employee("Сидоров С.С.") == first
    assert len(storage.list_employees()) == 1


def test_employee_name_key_ignores_case_spaces_and_yo(storage):
    """Кириллица: «Пётр» и «петр  ф.ф.» — один человек, а не три записи."""
    first = storage.get_or_create_employee("Пётр Ф.Ф.")
    assert storage.get_or_create_employee("петр  ф.ф. ") == first
    assert storage.get_or_create_employee("ПЁТР Ф.Ф.") == first
    assert len(storage.list_employees()) == 1


# ---------------------------------------------------------------- попытки


def test_save_and_read_attempt(storage):
    attempt_id = save_one(storage, "Иванов И.И.", right=3)

    row = storage.list_attempts()[0]
    assert row["employee_name"] == "Иванов И.И."
    assert row["percent"] == 75
    assert row["test_title"] == "Аттестация 2026"
    assert row["finish_reason"] == FinishReason.COMPLETED.value

    answers = storage.get_answers(attempt_id)
    assert len(answers) == 4
    assert [a["shown_index"] for a in answers] == [1, 2, 3, 4]
    assert sum(a["is_correct"] for a in answers) == 3


def test_raw_answers_are_stored(storage):
    """Сырые ответы нужны для экрана разбора и пересчёта."""
    attempt_id = save_one(storage, "Иванов И.И.", right=1)
    answered = [a for a in storage.get_answers(attempt_id) if a["raw_answer"]]
    assert json.loads(answered[0]["raw_answer"])["option_id"].startswith("a")


def test_plan_is_stored_for_review(storage):
    attempt_id = save_one(storage, "Иванов И.И.")
    row = storage.conn.execute(
        "SELECT plan, seed FROM attempts WHERE id = ?", (attempt_id,)
    ).fetchone()
    plan = json.loads(row["plan"])
    assert len(plan["question_ids"]) == 4
    assert plan["seed"] == row["seed"]


def test_second_attempt_appends_not_overwrites(storage):
    """Следующий сотрудник не должен затирать результат предыдущего."""
    save_one(storage, "Иванов И.И.")
    save_one(storage, "Петров П.П.")
    save_one(storage, "Иванов И.И.", right=2)
    assert len(storage.list_attempts()) == 3


def test_attempt_snapshots_survive_test_edit(storage):
    """Тест отредактировали — старый протокол обязан остаться прежним."""
    test = make_test()
    plan = build_plan(test, seed=1)
    answers = {"q0": {"option_id": "a0"}}
    result = grade_attempt(test, plan, answers)
    attempt_id = storage.save_attempt(test, plan, answers, result, employee_name="Иванов")

    test.title = "Совсем другой тест"
    test.questions[0].text = "Переписанный вопрос"
    test.revision += 1

    row = storage.list_attempts()[0]
    assert row["test_title"] == "Аттестация 2026"
    saved = {a["question_id"]: a["question_text"] for a in storage.get_answers(attempt_id)}
    assert saved["q0"] == "Вопрос 0"


def test_answers_deleted_with_attempt(storage):
    attempt_id = save_one(storage, "Иванов И.И.")
    storage.conn.execute("PRAGMA foreign_keys = ON")
    storage.conn.execute("DELETE FROM attempts WHERE id = ?", (attempt_id,))
    storage.conn.commit()
    assert storage.get_answers(attempt_id) == []


def test_aborted_attempt_is_recorded(storage):
    test = make_test()
    plan = build_plan(test, seed=1)
    result = grade_attempt(test, plan, {})
    storage.save_attempt(
        test, plan, {}, result, employee_name="Иванов",
        finish_reason=FinishReason.ABORTED,
    )
    assert storage.list_attempts()[0]["finish_reason"] == "aborted"


# ------------------------------------------------------------------ бэкап


def test_backup_creates_copy(storage, tmp_path):
    save_one(storage, "Иванов И.И.")
    backup = storage.backup()
    assert backup is not None and backup.exists()

    with Storage(backup) as copy:
        assert len(copy.list_attempts()) == 1


def test_backup_is_daily_not_per_launch(storage):
    first = storage.backup()
    assert storage.backup() == first
    assert len(list(first.parent.glob("results_*.db"))) == 1
