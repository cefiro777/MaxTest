"""Ручная проверка текстовых ответов и пересчёт итога."""

from __future__ import annotations

import sqlite3

import pytest

from maxtest.core.enums import QuestionType, TextMatch
from maxtest.core.grader import grade_attempt
from maxtest.core.models import (
    MatchPair,
    Option,
    OrderItem,
    Question,
    Scale,
    Section,
    Test,
    TextAnswer,
)
from maxtest.core.presenter import describe_correct, describe_given
from maxtest.core.session import build_plan
from maxtest.core.storage import Storage


@pytest.fixture()
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("MAXTEST_DATA_DIR", str(tmp_path))
    with Storage(tmp_path / "results.db") as st:
        yield st


def make_test() -> Test:
    """Три вопроса: два обычных и один текстовый на ручную проверку."""
    test = Test(title="Аттестация", sections=[Section(id="s1", title="Охрана труда")])
    test.grading.text_manual_review = True
    test.grading.scale = Scale.default_pass_fail(70)
    test.settings.shuffle_questions = False
    test.questions = [
        Question(
            id="q1", type=QuestionType.SINGLE, text="Вопрос 1", section_id="s1",
            options=[Option(id="a1", text="Верно", correct=True), Option(id="b1", text="Неверно")],
        ),
        Question(
            id="q2", type=QuestionType.SINGLE, text="Вопрос 2",
            options=[Option(id="a2", text="Верно", correct=True), Option(id="b2", text="Неверно")],
        ),
        Question(
            id="q3", type=QuestionType.TEXT, text="Своими словами опишите порядок допуска",
            answer_text=TextAnswer(accepted=["наряд-допуск"], match=TextMatch.CONTAINS),
        ),
    ]
    return test


def save_attempt(storage: Storage, text_answer: str = "что-то своё") -> int:
    test = make_test()
    plan = build_plan(test, seed=1)
    answers = {
        "q1": {"option_id": "a1"},
        "q2": {"option_id": "b2"},
        "q3": {"text": text_answer},
    }
    result = grade_attempt(test, plan, answers)
    return storage.save_attempt(test, plan, answers, result, employee_name="Иванов И.И.")


# --------------------------------------------------------------- очередь проверки


def test_attempt_lands_in_review_queue(storage):
    save_attempt(storage)
    assert storage.count_attempts_to_review() == 1
    assert len(storage.list_attempts_to_review()) == 1


def test_text_answer_waits_for_verdict(storage):
    attempt_id = save_attempt(storage)
    answers = {a["question_id"]: a for a in storage.get_answers(attempt_id)}
    assert answers["q3"]["is_correct"] is None
    assert answers["q1"]["is_correct"] == 1
    assert answers["q2"]["is_correct"] == 0


# ------------------------------------------------------------------- пересчёт


def test_accepting_answer_recalculates_everything(storage):
    attempt_id = save_attempt(storage)  # ответ не совпал с эталоном → 1 из 3
    before = storage.get_attempt(attempt_id)
    assert before["percent"] == 33

    q3 = next(a for a in storage.get_answers(attempt_id) if a["question_id"] == "q3")
    storage.review_answer(q3["id"], accepted=True)

    after = storage.get_attempt(attempt_id)
    assert after["score"] == pytest.approx(2.0)
    assert after["percent"] == 67
    assert after["grade_label"] == "Не сдал"  # порог 70 %
    assert after["passed"] == 0
    assert after["needs_review"] == 0  # очередь очистилась


def test_rejecting_answer_keeps_score(storage):
    attempt_id = save_attempt(storage)
    q3 = next(a for a in storage.get_answers(attempt_id) if a["question_id"] == "q3")
    storage.review_answer(q3["id"], accepted=False)

    after = storage.get_attempt(attempt_id)
    assert after["score"] == pytest.approx(1.0)
    assert after["percent"] == 33
    assert after["passed"] == 0
    assert after["needs_review"] == 0


def test_review_flips_grade_and_passed_together(storage):
    """Балл, процент, оценка и «сдал» обновляются одной транзакцией."""
    test = make_test()
    test.grading.scale = Scale.default_pass_fail(60)
    plan = build_plan(test, seed=1)
    answers = {
        "q1": {"option_id": "a1"},
        "q2": {"option_id": "a2"},
        "q3": {"text": "наряд-допуск оформляется заранее"},
    }
    result = grade_attempt(test, plan, answers)
    attempt_id = storage.save_attempt(test, plan, answers, result, employee_name="Петров")

    q3 = next(a for a in storage.get_answers(attempt_id) if a["question_id"] == "q3")
    storage.review_answer(q3["id"], accepted=False)

    after = storage.get_attempt(attempt_id)
    assert after["percent"] == 67
    assert after["passed"] == 1
    assert after["grade_label"] == "Сдал"

    storage.review_answer(q3["id"], accepted=True)
    after = storage.get_attempt(attempt_id)
    assert after["percent"] == 100 and after["passed"] == 1


