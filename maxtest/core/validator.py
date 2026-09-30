"""Проверка теста на готовность к запуску.

Валидация предупреждающая, а не запрещающая: редактор, который не даёт
сохранить полузаполненный вопрос, дерётся с пользователем на полпути. Задача —
показать список проблем, чтобы автор не узнал о сломанном вопросе в тот момент,
когда сотрудник уже сидит перед экраном.
"""

from __future__ import annotations

from dataclasses import dataclass

from .enums import QuestionType, SelectionMode
from .models import Question, Test

ERROR = "error"      # тест нельзя нормально пройти или оценить
WARNING = "warning"  # пройти можно, но автор скорее всего ошибся


@dataclass
class Problem:
    text: str
    level: str = ERROR
    question_id: str | None = None
    question_index: int | None = None  # 1-based, для перехода из панели

    @property
    def is_error(self) -> bool:
        return self.level == ERROR


def validate(test: Test, known_media: set[str] | None = None) -> list[Problem]:
    problems: list[Problem] = []

    if not test.title.strip():
        problems.append(Problem("У теста нет названия", WARNING))

    if not test.questions:
        problems.append(Problem("В тесте нет ни одного вопроса"))
        return problems

    for index, q in enumerate(test.questions, start=1):
        problems.extend(_validate_question(q, index, known_media))

    problems.extend(_validate_selection(test))
    problems.extend(_validate_scale(test))
    return problems


def _validate_question(
    q: Question, index: int, known_media: set[str] | None
) -> list[Problem]:
    out: list[Problem] = []

    def add(text: str, level: str = ERROR) -> None:
        out.append(Problem(f"Вопрос {index}: {text}", level, q.id, index))

    if not q.text.strip():
        add("не задан текст вопроса")
    if q.weight < 0:
        add("отрицательный вес")
    elif q.weight == 0:
        add("вес 0 — вопрос не влияет на оценку", WARNING)

    if known_media is not None and q.image and q.image not in known_media:
        add("картинка потеряна")

    if q.type in (QuestionType.SINGLE, QuestionType.MULTI):
        filled = [o for o in q.options if o.text.strip()]
        if len(q.options) < 2:
            add("меньше двух вариантов ответа")
        if len(filled) != len(q.options):
            add("есть пустые варианты ответа")

        correct = q.correct_option_ids()
        if not correct:
            add("не отмечен ни один правильный ответ")
        elif q.type is QuestionType.SINGLE and len(correct) > 1:
            add("тип «один ответ», а правильных отмечено несколько")
        elif q.type is QuestionType.MULTI and len(correct) == len(q.options):
            add("правильны все варианты — вопрос ничего не проверяет", WARNING)

    elif q.type is QuestionType.TEXT:
        accepted = [a for a in (q.answer_text.accepted if q.answer_text else []) if a.strip()]
        if not accepted:
            add("не задан ни один правильный ответ")

    elif q.type is QuestionType.MATCHING:
        pairs = q.pairs or []
        if len(pairs) < 2:
            add("меньше двух пар соответствия")
        if any(not p.left.strip() or not p.right.strip() for p in pairs):
            add("есть пары с пустой половиной")
        rights = [p.right.strip() for p in pairs if p.right.strip()]
        if len(set(rights)) != len(rights):
            add("одинаковые правые части — соответствие неоднозначно", WARNING)

    elif q.type is QuestionType.ORDERING:
        items = q.order or []
        if len(items) < 2:
            add("меньше двух пунктов для упорядочивания")
        if any(not i.text.strip() for i in items):
            add("есть пустые пункты")

    return out


def _validate_selection(test: Test) -> list[Problem]:
    """Выборка не должна просить больше вопросов, чем есть в банке."""
    out: list[Problem] = []
    settings = test.settings

    if settings.selection_mode is SelectionMode.RANDOM:
        asked = settings.questions_to_ask
        if asked is not None and asked > len(test.questions):
            out.append(
                Problem(
                    f"Отбор случайных вопросов: запрошено {asked}, "
                    f"а в тесте {len(test.questions)} — будут показаны все",
                    WARNING,
                )
            )
        if asked is not None and asked <= 0:
            out.append(Problem("Отбор случайных вопросов: запрошено 0 вопросов"))

    elif settings.selection_mode is SelectionMode.BY_SECTION:
        if not test.sections:
            out.append(Problem("Выбран отбор по разделам, но разделов нет"))
        for section in test.sections:
            available = len(test.questions_of_section(section.id))
            if available == 0:
                out.append(
                    Problem(f"Раздел «{section.title}»: нет вопросов", WARNING)
                )
            elif section.take_count is not None and section.take_count > available:
                out.append(
                    Problem(
                        f"Раздел «{section.title}»: запрошено {section.take_count}, "
                        f"доступно {available} — будут показаны все",
                        WARNING,
                    )
                )

    return out


def _validate_scale(test: Test) -> list[Problem]:
    out: list[Problem] = []
    thresholds = test.grading.scale.thresholds

    if not thresholds:
        out.append(Problem("Не задана шкала оценивания"))
        return out
    if not any(t.min_percent == 0 for t in thresholds):
        out.append(
            Problem("В шкале нет порога от 0 % — низкий балл не получит оценку")
        )
    if any(t.min_percent < 0 or t.min_percent > 100 for t in thresholds):
        out.append(Problem("В шкале есть порог вне диапазона 0–100 %"))
    if len({t.min_percent for t in thresholds}) != len(thresholds):
        out.append(Problem("В шкале есть пороги с одинаковым процентом"))
    if not any(t.passed for t in thresholds):
        out.append(Problem("В шкале нет ни одной положительной оценки", WARNING))

    return out


def errors(problems: list[Problem]) -> list[Problem]:
    return [p for p in problems if p.is_error]
