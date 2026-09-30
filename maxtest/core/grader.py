"""Движок оценки.

Чистые функции: ни GUI, ни БД, ни файлов — только модель, план и сырые ответы.
Это единственный модуль, который решает, сдал человек или нет, поэтому он
полностью покрыт тестами.

Формат сырого ответа (то, что уходит в БД как JSON) по типам:

* ``single``   — ``{"option_id": "o_1"}`` либо ``None``, если не ответил
* ``multi``    — ``{"option_ids": ["o_1", "o_4"]}``
* ``text``     — ``{"text": "220 В"}``
* ``matching`` — ``{"pairs": {"p_1": "p_2"}}`` — левая часть → правая часть
* ``ordering`` — ``{"order": ["i_2", "i_1", "i_3"]}``

Ответ всегда хранится по стабильным ``id``, а не по позиции на экране: при
перемешивании вариантов позиции «поедут» и правильный ответ станет неправильным.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .enums import MultiMode, QuestionType, TextMatch
from .models import GradingRules, Question, Test
from .normalize import normalize_text
from .session import AttemptPlan


#: Типы, которые движок умеет оценивать.
SUPPORTED_TYPES = frozenset(QuestionType)


class UnsupportedQuestionType(Exception):
    """Тип вопроса ещё не поддерживается движком (см. фазу 4 плана)."""


@dataclass
class QuestionResult:
    question_id: str
    score: float
    max_score: float
    #: ``None`` = ждёт ручной проверки преподавателем
    is_correct: bool | None
    needs_manual: bool = False


@dataclass
class AttemptResult:
    score: float = 0.0
    max_score: float = 0.0
    percent: int = 0
    grade_label: str = ""
    passed: bool = False
    needs_review: bool = False
    per_question: list[QuestionResult] = field(default_factory=list)
    #: section_id -> (набрано, максимум); ключ ``None`` — вопросы вне разделов
    by_section: dict[str | None, tuple[float, float]] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Отдельный вопрос
# --------------------------------------------------------------------------


def grade_question(q: Question, raw: dict | None, rules: GradingRules) -> QuestionResult:
    max_score = float(q.weight)
    needs_manual = False

    if q.type is QuestionType.SINGLE:
        score, correct = _grade_single(q, raw)
    elif q.type is QuestionType.MULTI:
        score, correct = _grade_multi(q, raw, rules)
    elif q.type is QuestionType.TEXT:
        score, correct = _grade_text(q, raw)
        # Балл начисляется предварительно; проверяющий может его изменить.
        # У вопроса может быть своё решение — оно важнее настройки теста.
        needs_manual = q.needs_manual_review(rules.text_manual_review)
    elif q.type is QuestionType.MATCHING:
        score, correct = _grade_matching(q, raw)
    elif q.type is QuestionType.ORDERING:
        score, correct = _grade_ordering(q, raw)
    else:
        raise UnsupportedQuestionType(f"Неизвестный тип вопроса: '{q.type}'")

    return QuestionResult(
        question_id=q.id,
        score=score * max_score,
        max_score=max_score,
        is_correct=None if needs_manual else correct,
        needs_manual=needs_manual,
    )


def _grade_single(q: Question, raw: dict | None) -> tuple[float, bool]:
    """Возвращает долю от веса (0.0 или 1.0) и признак правильности."""
    chosen = (raw or {}).get("option_id")
    if not chosen:
        return 0.0, False
    return (1.0, True) if chosen in q.correct_option_ids() else (0.0, False)


def _grade_multi(q: Question, raw: dict | None, rules: GradingRules) -> tuple[float, bool]:
    correct_ids = q.correct_option_ids()
    chosen = set((raw or {}).get("option_ids") or [])
    # Отбрасываем id, которых уже нет в вопросе (тест отредактировали).
    chosen &= {o.id for o in q.options}

    if not correct_ids:
        # Вопрос без правильных ответов — ошибка автора, а не сотрудника.
        return 0.0, False

    fully_correct = chosen == correct_ids

    if rules.multi_mode is MultiMode.ALL_OR_NOTHING:
        return (1.0 if fully_correct else 0.0), fully_correct

    hits = len(chosen & correct_ids)
    misses = len(chosen - correct_ids)
    wrong_total = len(q.options) - len(correct_ids)

    share = hits / len(correct_ids)
    if rules.partial_penalty and wrong_total > 0:
        share -= misses / wrong_total
    # Стратегия «отметить всё» даёт ровно ноль, а не половину балла.
    share = max(0.0, share)

    return share, fully_correct


def _grade_text(q: Question, raw: dict | None) -> tuple[float, bool]:
    given = ((raw or {}).get("text") or "").strip()
    if not given or q.answer_text is None or not q.answer_text.accepted:
        return 0.0, False

    mode = q.answer_text.match
    accepted = q.answer_text.accepted

    if mode is TextMatch.EXACT:
        hit = given in accepted
    elif mode is TextMatch.CONTAINS:
        norm = normalize_text(given)
        hit = any(normalize_text(a) in norm for a in accepted if a.strip())
    else:  # NORMALIZED
        norm = normalize_text(given)
        hit = any(normalize_text(a) == norm for a in accepted)

    return (1.0, True) if hit else (0.0, False)


def _grade_matching(q: Question, raw: dict | None) -> tuple[float, bool]:
    """Балл за каждую верно составленную пару."""
    pairs = q.pairs or []
    if not pairs:
        return 0.0, False

    mapping = (raw or {}).get("pairs") or {}
    hits = sum(1 for p in pairs if mapping.get(p.id) == p.id)
    share = hits / len(pairs)
    return share, hits == len(pairs)


def _grade_ordering(q: Question, raw: dict | None) -> tuple[float, bool]:
    """Доля правильно упорядоченных соседних пар.

    Мягче, чем «всё или ничего»: перепутанные местами два соседних пункта не
    обнуляют весь ответ, а стоят ровно одну пару.
    """
    items = q.order or []
    correct_ids = [i.id for i in items]
    if len(correct_ids) < 2:
        return 0.0, False

    given = [i for i in ((raw or {}).get("order") or []) if i in set(correct_ids)]
    if sorted(given) != sorted(correct_ids):
        return 0.0, False  # ответ неполный — считать нечего

    position = {item_id: index for index, item_id in enumerate(given)}
    total = len(correct_ids) - 1
    hits = sum(
        1
        for a, b in zip(correct_ids, correct_ids[1:])
        if position[a] < position[b]
    )
    return hits / total, given == correct_ids


# --------------------------------------------------------------------------
# Попытка целиком
# --------------------------------------------------------------------------


def grade_attempt(
    test: Test,
    plan: AttemptPlan,
    answers: dict[str, dict | None],
) -> AttemptResult:
    """Считает итог по вопросам, которые реально были показаны."""
    rules = test.grading
    result = AttemptResult()
    sections: dict[str | None, list[float]] = {}

    for qid in plan.question_ids:
        q = test.question_by_id(qid)
        if q is None:
            continue  # вопрос удалён из теста после начала попытки
        qr = grade_question(q, answers.get(qid), rules)
        result.per_question.append(qr)

        result.score += qr.score
        result.max_score += qr.max_score
        if qr.needs_manual:
            result.needs_review = True

        bucket = sections.setdefault(q.section_id, [0.0, 0.0])
        bucket[0] += qr.score
        bucket[1] += qr.max_score

    result.by_section = {k: (v[0], v[1]) for k, v in sections.items()}
    result.percent = to_percent(result.score, result.max_score)

    threshold = rules.scale.grade(result.percent)
    result.grade_label = threshold.label
    result.passed = threshold.passed
    return result


def to_percent(score: float, max_score: float) -> int:
    """Целый процент. Тест целиком из вопросов с весом 0 не должен ронять программу."""
    if max_score <= 0:
        return 0
    # floor(x + 0.5) вместо round(): round() в Python банковское,
    # round(2.5) == 2, и на границе шкалы это промах на балл.
    return int(math.floor(score / max_score * 100 + 0.5))
