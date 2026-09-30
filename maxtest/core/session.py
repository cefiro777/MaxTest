"""План попытки: что показываем, в каком порядке, с каким порядком вариантов.

``AttemptPlan`` создаётся один раз при старте попытки и сохраняется вместе с
результатом. Без него экран разбора покажет не то, что видел сотрудник:
вопросы отбираются случайно, варианты перемешиваются, а сам тест могут
отредактировать на следующий день.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .enums import SelectionMode
from .models import Question, Test


@dataclass
class AttemptPlan:
    seed: int
    question_ids: list[str] = field(default_factory=list)
    #: question_id -> порядок option_id на экране
    option_order: dict[str, list[str]] = field(default_factory=dict)
    #: question_id -> порядок правых частей (matching) либо стартовый порядок
    #: пунктов (ordering). Без него правильный ответ виден глазами.
    item_order: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "seed": self.seed,
            "question_ids": list(self.question_ids),
            "option_order": {k: list(v) for k, v in self.option_order.items()},
            "item_order": {k: list(v) for k, v in self.item_order.items()},
        }

    @staticmethod
    def from_dict(data: dict) -> "AttemptPlan":
        return AttemptPlan(
            seed=int(data.get("seed", 0)),
            question_ids=list(data.get("question_ids") or []),
            option_order={
                k: list(v) for k, v in (data.get("option_order") or {}).items()
            },
            item_order={k: list(v) for k, v in (data.get("item_order") or {}).items()},
        )


def build_plan(test: Test, seed: int | None = None) -> AttemptPlan:
    """Отбирает и перемешивает вопросы согласно настройкам теста."""
    if seed is None:
        seed = random.randrange(2**31)
    rnd = random.Random(seed)

    questions = _select_questions(test, rnd)

    if test.settings.shuffle_questions:
        rnd.shuffle(questions)

    plan = AttemptPlan(seed=seed, question_ids=[q.id for q in questions])
    for q in questions:
        if q.options:
            plan.option_order[q.id] = _order_options(q, rnd, test.settings.shuffle_options)
        if q.pairs:
            # Правые части всегда вперемешку: выстроенные напротив своих левых
            # частей, они показывают ответ ещё до первого клика.
            rights = [p.id for p in q.pairs]
            rnd.shuffle(rights)
            plan.item_order[q.id] = rights
        elif q.order:
            items = [i.id for i in q.order]
            rnd.shuffle(items)
            if items == [i.id for i in q.order] and len(items) > 1:
                items.reverse()  # случайно выпал правильный порядок
            plan.item_order[q.id] = items
    return plan


def _select_questions(test: Test, rnd: random.Random) -> list[Question]:
    mode = test.settings.selection_mode

    if mode is SelectionMode.RANDOM:
        limit = test.settings.questions_to_ask
        pool = list(test.questions)
        if limit is None or limit >= len(pool):
            return pool
        # sample сохраняет случайность без повторов; порядок всё равно перемешаем
        return rnd.sample(pool, limit)

    if mode is SelectionMode.BY_SECTION:
        picked: list[Question] = []
        for section in test.sections:
            pool = test.questions_of_section(section.id)
            take = section.take_count
            # Просят больше, чем есть в разделе — берём сколько есть.
            # Падать здесь нельзя: сотрудник уже сидит перед экраном.
            if take is None or take >= len(pool):
                picked.extend(pool)
            else:
                picked.extend(rnd.sample(pool, take))
        # Вопросы вне разделов берём целиком — иначе они молча исчезнут из теста.
        picked.extend(test.questions_of_section(None))
        return picked

    return list(test.questions)


def _order_options(q: Question, rnd: random.Random, shuffle: bool) -> list[str]:
    """Порядок вариантов с закреплением ``no_shuffle``.

    Варианты «Все перечисленное» / «Ничего из перечисленного» обязаны остаться
    на своём месте — перемешанные, они оказываются в середине и теряют смысл.
    """
    ids = [o.id for o in q.options]
    if not shuffle:
        return ids

    movable = [o.id for o in q.options if not o.no_shuffle]
    rnd.shuffle(movable)

    result: list[str] = []
    it = iter(movable)
    for o in q.options:
        result.append(o.id if o.no_shuffle else next(it))
    return result
