"""PIN-код: хранение и защита разделов интерфейса."""

from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from maxtest.core.security import MIN_LENGTH, PinError, PinStore  # noqa: E402


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("MAXTEST_DATA_DIR", str(tmp_path))
    return PinStore(tmp_path / "security.json")


# ------------------------------------------------------------------- хранение


def test_no_pin_by_default(store):
    assert store.is_set() is False
    assert store.verify("1234") is False


def test_set_and_verify(store):
    store.set_pin("1234")
    assert store.is_set() is True
    assert store.verify("1234") is True
    assert store.verify("4321") is False
    assert store.verify("") is False


def test_pin_is_not_stored_in_plain_text(store):
    store.set_pin("сек-рет-77")
    raw = store.path.read_text(encoding="utf-8")

    assert "сек-рет-77" not in raw
    data = json.loads(raw)
    assert set(data) >= {"hash", "salt", "iterations"}
    assert len(data["hash"]) == 64  # sha256 в hex


def test_same_pin_gives_different_hashes(tmp_path, monkeypatch):
    """Соль у каждой установки своя — одинаковые коды не видны по файлу."""
    monkeypatch.setenv("MAXTEST_DATA_DIR", str(tmp_path))
    first = PinStore(tmp_path / "a.json")
    second = PinStore(tmp_path / "b.json")
    first.set_pin("1234")
    second.set_pin("1234")

    a = json.loads(first.path.read_text(encoding="utf-8"))
    b = json.loads(second.path.read_text(encoding="utf-8"))
    assert a["salt"] != b["salt"]
    assert a["hash"] != b["hash"]


def test_too_short_pin_rejected(store):
    with pytest.raises(PinError):
        store.set_pin("1" * (MIN_LENGTH - 1))
    assert store.is_set() is False


def test_pin_is_trimmed_but_case_sensitive(store):
    store.set_pin("  Пароль12  ")
    assert store.verify("Пароль12") is True
    assert store.verify("пароль12") is False


def test_change_pin(store):
    store.set_pin("1234")
    store.set_pin("5678")
    assert store.verify("1234") is False
    assert store.verify("5678") is True


def test_clear(store):
    store.set_pin("1234")
    store.clear()
    assert store.is_set() is False
    store.clear()  # повторный вызов не должен падать


def test_broken_file_means_no_pin(store):
    store.path.write_text("{сломано", encoding="utf-8")
    assert store.is_set() is False
    assert store.verify("1234") is False


def test_no_temp_files_left(store):
    store.set_pin("1234")
    assert [p.suffix for p in store.path.parent.iterdir()] == [".json"]


# ------------------------------------------------------------- защита разделов


@pytest.fixture(scope="module")
def qapp():
    """Ссылку на QApplication нужно удерживать: без неё Qt падает вместе с
    интерпретатором, когда объект соберёт сборщик мусора."""
    pytest.importorskip("PyQt6.QtWidgets")
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def no_modal_dialogs(monkeypatch, qapp):
    """Модальные окна без пользователя вешают прогон навсегда."""
    from PyQt6.QtWidgets import QMessageBox

    for name in ("warning", "critical", "information"):
        monkeypatch.setattr(
            QMessageBox, name,
            staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok),
        )
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )


@pytest.fixture()
def app_window(tmp_path, monkeypatch, qapp, no_modal_dialogs):
    from maxtest.core.progress import ProgressStore
    from maxtest.core.storage import Storage
    from maxtest.ui.app_window import AppWindow

    monkeypatch.setenv("MAXTEST_DATA_DIR", str(tmp_path))

    storage = Storage(tmp_path / "results.db")
    window = AppWindow(storage, progress=ProgressStore(tmp_path / "progress"))
    yield window
    storage.close()


def test_sections_open_when_no_pin(app_window):
    assert app_window.require_pin("Конструктор тестов") is True
    assert "не задан" in app_window.security_label.text()


