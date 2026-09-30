"""Перечисления модели.

Все значения — строки: они уходят в manifest.json как есть и должны читаться
человеком при отладке файла теста.
"""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """Enum, который сериализуется в JSON как обычная строка."""

    def __str__(self) -> str:
        return self.value


class QuestionType(StrEnum):
    SINGLE = "single"        # один правильный ответ
    MULTI = "multi"          # несколько правильных
    TEXT = "text"            # ввод текста/числа
    MATCHING = "matching"    # установление соответствия
    ORDERING = "ordering"    # упорядочивание


class MultiMode(StrEnum):
    ALL_OR_NOTHING = "all_or_nothing"
    PARTIAL = "partial"


class TextMatch(StrEnum):
    EXACT = "exact"              # посимвольное совпадение
    NORMALIZED = "normalized"    # регистр, пробелы, ё→е, запятая→точка
    CONTAINS = "contains"        # эталон входит в ответ (после нормализации)


class SelectionMode(StrEnum):
    ALL = "all"                # все вопросы банка
    RANDOM = "random"          # случайные N из банка
    BY_SECTION = "by_section"  # по take_count из каждого раздела


class ScaleType(StrEnum):
    PASS_FAIL = "pass_fail"
    FIVE_POINT = "five_point"
    CUSTOM = "custom"


class FinishReason(StrEnum):
    COMPLETED = "completed"
    TIMEOUT = "timeout"
    ABORTED = "aborted"
