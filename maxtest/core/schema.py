"""Сериализация модели в manifest.json и обратно + миграции схемы.

Сериализация написана вручную, а не через ``dataclasses.asdict``, намеренно:
формат файла — публичный контракт, он должен меняться отдельно от внутренних
имён полей. Любое изменение структуры = +1 к ``SCHEMA_VERSION`` и новая
функция миграции в ``_MIGRATIONS``.
"""

from __future__ import annotations

from typing import Any, Callable

from .enums import (
    MultiMode,
    QuestionType,
    ScaleType,
    SelectionMode,
    TextMatch,
)
from .models import (
    GradingRules,
    MatchPair,
    Option,
    OrderItem,
    Question,
    Scale,
    Section,
    Test,
    TestSettings,
    TextAnswer,
    Threshold,
    new_id,
    now_iso,
)

SCHEMA_VERSION = 3


class SchemaError(Exception):
    """Manifest не читается: чужая версия, битая структура, неизвестный тип."""


# --------------------------------------------------------------------------
# Хелперы чтения (мягкие: отсутствующее поле = значение по умолчанию)
# --------------------------------------------------------------------------


def _req(data: dict, key: str, where: str) -> Any:
    if key not in data:
        raise SchemaError(f"{where}: отсутствует обязательное поле '{key}'")
    return data[key]


def _enum(cls, value: Any, where: str):
    try:
        return cls(value)
    except ValueError:
        allowed = ", ".join(m.value for m in cls)
        raise SchemaError(f"{where}: недопустимое значение '{value}' (ожидалось: {allowed})")


def _int_or_none(value: Any) -> int | None:
    return None if value is None else int(value)


def _bool_or_none(value: Any) -> bool | None:
    """``None`` — «как в настройках теста», а не «выключено»."""
    return None if value is None else bool(value)


# --------------------------------------------------------------------------
# Test -> dict
# --------------------------------------------------------------------------


def dump_test(test: Test) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "id": test.id,
        "title": test.title,
        "description": test.description,
        "author": test.author,
        "created_at": test.created_at,
        "modified_at": test.modified_at,
        "revision": test.revision,
        "settings": _settings_to_dict(test.settings),
        "grading": _grading_to_dict(test.grading),
        "sections": [
            {"id": s.id, "title": s.title, "take_count": s.take_count}
            for s in test.sections
        ],
        "questions": [_question_to_dict(q) for q in test.questions],
    }


def _settings_to_dict(s: TestSettings) -> dict:
    return {
        "shuffle_questions": s.shuffle_questions,
        "shuffle_options": s.shuffle_options,
        "questions_to_ask": s.questions_to_ask,
        "selection_mode": s.selection_mode.value,
        "time_limit_sec": s.time_limit_sec,
        "time_limit_per_question_sec": s.time_limit_per_question_sec,
        "allow_back": s.allow_back,
        "show_result_to_user": s.show_result_to_user,
        "show_review_to_user": s.show_review_to_user,
    }


def _grading_to_dict(g: GradingRules) -> dict:
    return {
        "multi_mode": g.multi_mode.value,
        "partial_penalty": g.partial_penalty,
        "text_manual_review": g.text_manual_review,
        "scale": {
            "type": g.scale.type.value,
            "thresholds": [
                {"min_percent": t.min_percent, "label": t.label, "passed": t.passed}
                for t in g.scale.thresholds
            ],
        },
    }


def _question_to_dict(q: Question) -> dict:
    data: dict[str, Any] = {
        "id": q.id,
        "type": q.type.value,
        "text": q.text,
        "weight": q.weight,
        "section_id": q.section_id,
        "image": q.image,
        "explanation": q.explanation,
        "manual_review": q.manual_review,
        "options": [
            {
                "id": o.id,
                "text": o.text,
                "correct": o.correct,
                "no_shuffle": o.no_shuffle,
            }
            for o in q.options
        ],
        "answer_text": None,
        "pairs": None,
        "order": None,
    }
    if q.answer_text is not None:
        data["answer_text"] = {
            "accepted": list(q.answer_text.accepted),
            "match": q.answer_text.match.value,
            "multiline": q.answer_text.multiline,
        }
    if q.pairs is not None:
        data["pairs"] = [{"id": p.id, "left": p.left, "right": p.right} for p in q.pairs]
    if q.order is not None:
        data["order"] = [{"id": i.id, "text": i.text} for i in q.order]
    return data


# --------------------------------------------------------------------------
# dict -> Test
# --------------------------------------------------------------------------


def load_test(data: dict) -> Test:
    if not isinstance(data, dict):
        raise SchemaError("manifest.json: ожидался объект JSON")

    data = migrate(data)

    test = Test(
        id=data.get("id") or new_id("t_"),
        title=data.get("title", ""),
        description=data.get("description", ""),
        author=data.get("author", ""),
        created_at=data.get("created_at") or now_iso(),
        modified_at=data.get("modified_at") or now_iso(),
        revision=int(data.get("revision", 1)),
        settings=_settings_from_dict(data.get("settings") or {}),
        grading=_grading_from_dict(data.get("grading") or {}),
        sections=[_section_from_dict(s) for s in data.get("sections") or []],
        questions=[_question_from_dict(q) for q in data.get("questions") or []],
    )
    return test


