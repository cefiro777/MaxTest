"""Позволяет запускать приложение как ``python -m maxtest``."""

import sys

from .main import main

sys.exit(main())
