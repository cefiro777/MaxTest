"""Тесты проверки теста на готовность."""

from __future__ import annotations

from maxtest.core.enums import QuestionType, SelectionMode
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
from maxtest.core.validator import errors, validate


def good_single() -> Question:
    return Question(
        type=QuestionType.SINGLE,
        text="Вопрос",
        options=[Option(text="Да", correct=True), Option(text="Нет")],
    )


def texts(problems) -> str:
    return " | ".join(p.text for p in problems)


def test_valid_test_has_no_errors():
    test = Test(title="Аттестация", questions=[good_single()])
    assert errors(validate(test)) == []


def test_empty_test_is_error():
    assert "нет ни одного вопроса" in texts(validate(Test(title="Пустой")))


def test_question_without_text():
    q = good_single()
    q.text = ""
    assert "не задан текст" in texts(validate(Test(title="t", questions=[q])))


def test_single_with_two_correct_options():
    q = good_single()
    q.options[1].correct = True
    assert "правильных отмечено несколько" in texts(validate(Test(title="t", questions=[q])))


def test_question_without_correct_option():
    q = good_single()
    q.options[0].correct = False
    assert "не отмечен ни один" in texts(validate(Test(title="t", questions=[q])))


def test_empty_option_text():
    q = good_single()
    q.options[1].text = ""
    assert "пустые варианты" in texts(validate(Test(title="t", questions=[q])))


def test_text_question_without_answers():
    q = Question(type=QuestionType.TEXT, text="?", answer_text=TextAnswer())
    assert "не задан ни один правильный ответ" in texts(validate(Test(title="t", questions=[q])))


def test_matching_needs_two_pairs():
    q = Question(type=QuestionType.MATCHING, text="?", pairs=[MatchPair(left="a", right="b")])
    assert "меньше двух пар" in texts(validate(Test(title="t", questions=[q])))


def test_matching_duplicate_right_parts_is_warning():
    q = Question(
        type=QuestionType.MATCHING,
        text="?",
        pairs=[MatchPair(left="a", right="x"), MatchPair(left="b", right="x")],
    )
    problems = validate(Test(title="t", questions=[q]))
    assert "неоднозначно" in texts(problems)
    assert errors(problems) == []  # предупреждение, а не запрет


def test_ordering_needs_two_items():
    q = Question(type=QuestionType.ORDERING, text="?", order=[OrderItem(text="Один")])
    assert "меньше двух пунктов" in texts(validate(Test(title="t", questions=[q])))


def test_missing_image_detected():
    q = good_single()
    q.image = "media/img_dead.jpg"
    problems = validate(Test(title="t", questions=[q]), known_media=set())
    assert "картинка потеряна" in texts(problems)


def test_zero_weight_is_warning_only():
    q = good_single()
    q.weight = 0
    problems = validate(Test(title="t", questions=[q]))
    assert "вес 0" in texts(problems)
    assert errors(problems) == []


def test_random_selection_more_than_bank_warns():
    test = Test(title="t", questions=[good_single()])
    test.settings.selection_mode = SelectionMode.RANDOM
    test.settings.questions_to_ask = 10
    problems = validate(test)
    assert "запрошено 10" in texts(problems)
    assert errors(problems) == []


def test_by_section_without_sections_is_error():
    test = Test(title="t", questions=[good_single()])
    test.settings.selection_mode = SelectionMode.BY_SECTION
    assert "разделов нет" in texts(validate(test))


def test_section_take_count_more_than_available_warns():
    section = Section(id="s1", title="ОТ", take_count=5)
    q = good_single()
    q.section_id = "s1"
    test = Test(title="t", sections=[section], questions=[q])
    test.settings.selection_mode = SelectionMode.BY_SECTION
    assert "доступно 1" in texts(validate(test))


def test_scale_without_zero_threshold_is_error():
    test = Test(title="t", questions=[good_single()])
    test.grading.scale = Scale(thresholds=[Threshold(50, "Сдал", True)])
    assert "нет порога от 0" in texts(validate(test))


def test_scale_with_duplicate_percent():
    test = Test(title="t", questions=[good_single()])
    test.grading.scale = Scale(
        thresholds=[Threshold(0, "A", False), Threshold(0, "B", True)]
    )
    assert "одинаковым процентом" in texts(validate(test))


def test_scale_out_of_range():
    test = Test(title="t", questions=[good_single()])
    test.grading.scale = Scale(
        thresholds=[Threshold(0, "A", False), Threshold(140, "B", True)]
    )
    assert "вне диапазона" in texts(validate(test))
