"""Тесты плана попытки: выборка вопросов и перемешивание."""

from __future__ import annotations

from maxtest.core.enums import QuestionType, SelectionMode
from maxtest.core.models import Option, Question, Section, Test
from maxtest.core.session import AttemptPlan, build_plan


def make_bank(count: int = 10, section_id: str | None = None) -> list[Question]:
    return [
        Question(
            id=f"q{i}",
            type=QuestionType.SINGLE,
            text=f"Вопрос {i}",
            section_id=section_id,
            options=[Option(id=f"{i}a", correct=True), Option(id=f"{i}b")],
        )
        for i in range(count)
    ]


def test_plan_all_questions_by_default():
    test = Test(questions=make_bank(5))
    test.settings.shuffle_questions = False
    plan = build_plan(test, seed=1)
    assert plan.question_ids == [f"q{i}" for i in range(5)]


def test_random_selection_takes_n():
    test = Test(questions=make_bank(20))
    test.settings.selection_mode = SelectionMode.RANDOM
    test.settings.questions_to_ask = 7
    plan = build_plan(test, seed=42)
    assert len(plan.question_ids) == 7
    assert len(set(plan.question_ids)) == 7  # без повторов


def test_random_selection_more_than_bank_takes_all():
    test = Test(questions=make_bank(3))
    test.settings.selection_mode = SelectionMode.RANDOM
    test.settings.questions_to_ask = 10
    assert len(build_plan(test, seed=1).question_ids) == 3


def test_by_section_selection():
    test = Test(
        sections=[Section(id="s1", take_count=2), Section(id="s2", take_count=3)],
        questions=make_bank(5, "s1") + [
            Question(id=f"x{i}", type=QuestionType.SINGLE, section_id="s2") for i in range(4)
        ],
    )
    test.settings.selection_mode = SelectionMode.BY_SECTION
    plan = build_plan(test, seed=7)
    assert len(plan.question_ids) == 5
    assert sum(1 for q in plan.question_ids if q.startswith("q")) == 2
    assert sum(1 for q in plan.question_ids if q.startswith("x")) == 3


def test_by_section_asks_more_than_available():
    """Просят 10 из раздела, где 3 вопроса — берём три, а не падаем."""
    test = Test(sections=[Section(id="s1", take_count=10)], questions=make_bank(3, "s1"))
    test.settings.selection_mode = SelectionMode.BY_SECTION
    assert len(build_plan(test, seed=1).question_ids) == 3


def test_by_section_keeps_sectionless_questions():
    test = Test(
        sections=[Section(id="s1", take_count=1)],
        questions=make_bank(3, "s1") + [Question(id="free", type=QuestionType.SINGLE)],
    )
    test.settings.selection_mode = SelectionMode.BY_SECTION
    plan = build_plan(test, seed=1)
    assert "free" in plan.question_ids


def test_same_seed_gives_same_plan():
    test = Test(questions=make_bank(20))
    test.settings.selection_mode = SelectionMode.RANDOM
    test.settings.questions_to_ask = 5
    assert build_plan(test, seed=123).to_dict() == build_plan(test, seed=123).to_dict()


def test_different_seeds_give_different_order():
    test = Test(questions=make_bank(20))
    a = build_plan(test, seed=1).question_ids
    b = build_plan(test, seed=2).question_ids
    assert a != b


def test_option_order_contains_all_ids():
    test = Test(questions=make_bank(3))
    plan = build_plan(test, seed=5)
    for q in test.questions:
        assert sorted(plan.option_order[q.id]) == sorted(o.id for o in q.options)


def test_no_shuffle_option_stays_in_place():
    """«Все перечисленное» обязано остаться последним при любом seed."""
    q = Question(
        id="q1",
        type=QuestionType.SINGLE,
        options=[
            Option(id="a"), Option(id="b"), Option(id="c"),
            Option(id="all", no_shuffle=True),
        ],
    )
    test = Test(questions=[q])
    for seed in range(30):
        order = build_plan(test, seed=seed).option_order["q1"]
        assert order[-1] == "all"


def test_shuffle_off_keeps_original_order():
    test = Test(questions=make_bank(3))
    test.settings.shuffle_options = False
    test.settings.shuffle_questions = False
    plan = build_plan(test, seed=9)
    assert plan.option_order["q0"] == ["0a", "0b"]


def test_plan_serialization_round_trip():
    test = Test(questions=make_bank(4))
    plan = build_plan(test, seed=11)
    assert AttemptPlan.from_dict(plan.to_dict()).to_dict() == plan.to_dict()
