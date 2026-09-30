"""Тесты движка оценки (single/multi, шкала, границы)."""

from __future__ import annotations

import pytest

from maxtest.core.enums import MultiMode, QuestionType
from maxtest.core.grader import (
    SUPPORTED_TYPES,
    UnsupportedQuestionType,
    grade_attempt,
    grade_question,
    to_percent,
)
from maxtest.core.models import (
    GradingRules,
    Option,
    Question,
    Scale,
    Section,
    Test,
)
from maxtest.core.session import AttemptPlan


def single_q(weight: float = 1.0) -> Question:
    return Question(
        id="q1",
        type=QuestionType.SINGLE,
        text="Вопрос",
        weight=weight,
        options=[
            Option(id="a", text="Верно", correct=True),
            Option(id="b", text="Неверно"),
            Option(id="c", text="Тоже неверно"),
        ],
    )


def multi_q(weight: float = 1.0) -> Question:
    return Question(
        id="q2",
        type=QuestionType.MULTI,
        text="Вопрос",
        weight=weight,
        options=[
            Option(id="a", text="Верно 1", correct=True),
            Option(id="b", text="Верно 2", correct=True),
            Option(id="c", text="Неверно 1"),
            Option(id="d", text="Неверно 2"),
        ],
    )


# ------------------------------------------------------------------- single


def test_single_correct():
    r = grade_question(single_q(), {"option_id": "a"}, GradingRules())
    assert (r.score, r.max_score, r.is_correct) == (1.0, 1.0, True)


def test_single_wrong():
    r = grade_question(single_q(), {"option_id": "b"}, GradingRules())
    assert r.score == 0.0 and r.is_correct is False


def test_single_no_answer():
    for raw in (None, {}, {"option_id": None}):
        r = grade_question(single_q(), raw, GradingRules())
        assert r.score == 0.0 and r.is_correct is False


def test_single_respects_weight():
    r = grade_question(single_q(weight=2.5), {"option_id": "a"}, GradingRules())
    assert r.score == 2.5 and r.max_score == 2.5


def test_single_zero_weight_not_in_denominator():
    q = single_q(weight=0.0)
    r = grade_question(q, {"option_id": "a"}, GradingRules())
    assert r.score == 0.0 and r.max_score == 0.0


# -------------------------------------------------------------------- multi


def test_multi_all_or_nothing():
    rules = GradingRules(multi_mode=MultiMode.ALL_OR_NOTHING)
    assert grade_question(multi_q(), {"option_ids": ["a", "b"]}, rules).score == 1.0
    assert grade_question(multi_q(), {"option_ids": ["a"]}, rules).score == 0.0
    assert grade_question(multi_q(), {"option_ids": ["a", "b", "c"]}, rules).score == 0.0


def test_multi_partial_half():
    rules = GradingRules(multi_mode=MultiMode.PARTIAL)
    r = grade_question(multi_q(), {"option_ids": ["a"]}, rules)
    assert r.score == pytest.approx(0.5)
    assert r.is_correct is False  # частичный балл ≠ правильный ответ


def test_multi_partial_penalty_for_extra():
    rules = GradingRules(multi_mode=MultiMode.PARTIAL, partial_penalty=True)
    # 2 из 2 верных, но 1 лишний из 2 неверных: 1.0 - 0.5 = 0.5
    r = grade_question(multi_q(), {"option_ids": ["a", "b", "c"]}, rules)
    assert r.score == pytest.approx(0.5)


def test_multi_select_all_scores_zero():
    """Стратегия «отметить всё» должна давать ровно ноль, а не половину."""
    rules = GradingRules(multi_mode=MultiMode.PARTIAL, partial_penalty=True)
    r = grade_question(multi_q(), {"option_ids": ["a", "b", "c", "d"]}, rules)
    assert r.score == 0.0


def test_multi_partial_without_penalty():
    rules = GradingRules(multi_mode=MultiMode.PARTIAL, partial_penalty=False)
    r = grade_question(multi_q(), {"option_ids": ["a", "b", "c", "d"]}, rules)
    assert r.score == pytest.approx(1.0)