def test_manual_override_flag_is_set(storage):
    attempt_id = save_attempt(storage)
    q3 = next(a for a in storage.get_answers(attempt_id) if a["question_id"] == "q3")
    storage.review_answer(q3["id"], accepted=True)
    updated = next(a for a in storage.get_answers(attempt_id) if a["question_id"] == "q3")
    assert updated["manual_override"] == 1


def test_review_unknown_answer_raises(storage):
    with pytest.raises(KeyError):
        storage.review_answer(99999, accepted=True)


def test_scale_snapshot_survives_test_change(storage):
    """Пересчёт не должен зависеть от файла теста — он мог измениться."""
    test = make_test()
    plan = build_plan(test, seed=1)
    answers = {"q1": {"option_id": "a1"}, "q2": {"option_id": "a2"}, "q3": {"text": "наряд-допуск"}}
    result = grade_attempt(test, plan, answers)
    attempt_id = storage.save_attempt(test, plan, answers, result, employee_name="Сидоров")

    # Автор переписал шкалу в файле теста — на прошлый протокол это не влияет.
    test.grading.scale = Scale.default_five_point()

    q3 = next(a for a in storage.get_answers(attempt_id) if a["question_id"] == "q3")
    after = storage.recalculate_attempt(storage.review_answer(q3["id"], accepted=True))
    assert after["grade_label"] in ("Сдал", "Не сдал")  # шкала прежняя, pass/fail


def test_old_db_without_scale_column_is_migrated(tmp_path, monkeypatch):
    """База прежней версии не должна падать при открытии."""
    monkeypatch.setenv("MAXTEST_DATA_DIR", str(tmp_path))
    path = tmp_path / "old.db"

    legacy = sqlite3.connect(str(path))
    legacy.executescript(
        """
        CREATE TABLE attempts (id INTEGER PRIMARY KEY, employee_name TEXT,
            test_id TEXT, test_title TEXT, test_revision INTEGER,
            started_at TEXT, needs_review INTEGER DEFAULT 0);
        CREATE TABLE answers (id INTEGER PRIMARY KEY, attempt_id INTEGER,
            question_id TEXT, question_text TEXT, shown_index INTEGER);
        """
    )
    legacy.close()

    with Storage(path) as storage:
        columns = {r["name"] for r in storage.conn.execute("PRAGMA table_info(attempts)")}
        assert "scale" in columns
        columns = {r["name"] for r in storage.conn.execute("PRAGMA table_info(answers)")}
        assert {"question_type", "section_title", "correct_answer"} <= columns


# ------------------------------------------------------------------ снимки


def test_answer_snapshot_columns_filled(storage):
    attempt_id = save_attempt(storage)
    answers = {a["question_id"]: a for a in storage.get_answers(attempt_id)}
    assert answers["q1"]["section_title"] == "Охрана труда"
    assert answers["q1"]["question_type"] == "single"
    assert answers["q1"]["correct_answer"] == "Верно"
    assert answers["q3"]["correct_answer"] == "наряд-допуск"


# --------------------------------------------------------------- описания


def test_describe_correct_all_types():
    q_single = make_test().questions[0]
    assert describe_correct(q_single) == "Верно"

    q_multi = Question(
        type=QuestionType.MULTI,
        options=[Option(text="A", correct=True), Option(text="B", correct=True), Option(text="C")],
    )
    assert describe_correct(q_multi) == "A; B"

    q_match = Question(
        type=QuestionType.MATCHING,
        pairs=[MatchPair(left="Ампер", right="Ток"), MatchPair(left="Вольт", right="Напряжение")],
    )
    assert describe_correct(q_match) == "Ампер → Ток; Вольт → Напряжение"

    q_order = Question(
        type=QuestionType.ORDERING,
        order=[OrderItem(text="Раз"), OrderItem(text="Два")],
    )
    assert describe_correct(q_order) == "Раз → Два"


def test_describe_given_uses_ids_not_positions():
    q = Question(
        type=QuestionType.SINGLE,
        options=[Option(id="x", text="Первый"), Option(id="y", text="Второй")],
    )
    assert describe_given(q, {"option_id": "y"}) == "Второй"
    assert describe_given(q, None) == "— нет ответа —"
    assert describe_given(q, {"option_id": "удалённый"}) == "— нет ответа —"


def test_describe_given_matching_and_ordering():
    q_match = Question(
        type=QuestionType.MATCHING,
        pairs=[
            MatchPair(id="p1", left="Ампер", right="Ток"),
            MatchPair(id="p2", left="Вольт", right="Напряжение"),
        ],
    )
    assert describe_given(q_match, {"pairs": {"p1": "p2"}}) == "Ампер → Напряжение"

    q_order = Question(
        type=QuestionType.ORDERING,
        order=[OrderItem(id="i1", text="Раз"), OrderItem(id="i2", text="Два")],
    )
    assert describe_given(q_order, {"order": ["i2", "i1"]}) == "Два → Раз"
