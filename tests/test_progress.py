"""Тесты автосохранения прогресса попытки."""

from __future__ import annotations

import json

import pytest

from maxtest.core.progress import PendingAttempt, ProgressStore


@pytest.fixture()
def store(tmp_path):
    return ProgressStore(tmp_path / "progress")


def make_pending(**kwargs) -> PendingAttempt:
    defaults = dict(
        test_path=r"C:\tests\demo.qtest",
        test_id="t_1",
        test_title="Аттестация",
        employee_name="Иванов И.И.",
        started_at="2026-07-21T10:00:00",
        plan={"seed": 1, "question_ids": ["q1", "q2", "q3"]},
        answers={"q1": {"option_id": "a"}},
        index=1,
        elapsed_sec=42,
    )
    defaults.update(kwargs)
    return PendingAttempt(**defaults)


def test_save_and_list(store):
    pending = make_pending()
    store.save(pending)

    restored = store.list_pending()
    assert len(restored) == 1
    assert restored[0].employee_name == "Иванов И.И."
    assert restored[0].index == 1
    assert restored[0].elapsed_sec == 42
    assert restored[0].answers == {"q1": {"option_id": "a"}}


def test_saved_at_is_filled(store):
    pending = make_pending()
    store.save(pending)
    assert store.list_pending()[0].saved_at


def test_counters(store):
    pending = make_pending()
    assert pending.answered_count == 1
    assert pending.total_count == 3


def test_repeated_save_overwrites_same_file(store):
    pending = make_pending()
    store.save(pending)
    pending.index = 2
    store.save(pending)

    assert len(list(store.dir.glob("*.json"))) == 1
    assert store.list_pending()[0].index == 2


def test_delete(store):
    pending = make_pending()
    store.save(pending)
    store.delete(pending.id)
    assert store.list_pending() == []


def test_cyrillic_survives(store):
    store.save(make_pending(employee_name="Пётр Ф.Ф.", test_title="Охрана труда"))
    raw = next(store.dir.glob("*.json")).read_text(encoding="utf-8")
    assert "Пётр Ф.Ф." in raw
    assert json.loads(raw)["test_title"] == "Охрана труда"


def test_broken_file_does_not_break_startup(store):
    store.save(make_pending())
    (store.dir / "broken.json").write_text("{не json", encoding="utf-8")
    assert len(store.list_pending()) == 1  # битый файл просто пропущен


def test_no_temp_files_left(store):
    store.save(make_pending())
    assert [p.suffix for p in store.dir.iterdir()] == [".json"]
