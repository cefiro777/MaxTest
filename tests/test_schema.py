"""Тесты сериализации и миграций схемы."""

from __future__ import annotations

import pytest

from maxtest.core.enums import MultiMode, QuestionType, ScaleType, TextMatch
from maxtest.core.models import (
    MatchPair,
    Option,
    OrderItem,
    Question,
    Scale,
    Section,
    Test,
    TextAnswer,
    Threshold,
)
from maxtest.core.schema import (
    SCHEMA_VERSION,
    SchemaError,
    migrate,
    load_test,
    dump_test,
)


def make_full_test() -> Test:
    """Тест со всеми пятью типами вопросов — эталон для round-trip."""
    section = Section(id="s_ot", title="Охрана труда", take_count=2)
    test = Test(title="Аттестация 2026", author="Иванов И.И.", sections=[section])
    test.grading.multi_mode = MultiMode.PARTIAL
    test.grading.scale = Scale.default_five_point()

    test.questions = [
        Question(
            id="q_1",
            type=QuestionType.SINGLE,
            text="Что делать при обнаружении оголённого провода?",
            section_id="s_ot",
            weight=2.0,
            image="media/img_ab12cd34.jpg",
            explanation="ПОТЭЭ п. 3.2",
            options=[
                Option(id="o_1", text="Обесточить участок", correct=True),
                Option(id="o_2", text="Изолировать вручную"),
                Option(id="o_3", text="Все перечисленное", no_shuffle=True),
            ],
        ),
        Question(
            id="q_2",
            type=QuestionType.MULTI,
            text="Выберите средства индивидуальной защиты",
            options=[
                Option(id="o_4", text="Каска", correct=True),
                Option(id="o_5", text="Диэлектрические перчатки", correct=True),
                Option(id="o_6", text="Отвёртка"),
            ],
        ),
        Question(
            id="q_3",
            type=QuestionType.TEXT,
            text="Напряжение бытовой сети?",
            answer_text=TextAnswer(accepted=["220 В", "220"], match=TextMatch.NORMALIZED),
        ),
        Question(
            id="q_4",
            type=QuestionType.MATCHING,
            text="Сопоставьте прибор и измеряемую величину",
            pairs=[
                MatchPair(id="p_1", left="Амперметр", right="Ток"),
                MatchPair(id="p_2", left="Вольтметр", right="Напряжение"),
            ],
        ),
        Question(
            id="q_5",
            type=QuestionType.ORDERING,
            text="Расставьте этапы допуска к работам",
            order=[
                OrderItem(id="i_1", text="Оформление наряда"),
                OrderItem(id="i_2", text="Подготовка рабочего места"),
                OrderItem(id="i_3", text="Допуск бригады"),
            ],
        ),
    ]
    return test


def test_round_trip_preserves_everything():
    original = make_full_test()
    restored = load_test(dump_test(original))

    assert dump_test(restored) == dump_test(original)
    assert restored.title == original.title
    assert len(restored.questions) == 5
    assert restored.grading.scale.type is ScaleType.FIVE_POINT


def test_ids_are_stable_through_round_trip():
    """Правильность привязана к id — они не должны перегенерироваться."""
    restored = load_test(dump_test(make_full_test()))
    q1 = restored.question_by_id("q_1")
    assert q1 is not None
    assert q1.correct_option_ids() == {"o_1"}
    assert [o.id for o in q1.options] == ["o_1", "o_2", "o_3"]


def test_no_shuffle_flag_survives():
    restored = load_test(dump_test(make_full_test()))
    q1 = restored.question_by_id("q_1")
    assert q1.option_by_id("o_3").no_shuffle is True


def test_manifest_has_schema_version():
    assert dump_test(make_full_test())["schema_version"] == SCHEMA_VERSION


def test_missing_schema_version_rejected():
    with pytest.raises(SchemaError, match="schema_version"):
        load_test({"title": "Тест", "questions": []})


def test_future_schema_version_rejected():
    data = dump_test(make_full_test())
    data["schema_version"] = SCHEMA_VERSION + 5
    with pytest.raises(SchemaError, match="более новой версией"):
        load_test(data)


def test_unknown_question_type_rejected():
    data = dump_test(make_full_test())
    data["questions"][0]["type"] = "essay"
    with pytest.raises(SchemaError, match="essay"):
        load_test(data)


def test_missing_optional_blocks_get_defaults():
    minimal = {"schema_version": SCHEMA_VERSION, "title": "Пустой", "questions": []}
    test = load_test(minimal)
    assert test.settings.shuffle_questions is True
    assert test.grading.scale.thresholds  # шкала не может быть пустой
    assert test.id  # id сгенерирован


def test_migrate_is_noop_for_current_version():
    data = dump_test(make_full_test())
    assert migrate(dict(data)) == data


def test_scale_boundaries():
    """Границы шкалы: 69/70/71 при пороге 70 (см. PLAN.md §5.2)."""
    scale = Scale.default_pass_fail(70)
    assert scale.grade(69).passed is False
    assert scale.grade(70).passed is True
    assert scale.grade(71).passed is True


def test_scale_without_zero_threshold_falls_back():
    scale = Scale(thresholds=[Threshold(50, "Сдал", True)])
    assert scale.grade(10).passed is False
