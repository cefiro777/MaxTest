"""Оценка вопросов с вводом текста, соответствием и упорядочиванием."""

from __future__ import annotations

import pytest

from maxtest.core.enums import QuestionType, TextMatch
from maxtest.core.grader import grade_question
from maxtest.core.models import GradingRules, MatchPair, OrderItem, Question, TextAnswer
from maxtest.core.normalize import normalize_text


def text_q(accepted: list[str], match: TextMatch = TextMatch.NORMALIZED) -> Question:
    return Question(
        type=QuestionType.TEXT,
        text="Напряжение бытовой сети?",
        answer_text=TextAnswer(accepted=accepted, match=match),
    )


def matching_q() -> Question:
    return Question(
        type=QuestionType.MATCHING,
        text="Сопоставьте",
        pairs=[
            MatchPair(id="p1", left="Амперметр", right="Ток"),
            MatchPair(id="p2", left="Вольтметр", right="Напряжение"),
            MatchPair(id="p3", left="Мегаомметр", right="Сопротивление"),
        ],
    )


def ordering_q() -> Question:
    return Question(
        type=QuestionType.ORDERING,
        text="Расставьте по порядку",
        order=[
            OrderItem(id="i1", text="Отключение"),
            OrderItem(id="i2", text="Плакаты"),
            OrderItem(id="i3", text="Проверка напряжения"),
            OrderItem(id="i4", text="Заземление"),
        ],
    )


# --------------------------------------------------------------- нормализация


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("  220 В  ", "220 в"),
        ("Ёлка", "елка"),
        ("два   пробела", "два пробела"),
        ("3,5", "3.5"),
        ("Ответ.", "ответ"),
    ],
)
def test_normalize_text(raw, expected):
    assert normalize_text(raw) == expected


# ------------------------------------------------------------------ ввод текста


def test_text_normalized_match():
    q = text_q(["220 В"])
    rules = GradingRules()
    for given in ("220 В", "220 в", "  220   в ", "220 в."):
        assert grade_question(q, {"text": given}, rules).score == 1.0


def test_text_yo_and_decimal_comma():
    assert grade_question(text_q(["ёмкость"]), {"text": "Емкость"}, GradingRules()).score == 1.0
    assert grade_question(text_q(["3.5"]), {"text": "3,5"}, GradingRules()).score == 1.0


def test_text_wrong_and_empty():
    q = text_q(["220"])
    rules = GradingRules()
    assert grade_question(q, {"text": "380"}, rules).score == 0.0
    assert grade_question(q, {"text": "   "}, rules).score == 0.0
    assert grade_question(q, None, rules).score == 0.0


def test_text_exact_match_is_strict():
    q = text_q(["220 В"], TextMatch.EXACT)
    rules = GradingRules()
    assert grade_question(q, {"text": "220 В"}, rules).score == 1.0
    assert grade_question(q, {"text": "220 в"}, rules).score == 0.0


def test_text_contains_match():
    q = text_q(["обесточить"], TextMatch.CONTAINS)
    r = grade_question(q, {"text": "Нужно обесточить участок сети"}, GradingRules())
    assert r.score == 1.0


def test_text_several_accepted_variants():
    q = text_q(["220", "220 В", "220 вольт"])
    rules = GradingRules()
    for given in ("220", "220 в", "220 ВОЛЬТ"):
        assert grade_question(q, {"text": given}, rules).score == 1.0


def test_text_manual_review_flag():
    q = text_q(["220"])
    rules = GradingRules(text_manual_review=True)
    r = grade_question(q, {"text": "220"}, rules)
    assert r.needs_manual is True
    assert r.is_correct is None       # решение за проверяющим
    assert r.score == 1.0             # балл предварительный


def test_text_without_reference_answers_scores_zero():
    q = Question(type=QuestionType.TEXT, text="?", answer_text=TextAnswer())
    assert grade_question(q, {"text": "что угодно"}, GradingRules()).score == 0.0


# ------------------------------------------------------------------ соответствие


def test_matching_all_correct():
    r = grade_question(
        matching_q(), {"pairs": {"p1": "p1", "p2": "p2", "p3": "p3"}}, GradingRules()
    )
    assert r.score == 1.0 and r.is_correct is True


def test_matching_partial():
    r = grade_question(
        matching_q(), {"pairs": {"p1": "p1", "p2": "p3", "p3": "p2"}}, GradingRules()
    )
    assert r.score == pytest.approx(1 / 3)
    assert r.is_correct is False


def test_matching_empty_answer():
    assert grade_question(matching_q(), None, GradingRules()).score == 0.0


def test_matching_partially_filled():
    r = grade_question(matching_q(), {"pairs": {"p1": "p1"}}, GradingRules())
    assert r.score == pytest.approx(1 / 3)


# --------------------------------------------------------------- упорядочивание


def test_ordering_correct():
    r = grade_question(
        ordering_q(), {"order": ["i1", "i2", "i3", "i4"]}, GradingRules()
    )
    assert r.score == 1.0 and r.is_correct is True


def test_ordering_one_swap_costs_one_pair():
    """Переставленные соседи не должны обнулять весь ответ."""
    r = grade_question(
        ordering_q(), {"order": ["i2", "i1", "i3", "i4"]}, GradingRules()
    )
    assert r.score == pytest.approx(2 / 3)
    assert r.is_correct is False


def test_ordering_fully_reversed():
    r = grade_question(
        ordering_q(), {"order": ["i4", "i3", "i2", "i1"]}, GradingRules()
    )
    assert r.score == 0.0


def test_ordering_incomplete_answer_scores_zero():
    r = grade_question(ordering_q(), {"order": ["i1", "i2"]}, GradingRules())
    assert r.score == 0.0


def test_ordering_empty_answer():
    assert grade_question(ordering_q(), None, GradingRules()).score == 0.0


def test_ordering_ignores_stale_ids():
    r = grade_question(
        ordering_q(), {"order": ["i1", "i2", "i3", "i4", "zzz"]}, GradingRules()
    )
    assert r.score == 1.0
