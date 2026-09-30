# -*- mode: python ; coding: utf-8 -*-
"""Сборка MaxTest в папку с .exe.

Запуск из корня проекта:

    .venv\\Scripts\\pyinstaller build\\maxtest.spec --noconfirm

Почему ``--onedir``, а не ``--onefile``: одиночный .exe регулярно ловит ложное
срабатывание Windows Defender и корпоративных антивирусов — распаковка кода во
временную папку при запуске выглядит для них подозрительно. Папку проще
согласовать с ИТ-службой, и запускается она быстрее.

Плагины Qt перечислены явно, хотя штатный хук PyInstaller обычно тащит их сам:
без ``platforms/qwindows.dll`` приложение не стартует вовсе, а без
``imageformats`` молча не показывает JPEG в вопросах. Проверить собранное:

    dist\\MaxTest\\MaxTest.exe --selfcheck
"""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
ICON = ROOT / "maxtest" / "resources" / "icon.ico"

datas = []
# Картинки и иконки пакета: без них собранное приложение не найдёт QR-код
# для окна «Поддержать проект».
for resource in (ROOT / "maxtest" / "resources").glob("*"):
    if resource.is_file():
        datas.append((str(resource), "maxtest/resources"))

if (ROOT / "samples" / "demo.qtest").exists():
    datas.append((str(ROOT / "samples" / "demo.qtest"), "samples"))
for doc in ("АДМИНИСТРАТОРУ.md", "СОТРУДНИКУ.md"):
    path = ROOT / "docs" / doc
    if path.exists():
        datas.append((str(path), "docs"))

a = Analysis(
    # Именно run_maxtest.py, а не maxtest/__main__.py: PyInstaller запускает
    # стартовый скрипт без пакета, и относительный импорт внутри __main__.py
    # падает ещё до создания окна.
    [str(ROOT / "run_maxtest.py")],
    pathex=[str(ROOT)],
    # binaries НЕ собираем через collect_dynamic_libs("PyQt6"): он тащит все
    # DLL Qt подряд (Qml, Quick, Designer, кодеки, opengl32sw) — это +130 МБ
    # мёртвого груза. Штатный хук PyInstaller берёт только нужные модули и
    # уважает excludes ниже.
    binaries=[],
    datas=datas,
    hiddenimports=[
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.sip",
        "openpyxl",
        "PIL.Image",
    ],
    hookspath=[],
    runtime_hooks=[],
    # Сеть приложению не нужна по требованию заказчика, лишние модули Qt —
    # это десятки мегабайт и лишние поводы для антивируса.
    excludes=[
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtQml",
        "PyQt6.QtQuick",
        "PyQt6.QtBluetooth",
        "PyQt6.QtMultimedia",
        "PyQt6.QtPositioning",
        "PyQt6.QtSql",
        "PyQt6.QtTest",
        "tkinter",
        "matplotlib",
        "numpy",
        "pytest",
        "PySide6",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MaxTest",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX-упаковка — ещё один повод для ложного срабатывания антивируса
    console=False,
    icon=str(ICON) if ICON.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="MaxTest",
)
