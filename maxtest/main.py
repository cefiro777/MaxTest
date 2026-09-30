"""Точка входа MaxTest.

Здесь три вещи, которые в собранном ``.exe`` обычно вспоминают слишком поздно:

* политика DPI — без неё на экране с масштабом 125 % интерфейс мыльный;
* ``excepthook`` — в GUI-сборке консоли нет, и необработанное исключение просто
  молча закрывает окно, не оставляя следов;
* лог доступных форматов изображений — если в сборку не доехал плагин Qt
  ``imageformats``, JPEG в вопросах не откроется, и причину видно только здесь.
"""

from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path
from logging.handlers import RotatingFileHandler

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QGuiApplication, QImageReader
from PyQt6.QtWidgets import QApplication, QMessageBox

from . import __version__
from .core.paths import data_dir, logs_dir
from .core.security import PinError, PinStore
from .core.storage import Storage
from .ui import theme
from .ui.app_window import AppWindow

log = logging.getLogger("maxtest")


def setup_logging() -> None:
    handler = RotatingFileHandler(
        logs_dir() / "maxtest.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def install_excepthook() -> None:
    def hook(exc_type, exc_value, exc_tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        log.error("Необработанная ошибка:\n%s", text)
        QMessageBox.critical(
            None,
            "Ошибка",
            "Произошла непредвиденная ошибка. Подробности записаны в журнал:\n"
            f"{logs_dir() / 'maxtest.log'}\n\n{exc_value}",
        )

    sys.excepthook = hook


def selfcheck() -> int:
    """Диагностика собранного приложения: ``MaxTest.exe --selfcheck``.

    Проверяет ровно то, что чаще всего ломается в сборке PyInstaller: доехали
    ли плагины Qt (платформа и форматы изображений) и есть ли права на запись
    в папку данных. Без такой команды разбираться на чужом компьютере, где нет
    ни Python, ни консоли, крайне неудобно.
    """
    app = QApplication(sys.argv)
    formats = sorted(bytes(f).decode() for f in QImageReader.supportedImageFormats())

    try:
        probe = data_dir() / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        writable = "да"
    except OSError as exc:
        writable = f"НЕТ ({exc})"

    ok = "jpg" in formats and "png" in formats and writable == "да"
    lines = [
        f"MaxTest {__version__}",
        f"Платформа Qt: {app.platformName()}",
        f"Форматы изображений: {', '.join(formats) or 'нет'}",
        f"JPEG: {'да' if 'jpg' in formats else 'НЕТ — картинки не отобразятся'}",
        f"PNG:  {'да' if 'png' in formats else 'НЕТ — картинки не отобразятся'}",
        f"Папка данных: {data_dir()}",
        f"Запись в папку данных: {writable}",
        f"ИТОГ: {'всё в порядке' if ok else 'ЕСТЬ ПРОБЛЕМЫ (см. выше)'}",
    ]
    report = "\n".join(lines)

    # Консоль Windows по умолчанию в cp866: без переключения на UTF-8 русский
    # отчёт превращается в мусор, а на части кодировок print и вовсе падает.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    # У собранного GUI-приложения консоли нет: print() уходит в никуда.
    # Поэтому отчёт всегда пишется в файл и показывается диалогом.
    try:
        print(report)
    except (UnicodeEncodeError, OSError):
        pass
    try:
        (data_dir() / "selfcheck.txt").write_text(report, encoding="utf-8")
    except OSError:
        pass

    if "--quiet" not in sys.argv:
        box = QMessageBox()
        box.setWindowTitle("Проверка MaxTest")
        box.setIcon(QMessageBox.Icon.Information if ok else QMessageBox.Icon.Warning)
        box.setText(report)
        box.exec()

    return 0 if ok else 1


def set_pin_from_file(path: str) -> int:
    """``MaxTest.exe --set-pin-file <файл>`` — установка PIN при инсталляции.

    PIN передаётся файлом, а не аргументом командной строки: аргументы видны
    в диспетчере задач любому пользователю системы. Файл читается один раз и
    сразу удаляется, что бы дальше ни случилось.
    """
    source = Path(path)
    try:
        pin = source.read_text(encoding="utf-8").strip()
    except OSError as exc:
        log.error("Не удалось прочитать файл с PIN: %s", exc)
        return 1
    finally:
        try:
            source.unlink(missing_ok=True)
        except OSError:
            pass

    if not pin:
        return 1
    try:
        PinStore().set_pin(pin)
    except (PinError, OSError) as exc:
        log.error("Не удалось установить PIN: %s", exc)
        return 1
    return 0


def main() -> int:
    if "--selfcheck" in sys.argv:
        return selfcheck()

    if "--set-pin-file" in sys.argv:
        index = sys.argv.index("--set-pin-file")
        if index + 1 >= len(sys.argv):
            return 1
        setup_logging()
        return set_pin_from_file(sys.argv[index + 1])

    # Должно вызываться ДО создания QApplication.
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("MaxTest")
    theme.apply(app)

    setup_logging()
    install_excepthook()

    formats = sorted(bytes(f).decode() for f in QImageReader.supportedImageFormats())
    log.info("Форматы изображений Qt: %s", ", ".join(formats))
    if "jpg" not in formats:
        log.warning("Плагин JPEG не найден — картинки в тестах не отобразятся")

    storage = Storage()
    try:
        storage.backup()
    except Exception:  # бэкап не должен мешать работе
        log.exception("Не удалось создать резервную копию базы")

    window = AppWindow(storage)
    window.show()
    # Оборванные попытки предлагаем восстановить сразу после показа окна.
    QTimer.singleShot(0, window.check_pending_attempts)
    try:
        return app.exec()
    finally:
        window.shutdown()  # окна закрываем до базы, а не наоборот
        storage.close()


if __name__ == "__main__":
    sys.exit(main())
