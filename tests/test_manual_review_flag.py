"""Ручная проверка на уровне вопроса, а не только всего теста."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from maxtest.core.bundle import Bundle  # noqa: E402
from maxtest.core.enums import QuestionType, TextMatch  # noqa: E402
from maxtest.core.grader import grade_question  # noqa: E402
from maxtest.core.models import GradingRules, Question, TextAnswer  # noqa: E402
from maxtest.core.schema import SCHEMA_VERSION, dump_test, load_test  # noqa: E402


def text_q(manual_review: bool | None = None) -> Question:
    return Question(
        id="q_text",
        type=QuestionType.TEXT,
        text="Опишите порядок допуска",
        answer_text=TextAnswer(accepted=["наряд-допуск"], match=TextMatch.CONTAINS),
        manual_review=manual_review,
    )


# ------------------------------------------------------------------- оценка


@pytest.mark.parametrize(
    "question_flag, test_default, expected",
    [
        (None, True, True),    # как в настройках теста
        (None, False, False),
        (True, False, True),   # вопрос важнее настройки теста
        (False, True, False),
    ],
)
def test_manual_review_resolution(question_flag, test_default, expected):
    rules = GradingRules(text_manual_review=test_default)
    result = grade_question(text_q(question_flag), {"text": "наряд-допуск"}, rules)

    assert result.needs_manual is expected
    # На ручной проверке вердикт остаётся за человеком.
    assert result.is_correct is (None if expected else True)


def test_short_answer_can_skip_review_in_strict_test():
    """Тест с ручной проверкой, но вопрос «220 В» проверять не нужно."""
    q = Question(
        type=QuestionType.TEXT,
        text="Напряжение сети?",
        answer_text=TextAnswer(accepted=["220"]),
        manual_review=False,
    )
    result = grade_question(q, {"text": "220"}, GradingRules(text_manual_review=True))
    assert result.needs_manual is False
    assert result.is_correct is True


# -------------------------------------------------------------------- формат


def test_flag_survives_round_trip():
    from .test_schema import make_full_test

    test = make_full_test()
    test.questions[2].manual_review = True
    restored = load_test(dump_test(test))
    assert restored.question_by_id("q_3").manual_review is True


def test_none_is_not_false_in_file():
    """«Как в настройках теста» и «выключено» — разные состояния."""
    from .test_schema import make_full_test

    test = make_full_test()
    data = dump_test(test)
    assert data["questions"][2]["manual_review"] is None

    test.questions[2].manual_review = False
    assert dump_test(test)["questions"][2]["manual_review"] is False


def test_old_file_version_1_still_opens(tmp_path):
    """Файлы прежней версии читаются: поля нет — значит «как в тесте»."""
    from .test_schema import make_full_test

    data = dump_test(make_full_test())
    data["schema_version"] = 1
    for question in data["questions"]:
        question.pop("manual_review", None)

    restored = load_test(data)
    assert restored.question_by_id("q_3").manual_review is None


def test_schema_version_covers_manual_review():
    """Поле добавлено в версии 2 — версия схемы не могла остаться первой."""
    assert SCHEMA_VERSION >= 2


def test_bundle_round_trip_keeps_flag(tmp_path):
    bundle = Bundle.new("Тест")
    bundle.test.questions = [text_q(True)]
    path = bundle.save(tmp_path / "t.qtest")
    assert Bundle.load(path).test.questions[0].manual_review is True


# ---------------------------------------------------------------- редактор


def test_editor_checkbox_is_editable():
    pytest.importorskip("PyQt6.QtWidgets")
    from PyQt6.QtWidgets import QApplication

    from maxtest.ui.editor.editors import TextInputEditor

    app = QApplication.instance() or QApplication([])  # noqa: F841

    editor = TextInputEditor()
    question = text_q(None)
    editor.load(question)
    editor.set_test_default(False)

    assert editor.warning.isEnabled() is True  # раньше галочка была мёртвой
    assert editor.warning.isChecked() is False
    assert "как в настройках теста" in editor.manual_source.text()

    editor.warning.setChecked(True)
    assert question.manual_review is True
    assert "для этого вопроса отдельно" in editor.manual_source.text()

    editor.warning.setChecked(False)
    assert question.manual_review is False


def test_editor_checkbox_follows_test_default():
    pytest.importorskip("PyQt6.QtWidgets")
    from PyQt6.QtWidgets import QApplication

    from maxtest.ui.editor.editors import TextInputEditor

    app = QApplication.instance() or QApplication([])  # noqa: F841

    editor = TextInputEditor()
    question = text_q(None)
    editor.load(question)
    editor.set_test_default(True)

    assert editor.warning.isChecked() is True
    assert question.manual_review is None  # отображение не должно ничего писать