def test_multi_empty_answer():
    r = grade_question(multi_q(), {"option_ids": []}, GradingRules())
    assert r.score == 0.0


def test_multi_ignores_stale_option_ids():
    """Тест отредактировали — id из старой попытки не должны ломать подсчёт."""
    r = grade_question(multi_q(), {"option_ids": ["a", "b", "zzz"]}, GradingRules())
    assert r.score == pytest.approx(1.0)


def test_multi_without_correct_options_scores_zero():
    q = multi_q()
    for o in q.options:
        o.correct = False
    assert grade_question(q, {"option_ids": ["a"]}, GradingRules()).score == 0.0


def test_all_question_types_are_gradable():
    assert SUPPORTED_TYPES == set(QuestionType)


def test_unknown_type_raises():
    q = Question(type=QuestionType.SINGLE, text="?")
    q.type = "essay"  # тип из будущей версии файла
    with pytest.raises(UnsupportedQuestionType):
        grade_question(q, None, GradingRules())


# ------------------------------------------------------------------ percent


def test_to_percent_rounds_half_up():
    # round() в Python банковское: round(2.5) == 2. Проверяем, что не оно.
    assert to_percent(2.5, 100) == 3
    assert to_percent(7, 10) == 70
    assert to_percent(2, 3) == 67


def test_to_percent_zero_max_does_not_crash():
    assert to_percent(0, 0) == 0


# ------------------------------------------------------------------ попытка


def build_test() -> Test:
    test = Test(title="Аттестация", sections=[Section(id="s1", title="ОТ")])
    q1 = single_q()
    q1.section_id = "s1"
    q2 = multi_q()
    q2.section_id = "s1"
    q3 = single_q()
    q3.id = "q3"
    test.questions = [q1, q2, q3]
    test.grading.scale = Scale.default_pass_fail(70)
    return test


def test_grade_attempt_totals():
    test = build_test()
    plan = AttemptPlan(seed=1, question_ids=["q1", "q2", "q3"])
    result = grade_attempt(test, plan, {"q1": {"option_id": "a"}, "q2": {"option_ids": ["a", "b"]}})

    assert result.max_score == 3.0
    assert result.score == pytest.approx(2.0)
    assert result.percent == 67
    assert result.passed is False


def test_max_score_counts_only_shown_questions():
    """Выборка 2 из 3: максимум — 2 балла, иначе все получат заниженный процент."""
    test = build_test()
    plan = AttemptPlan(seed=1, question_ids=["q1", "q3"])
    result = grade_attempt(test, plan, {"q1": {"option_id": "a"}, "q3": {"option_id": "a"}})

    assert result.max_score == 2.0
    assert result.percent == 100
    assert result.passed is True


def test_grade_attempt_skips_deleted_question():
    test = build_test()
    plan = AttemptPlan(seed=1, question_ids=["q1", "q_deleted"])
    result = grade_attempt(test, plan, {"q1": {"option_id": "a"}})
    assert result.max_score == 1.0 and result.percent == 100


def test_by_section_totals():
    test = build_test()
    plan = AttemptPlan(seed=1, question_ids=["q1", "q2", "q3"])
    result = grade_attempt(test, plan, {"q1": {"option_id": "a"}})

    assert result.by_section["s1"] == (pytest.approx(1.0), 2.0)
    assert result.by_section[None] == (0.0, 1.0)


def test_scale_boundary_69_70_71():
    """Границы шкалы на реальном подсчёте, а не на голом Scale.grade()."""
    test = Test()
    test.grading.scale = Scale.default_pass_fail(70)
    test.questions = [
        Question(id=f"q{i}", type=QuestionType.SINGLE, text="?",
                 options=[Option(id=f"a{i}", correct=True), Option(id=f"b{i}")])
        for i in range(10)
    ]
    plan = AttemptPlan(seed=1, question_ids=[f"q{i}" for i in range(10)])

    for right, expected_passed in ((6, False), (7, True), (8, True)):
        answers = {f"q{i}": {"option_id": f"a{i}"} for i in range(right)}
        result = grade_attempt(test, plan, answers)
        assert result.percent == right * 10
        assert result.passed is expected_passed