def _settings_from_dict(d: dict) -> TestSettings:
    default = TestSettings()
    return TestSettings(
        shuffle_questions=bool(d.get("shuffle_questions", default.shuffle_questions)),
        shuffle_options=bool(d.get("shuffle_options", default.shuffle_options)),
        questions_to_ask=_int_or_none(d.get("questions_to_ask")),
        selection_mode=_enum(
            SelectionMode, d.get("selection_mode", default.selection_mode.value), "settings"
        ),
        time_limit_sec=_int_or_none(d.get("time_limit_sec")),
        time_limit_per_question_sec=_int_or_none(d.get("time_limit_per_question_sec")),
        allow_back=bool(d.get("allow_back", default.allow_back)),
        show_result_to_user=bool(d.get("show_result_to_user", default.show_result_to_user)),
        show_review_to_user=bool(d.get("show_review_to_user", default.show_review_to_user)),
    )


def _grading_from_dict(d: dict) -> GradingRules:
    default = GradingRules()
    scale_data = d.get("scale") or {}
    thresholds = [
        Threshold(
            min_percent=int(t.get("min_percent", 0)),
            label=t.get("label", ""),
            passed=bool(t.get("passed", False)),
        )
        for t in scale_data.get("thresholds") or []
    ]
    if not thresholds:
        thresholds = Scale.default_pass_fail().thresholds

    return GradingRules(
        multi_mode=_enum(MultiMode, d.get("multi_mode", default.multi_mode.value), "grading"),
        partial_penalty=bool(d.get("partial_penalty", default.partial_penalty)),
        text_manual_review=bool(d.get("text_manual_review", default.text_manual_review)),
        scale=Scale(
            type=_enum(ScaleType, scale_data.get("type", ScaleType.PASS_FAIL.value), "scale"),
            thresholds=thresholds,
        ),
    )


def _section_from_dict(d: dict) -> Section:
    return Section(
        id=d.get("id") or new_id("s_"),
        title=d.get("title", ""),
        take_count=_int_or_none(d.get("take_count")),
    )


def _question_from_dict(d: dict) -> Question:
    where = f"вопрос {d.get('id', '?')}"
    qtype = _enum(QuestionType, _req(d, "type", where), where)

    q = Question(
        id=d.get("id") or new_id("q_"),
        type=qtype,
        text=d.get("text", ""),
        weight=float(d.get("weight", 1.0)),
        section_id=d.get("section_id"),
        image=d.get("image"),
        explanation=d.get("explanation", ""),
        manual_review=_bool_or_none(d.get("manual_review")),
        options=[
            Option(
                id=o.get("id") or new_id("o_"),
                text=o.get("text", ""),
                correct=bool(o.get("correct", False)),
                no_shuffle=bool(o.get("no_shuffle", False)),
            )
            for o in d.get("options") or []
        ],
    )

    answer_text = d.get("answer_text")
    if answer_text:
        q.answer_text = TextAnswer(
            accepted=list(answer_text.get("accepted") or []),
            match=_enum(
                TextMatch, answer_text.get("match", TextMatch.NORMALIZED.value), where
            ),
            multiline=bool(answer_text.get("multiline", False)),
        )

    pairs = d.get("pairs")
    if pairs:
        q.pairs = [
            MatchPair(
                id=p.get("id") or new_id("p_"),
                left=p.get("left", ""),
                right=p.get("right", ""),
            )
            for p in pairs
        ]

    order = d.get("order")
    if order:
        q.order = [
            OrderItem(id=i.get("id") or new_id("i_"), text=i.get("text", ""))
            for i in order
        ]

    return q


# --------------------------------------------------------------------------
# Миграции
# --------------------------------------------------------------------------

def _migrate_1_to_2(data: dict) -> dict:
    """v2 добавила у вопроса ``manual_review`` (ручная проверка ответа).

    Данные править не нужно: отсутствующее поле читается как ``None``, то есть
    «как задано в настройках теста» — прежнее поведение файлов версии 1.
    """
    return data


def _migrate_2_to_3(data: dict) -> dict:
    """v3 добавила ``answer_text.multiline`` — поле ввода на несколько строк.

    Старые тесты открываются как однострочные: ровно так они и работали.
    """
    return data


# Ключ — версия, ИЗ которой мигрируем. Функция поднимает данные на +1.
_MIGRATIONS: dict[int, Callable[[dict], dict]] = {
    1: _migrate_1_to_2,
    2: _migrate_2_to_3,
}


def migrate(data: dict) -> dict:
    """Поднимает manifest до текущей ``SCHEMA_VERSION``."""
    version = data.get("schema_version")
    if version is None:
        raise SchemaError("manifest.json: отсутствует 'schema_version'")
    try:
        version = int(version)
    except (TypeError, ValueError):
        raise SchemaError(f"manifest.json: некорректная версия схемы: {version!r}")

    if version > SCHEMA_VERSION:
        raise SchemaError(
            f"Файл создан более новой версией программы (схема {version}, "
            f"поддерживается до {SCHEMA_VERSION}). Обновите MaxTest."
        )

    while version < SCHEMA_VERSION:
        step = _MIGRATIONS.get(version)
        if step is None:
            raise SchemaError(f"Не найдена миграция схемы с версии {version}")
        data = step(data)
        version += 1
        data["schema_version"] = version

    return data