def test_pin_blocks_section_when_dialog_cancelled(app_window, monkeypatch):
    from PyQt6.QtWidgets import QDialog

    app_window.pin.set_pin("1234")
    app_window.lock()
    monkeypatch.setattr(
        "maxtest.ui.app_window.PinDialog.exec",
        lambda self: QDialog.DialogCode.Rejected,
    )
    assert app_window.require_pin("Конструктор тестов") is False


def test_correct_pin_unlocks_for_a_while(app_window, monkeypatch):
    from PyQt6.QtWidgets import QDialog

    app_window.pin.set_pin("1234")
    app_window.lock()
    monkeypatch.setattr(
        "maxtest.ui.app_window.PinDialog.exec",
        lambda self: QDialog.DialogCode.Accepted,
    )

    assert app_window.require_pin("Результаты") is True
    assert app_window.unlocked is True
    # Второй раз код уже не спрашивается: подменённый exec не понадобится.
    monkeypatch.setattr(
        "maxtest.ui.app_window.PinDialog.exec",
        lambda self: pytest.fail("PIN спрошен повторно внутри окна разблокировки"),
    )
    assert app_window.require_pin("Конструктор тестов") is True


def test_unlock_expires(app_window, monkeypatch):
    import time

    from PyQt6.QtWidgets import QDialog

    app_window.pin.set_pin("1234")
    monkeypatch.setattr(
        "maxtest.ui.app_window.PinDialog.exec",
        lambda self: QDialog.DialogCode.Accepted,
    )
    app_window.require_pin("Результаты")

    app_window._unlocked_until = time.monotonic() - 1  # время вышло
    assert app_window.unlocked is False


def test_lock_button_closes_sections(app_window, monkeypatch):
    from PyQt6.QtWidgets import QDialog

    app_window.pin.set_pin("1234")
    monkeypatch.setattr(
        "maxtest.ui.app_window.PinDialog.exec",
        lambda self: QDialog.DialogCode.Accepted,
    )
    app_window.require_pin("Результаты")
    assert app_window.lock_button.isVisible() is False or app_window.unlocked

    app_window.lock()
    assert app_window.unlocked is False
    assert "закрыты" in app_window.security_label.text()


def test_starting_test_locks_sections(app_window, monkeypatch, tmp_path):
    """Сотрудник садится за компьютер — разделы должны закрыться сразу."""
    from PyQt6.QtWidgets import QDialog

    from maxtest.core.bundle import Bundle
    from maxtest.core.enums import QuestionType
    from maxtest.core.models import Option, Question
    from maxtest.core.session import build_plan

    app_window.pin.set_pin("1234")
    monkeypatch.setattr(
        "maxtest.ui.app_window.PinDialog.exec",
        lambda self: QDialog.DialogCode.Accepted,
    )
    app_window.require_pin("Результаты")
    assert app_window.unlocked is True

    bundle = Bundle.new("Тест")
    bundle.test.questions = [
        Question(
            type=QuestionType.SINGLE,
            text="Вопрос",
            options=[Option(text="Да", correct=True), Option(text="Нет")],
        )
    ]
    app_window._start_player(bundle, build_plan(bundle.test, seed=1), "Иванов", None)

    assert app_window.unlocked is False
    app_window.shutdown()


def test_pin_dialog_counts_attempts(tmp_path, monkeypatch, qapp):
    from PyQt6.QtWidgets import QMessageBox

    from maxtest.ui.pin_dialog import MAX_ATTEMPTS, PinDialog

    monkeypatch.setenv("MAXTEST_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    )

    store = PinStore(tmp_path / "security.json")
    store.set_pin("1234")
    dialog = PinDialog(store, "Результаты")

    dialog.pin.setText("0000")
    dialog._on_accept()
    assert dialog.attempts == 1
    assert "Осталось попыток" in dialog.error.text()
    assert dialog.pin.text() == ""  # поле очищено

    for _ in range(MAX_ATTEMPTS - 1):
        dialog.pin.setText("0000")
        dialog._on_accept()
    assert dialog.attempts == MAX_ATTEMPTS

    dialog.pin.setText("1234")
    dialog._on_accept()
    assert dialog.result() == int(dialog.DialogCode.Accepted)
