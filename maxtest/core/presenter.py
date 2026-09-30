"""Человекочитаемое описание ответов — для разбора ошибок и отчётов.

Живёт в ядре, а не в интерфейсе: те же строки нужны и на экране проверки, и в
Excel-отчёте, и в снимке ответа, который сохраняется в базу.
"""

from __future__ import annotations

from .enums import QuestionType
from .models import Question

EMPTY = "— нет ответа —"


def describe_correct(q: Question) -> str:
    """Правильный ответ вопроса одной строкой."""
    if q.type in (QuestionType.SINGLE, QuestionType.MULTI):
        texts = [o.text for o in q.options if o.correct]
        return "; ".join(texts) if texts else "—"

    if q.type is QuestionType.TEXT:
        accepted = q.answer_text.accepted if q.answer_text else []
        return " / ".join(accepted) if accepted else "—"

    if q.type is QuestionType.MATCHING:
        return "; ".join(f"{p.left} → {p.right}" for p in (q.pairs or [])) or "—"

    if q.type is QuestionType.ORDERING:
        return " → ".join(i.text for i in (q.order or [])) or "—"

    return "—"


def describe_given(q: Question, raw: dict | None) -> str:
    """Ответ сотрудника одной строкой."""
    if not raw:
        return EMPTY

    if q.type is QuestionType.SINGLE:
        option = q.option_by_id(raw.get("option_id", ""))
        return option.text if option else EMPTY

    if q.type is QuestionType.MULTI:
        chosen = [q.option_by_id(oid) for oid in raw.get("option_ids") or []]
        texts = [o.text for o in chosen if o is not None]
        return "; ".join(texts) if texts else EMPTY

    if q.type is QuestionType.TEXT:
        return raw.get("text") or EMPTY

    if q.type is QuestionType.MATCHING:
        by_id = {p.id: p for p in (q.pairs or [])}
        parts = []
        for pair_id, chosen_id in (raw.get("pairs") or {}).items():
            left = by_id.get(pair_id)
            right = by_id.get(chosen_id)
            if left is not None:
                parts.append(f"{left.left} → {right.right if right else '—'}")
        return "; ".join(parts) if parts else EMPTY

    if q.type is QuestionType.ORDERING:
        by_id = {i.id: i for i in (q.order or [])}
        texts = [by_id[i].text for i in raw.get("order") or [] if i in by_id]
        return " → ".join(texts) if texts else EMPTY

    return EMPTY
