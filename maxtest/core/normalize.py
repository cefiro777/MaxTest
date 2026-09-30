"""Нормализация текстовых ответов.

Точное сравнение убивает доверие к системе: верный ответ, не засчитанный из-за
лишнего пробела, регистра или «ё», — и человек перестаёт верить всему тесту.
Поэтому по умолчанию сравниваем нормализованные строки.
"""

from __future__ import annotations

import re

_SPACES = re.compile(r"\s+")
_TRAILING_PUNCT = re.compile(r"[.!;,]+$")


def normalize_text(value: str) -> str:
    """Регистр, пробелы, ё→е, десятичная запятая, точка в конце — не важны."""
    text = (value or "").strip().lower().replace("ё", "е")
    text = _SPACES.sub(" ", text)
    text = _TRAILING_PUNCT.sub("", text)
    # «3,5» и «3.5» — один и тот же ответ.
    text = re.sub(r"(?<=\d),(?=\d)", ".", text)
    return text
