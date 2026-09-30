"""Точка входа для PyInstaller.

Отдельный файл, а не ``maxtest/__main__.py``: PyInstaller запускает стартовый
скрипт как модуль верхнего уровня, без пакета, и относительный импорт
``from .main import main`` падает с ``ImportError: attempted relative import
with no known parent package``. В оконной сборке (``console=False``) эта ошибка
не видна вообще — процесс просто зависает на невидимом системном диалоге.

``python -m maxtest`` по-прежнему работает через ``maxtest/__main__.py``.
"""

import sys

from maxtest.main import main

if __name__ == "__main__":
    sys.exit(main())
