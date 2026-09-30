"""Установщик: CLI установки PIN и проверки самого скрипта Inno Setup.

Скомпилировать установщик в тестах нельзя (нужен ISCC и полная сборка), но
сам скрипт — текстовый файл, и грубые ошибки в нём ловятся чтением: забытый
`SuppressibleMsgBox` вешает тихое удаление, изменённый AppId ломает
обновление уже установленной программы.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from maxtest.core.security import PinStore  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ISS = ROOT / "build" / "maxtest.iss"
ENTRY = ROOT / "run_maxtest.py"


# ------------------------------------------------------- установка PIN из файла


def run_entry(args: list[str], data_dir: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["MAXTEST_DATA_DIR"] = str(data_dir)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(ENTRY), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, cwd=str(ROOT), timeout=120,
    )


def test_set_pin_from_file(tmp_path):
    pin_file = tmp_path / "pin.txt"
    pin_file.write_text("1234", encoding="utf-8")

    result = run_entry(["--set-pin-file", str(pin_file)], tmp_path)

    assert result.returncode == 0, result.stderr
    assert PinStore(tmp_path / "security.json").verify("1234") is True


def test_pin_file_is_deleted_after_use(tmp_path):
    """Файл с кодом не должен оставаться на диске."""
    pin_file = tmp_path / "pin.txt"
    pin_file.write_text("секрет77", encoding="utf-8")

    run_entry(["--set-pin-file", str(pin_file)], tmp_path)
    assert pin_file.exists() is False


def test_missing_pin_file_fails_gracefully(tmp_path):
    result = run_entry(["--set-pin-file", str(tmp_path / "нет.txt")], tmp_path)
    assert result.returncode == 1
    assert PinStore(tmp_path / "security.json").is_set() is False


def test_empty_pin_file_sets_nothing(tmp_path):
    pin_file = tmp_path / "pin.txt"
    pin_file.write_text("   \n", encoding="utf-8")

    result = run_entry(["--set-pin-file", str(pin_file)], tmp_path)
    assert result.returncode == 1
    assert PinStore(tmp_path / "security.json").is_set() is False


def test_too_short_pin_rejected(tmp_path):
    pin_file = tmp_path / "pin.txt"
    pin_file.write_text("12", encoding="utf-8")

    result = run_entry(["--set-pin-file", str(pin_file)], tmp_path)
    assert result.returncode == 1
    assert PinStore(tmp_path / "security.json").is_set() is False


def test_set_pin_does_not_open_window(tmp_path):
    """Установщик запускает программу скрыто: окно появляться не должно."""
    pin_file = tmp_path / "pin.txt"
    pin_file.write_text("1234", encoding="utf-8")

    result = run_entry(["--set-pin-file", str(pin_file)], tmp_path)
    assert result.returncode == 0
    # Никакого отчёта в stdout — команда служебная.
    assert result.stdout.strip() == ""


# --------------------------------------------------------- скрипт установщика


def iss_text() -> str:
    return ISS.read_text(encoding="utf-8")


def test_iss_exists():
    assert ISS.exists()


def test_silent_mode_uses_suppressible_msgbox():
    """MsgBox из [Code] игнорирует /SUPPRESSMSGBOXES и вешает тихое удаление."""
    code = iss_text().split("[Code]", 1)[1]
    plain = re.findall(r"(?<!Suppressible)MsgBox\(", code)
    assert plain == [], "в [Code] остался обычный MsgBox — тихий режим зависнет"


def test_uninstall_keeps_data_by_default():
    code = iss_text()
    assert "MB_DEFBUTTON2, IDNO" in code  # по умолчанию данные сохраняются
    assert "DelTree(DataDir()" in code    # но удалить их всё же можно


def test_app_id_is_fixed():
    """AppId связывает установку с обновлением и удалением — он не должен плавать."""
    assert "AppId={{7C1B4E52-9E1F-4A5D-9C6B-2A6F0D3B1E44}" in iss_text()


def test_install_without_admin_rights():
    assert "PrivilegesRequired=lowest" in iss_text()


def test_license_file_is_bundled():
    assert "LicenseFile=ЛИЦЕНЗИЯ.txt" in iss_text()
    assert (ROOT / "build" / "ЛИЦЕНЗИЯ.txt").exists()
    assert (ROOT / "LICENSE").exists()
    assert "MIT License" in (ROOT / "LICENSE").read_text(encoding="utf-8")


def test_desktop_shortcut_is_a_task():
    code = iss_text()
    assert 'Name: "desktopicon"' in code
    assert "{autodesktop}\\{#AppName}" in code


def test_pin_page_present():
    code = iss_text()
    assert "CreateInputQueryPage" in code
    assert "--set-pin-file" in code


def test_pin_is_not_passed_as_plain_argument():
    """PIN уходит файлом: аргументы командной строки видны в диспетчере задач."""
    code = iss_text()
    assert "--set-pin " not in code
    assert "SaveStringToFile(PinFile" in code


@pytest.mark.parametrize("path", ["docs/АДМИНИСТРАТОРУ.md", "docs/СОТРУДНИКУ.md",
                                  "samples/demo.qtest"])
def test_extra_files_are_installed(path):
    name = Path(path).name
    assert name in iss_text()
    assert (ROOT / path).exists()


def test_build_script_verifies_before_packing():
    """Заворачивать в установщик непроверенную сборку нельзя."""
    script = (ROOT / "tools" / "build_release.py").read_text(encoding="utf-8")
    verify_at = script.index("verify_app()")
    installer_at = script.index("build_installer()")
    assert verify_at < installer_at
    assert "--selfcheck" in script
