"""Развёрнутый текстовый ответ и окно поддержки проекта."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from maxtest.core.bundle import Bundle  # noqa: E402
from maxtest.core.enums import QuestionType, TextMatch  # noqa: E402
from maxtest.core.grader import grade_question  # noqa: E402
from maxtest.core.models import GradingRules, Question, TextAnswer  # noqa: E402
from maxtest.core.resources import read_bytes, resource_path  # noqa: E402
from maxtest.core.schema import SCHEMA_VERSION, dump_test, load_test  # noqa: E402
from maxtest.ui.donate_dialog import QR_FILE, DonateDialog  # noqa: E402
from maxtest.ui.widgets.question_view import QuestionView  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def text_question(multiline: bool) -> Question:
    return Question(
        id="q_text",
        type=QuestionType.TEXT,
        text="Опишите порядок допуска к работам",
        answer_text=TextAnswer(
            accepted=["наряд-допуск"], match=TextMatch.CONTAINS, multiline=multiline
        ),
    )


# ------------------------------------------------------- многострочный ответ


def test_text_answer_field_wraps_and_grows(qapp):
    """Любой текстовый ответ — растущее поле с переносом, а не QLineEdit,
    который прятал длинный ответ под горизонтальный ползунок."""
    from maxtest.ui.widgets.growing_text import GrowingTextEdit

    view = QuestionView()
    view.set_question(text_question(multiline=False))
    assert isinstance(view._text_area, GrowingTextEdit)


def test_multiline_answer_starts_taller(qapp):
    """Развёрнутый ответ отличается только стартовой высотой поля."""
    view_short = QuestionView()
    view_short.set_question(text_question(multiline=False))
    short = view_short._text_area

    view_long = QuestionView()
    view_long.set_question(text_question(multiline=True))
    long = view_long._text_area

    assert long._min_lines > short._min_lines


def test_multiline_answer_is_collected(qapp):
    view = QuestionView()
    view.set_question(text_question(multiline=True))
    view._text_area.setPlainText("Сначала оформляется наряд-допуск,\nзатем инструктаж")

    answer = view.answer()
    assert "наряд-допуск" in answer["text"]
    assert "\n" in answer["text"]


def test_multiline_answer_survives_going_back(qapp):
    """Возврат к вопросу должен вернуть написанный текст целиком."""
    question = text_question(multiline=True)
    saved = {"text": "Первая строка\nВторая строка"}

    view = QuestionView()
    view.set_question(question, answer=saved)
    assert view._text_area.toPlainText() == saved["text"]
    assert view.answer() == saved


def test_empty_multiline_answer_is_none(qapp):
    view = QuestionView()
    view.set_question(text_question(multiline=True))
    view._text_area.setPlainText("   \n  ")
    assert view.answer() is None


def test_line_breaks_do_not_break_grading():
    """Перенос строки в ответе не должен мешать сравнению с эталоном."""
    question = text_question(multiline=True)
    result = grade_question(
        question,
        {"text": "Оформляется\nнаряд-допуск\nи проводится инструктаж"},
        GradingRules(),
    )
    assert result.score == 1.0


def test_multiline_flag_round_trip(tmp_path):
    bundle = Bundle.new("Тест")
    bundle.test.questions = [text_question(multiline=True)]
    path = bundle.save(tmp_path / "t.qtest")

    restored = Bundle.load(path).test.questions[0]
    assert restored.answer_text.multiline is True


def test_old_files_open_as_single_line():
    from .test_schema import make_full_test

    data = dump_test(make_full_test())
    data["schema_version"] = 1
    for question in data["questions"]:
        question.pop("manual_review", None)
        if question.get("answer_text"):
            question["answer_text"].pop("multiline", None)

    restored = load_test(data)
    assert restored.question_by_id("q_3").answer_text.multiline is False


def test_schema_version_bumped():
    assert SCHEMA_VERSION == 3


def test_editor_has_multiline_checkbox(qapp):
    from maxtest.ui.editor.editors import TextInputEditor

    editor = TextInputEditor()
    question = text_question(multiline=False)
    editor.load(question)

    assert editor.multiline.isChecked() is False
    editor.multiline.setChecked(True)
    assert question.answer_text.multiline is True


# --------------------------------------------------------------- поддержка


def test_qr_resource_exists():
    path = resource_path(QR_FILE)
    assert path.exists(), "картинка QR-кода не найдена в maxtest/resources"
    assert path.stat().st_size > 1000
    assert read_bytes(QR_FILE)[:8] == b"\x89PNG\r\n\x1a\n"


def test_missing_resource_returns_none():
    assert read_bytes("нет-такого-файла.png") is None


def test_donate_dialog_shows_qr(qapp):
    dialog = DonateDialog()
    assert dialog._pixmap is not None
    assert dialog.qr.pixmap() is not None
    assert dialog.save_button.isEnabled() is True


def test_donate_dialog_survives_missing_resource(qapp, monkeypatch):
    """Отсутствие картинки в сборке не должно ронять окно."""
    monkeypatch.setattr("maxtest.ui.donate_dialog.read_bytes", lambda name: None)

    dialog = DonateDialog()
    assert dialog._pixmap is None
    assert dialog.save_button.isEnabled() is False
    assert "недоступен" in dialog.qr.text()


def test_donate_saves_original_file(qapp, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog

    target = tmp_path / "qr.png"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), ""))
    )
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    )

    DonateDialog().save_qr()
    assert target.read_bytes() == read_bytes(QR_FILE)


def test_main_window_has_donate_button(qapp, tmp_path, monkeypatch):
    from maxtest.core.progress import ProgressStore
    from maxtest.core.storage import Storage
    from maxtest.ui.app_window import AppWindow

    monkeypatch.setenv("MAXTEST_DATA_DIR", str(tmp_path))
    with Storage(tmp_path / "results.db") as storage:
        window = AppWindow(storage, progress=ProgressStore(tmp_path / "progress"))
        assert "Поддержать" in window.donate_button.text()


def test_spec_bundles_resources():
    from pathlib import Path

    spec = (Path(__file__).resolve().parents[1] / "build" / "maxtest.spec").read_text(
        encoding="utf-8"
    )
    assert "maxtest/resources" in spec
