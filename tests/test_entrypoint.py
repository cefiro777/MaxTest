"""Стражи точки входа и самопроверки.

Ошибка в стартовом скрипте не видна ни одному другому тесту: приложение
импортируется в них напрямую. А в оконной сборке такая ошибка вообще не
показывается — процесс молча зависает на невидимом системном диалоге.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "run_maxtest.py"


def run_entry(args: list[str], data_dir: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["MAXTEST_DATA_DIR"] = str(data_dir)
    # Иначе кодировка вывода зависит от того, из какой консоли запущены тесты.
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(ENTRY), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(ROOT),
        timeout=120,
    )


def test_entry_script_exists():
    """PyInstaller запускает стартовый скрипт без пакета — он не должен
    использовать относительные импорты."""
    source = ENTRY.read_text(encoding="utf-8")
    assert "from maxtest.main import main" in source
    # Относительных импортов быть не должно (упоминание в комментарии — можно).
    code_lines = [line for line in source.splitlines() if line.startswith("from .")]
    assert code_lines == []


def test_selfcheck_reports_ok(tmp_path):
    result = run_entry(["--selfcheck", "--quiet"], tmp_path)
    assert result.returncode == 0, result.stderr
    assert "ИТОГ: всё в порядке" in result.stdout
    assert "JPEG: да" in result.stdout


def test_selfcheck_writes_report_file(tmp_path):
    """У собранного GUI-приложения нет консоли: отчёт нужен файлом."""
    run_entry(["--selfcheck", "--quiet"], tmp_path)
    report = (tmp_path / "selfcheck.txt").read_text(encoding="utf-8")
    assert "Папка данных" in report
    assert "ИТОГ" in report


def test_selfcheck_fails_when_data_dir_not_writable(tmp_path):
    """Программа в Program Files без прав на запись должна сказать об этом."""
    blocker = tmp_path / "blocked"
    blocker.write_text("я файл, а не папка", encoding="utf-8")

    result = run_entry(["--selfcheck", "--quiet"], blocker)
    assert result.returncode != 0


def test_spec_points_at_entry_script():
    spec = (ROOT / "build" / "maxtest.spec").read_text(encoding="utf-8")
    assert "run_maxtest.py" in spec
    assert '"__main__.py"' not in spec


@pytest.mark.parametrize("marker", ["platforms", "imageformats"])
def test_spec_mentions_required_qt_plugins(marker):
    """Плагины Qt должны быть хотя бы упомянуты: без platforms приложение не
    стартует, без imageformats молча не показывает JPEG."""
    spec = (ROOT / "build" / "maxtest.spec").read_text(encoding="utf-8")
    assert marker in spec


def test_spec_avoids_onefile_and_upx():
    """--onefile и UPX — главные поводы для ложного срабатывания антивируса."""
    spec = (ROOT / "build" / "maxtest.spec").read_text(encoding="utf-8")
    assert "upx=False" in spec
    assert "COLLECT(" in spec  # onedir-сборка
