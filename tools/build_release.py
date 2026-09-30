"""Полная сборка релиза: иконка → приложение → установщик.

Запуск:  .venv\\Scripts\\python -m tools.build_release

Что делает по шагам:
  1. рисует иконку (tools/make_icon.py);
  2. пересобирает демо-тест, который кладётся в установщик;
  3. собирает приложение PyInstaller в dist\\MaxTest (папка, не onefile);
  4. проверяет собранное командой ``MaxTest.exe --selfcheck --quiet``;
  5. компилирует установщик Inno Setup в dist\\MaxTest-Setup-<версия>.exe.

Шаг 4 намеренно между сборкой и установщиком: заворачивать в инсталлятор
заведомо нерабочую сборку — верный способ узнать о проблеме уже на рабочем
компьютере заказчика.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
APP_DIR = DIST / "MaxTest"
SPEC = ROOT / "build" / "maxtest.spec"
ISS = ROOT / "build" / "maxtest.iss"
STABLE_NAME = "MaxTest-Setup.exe"

ISCC_CANDIDATES = (
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
)


def log(message: str) -> None:
    print(f"\n=== {message}", flush=True)


def run(command: list[str], **kwargs) -> None:
    print("  $", " ".join(str(c) for c in command), flush=True)
    subprocess.run(command, check=True, cwd=str(ROOT), **kwargs)


def python() -> str:
    return sys.executable


def find_iscc() -> Path | None:
    for candidate in ISCC_CANDIDATES:
        if candidate.exists():
            return candidate
    found = shutil.which("ISCC.exe")
    return Path(found) if found else None


def installer_version() -> str:
    """Версия установщика берётся из .iss — единственного места, где она задана."""
    text = ISS.read_text(encoding="utf-8")
    match = re.search(r'#define\s+AppVersion\s+"([^"]+)"', text)
    return match.group(1) if match else "0.0.0"


def build_app() -> None:
    log("Сборка приложения (PyInstaller)")
    run([python(), "-m", "PyInstaller", str(SPEC), "--noconfirm",
         "--distpath", str(DIST), "--workpath", str(ROOT / "build" / "work")])


def verify_app() -> None:
    log("Проверка собранного приложения (--selfcheck)")
    exe = APP_DIR / "MaxTest.exe"
    if not exe.exists():
        raise SystemExit(f"Не найден {exe}: сборка приложения не удалась")

    result = subprocess.run([str(exe), "--selfcheck", "--quiet"], cwd=str(ROOT))
    if result.returncode != 0:
        raise SystemExit(
            "Самопроверка собранного приложения не прошла — установщик не собираем. "
            "Подробности в %APPDATA%\\MaxTest\\selfcheck.txt"
        )
    print("  самопроверка пройдена", flush=True)


def build_installer() -> Path:
    log("Сборка установщика (Inno Setup)")
    iscc = find_iscc()
    if iscc is None:
        raise SystemExit(
            "Не найден ISCC.exe (компилятор Inno Setup 6).\n"
            "Установите Inno Setup 6 с https://jrsoftware.org/isdl.php "
            "или укажите путь в PATH."
        )

    run([str(iscc), str(ISS)])
    target = DIST / f"MaxTest-Setup-{installer_version()}.exe"
    if not target.exists():
        raise SystemExit(f"Установщик не создан: {target}")

    # Копия с постоянным именем: кнопка «Скачать» в README ведёт на
    # /releases/latest/download/MaxTest-Setup.exe и должна работать для любой версии.
    shutil.copyfile(target, DIST / STABLE_NAME)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Сборка релиза MaxTest")
    parser.add_argument(
        "--skip-app", action="store_true",
        help="не пересобирать приложение (использовать готовое в dist\\MaxTest)",
    )
    args = parser.parse_args()

    log("Иконка и демо-тест")
    run([python(), "-m", "tools.make_icon"])
    run([python(), "-m", "tools.make_demo"])

    if not args.skip_app:
        build_app()
    verify_app()
    installer = build_installer()

    size_mb = installer.stat().st_size / 1024 / 1024
    log("Готово")
    print(f"  Установщик: {installer}  ({size_mb:.1f} МБ)")
    print(f"  Приложение: {APP_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
