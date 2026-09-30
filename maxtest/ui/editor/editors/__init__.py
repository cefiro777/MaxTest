"""Редакторы вопросов — по одному на тип.

Форма для «одного правильного ответа» и для «установления соответствия»
выглядят совершенно по-разному, поэтому это не один экран с флагами, а
несколько виджетов, переключаемых через ``QStackedWidget``.
"""

from .base import BaseQuestionEditor
from .matching import MatchingEditor
from .options import OptionsEditor
from .ordering import OrderingEditor
from .text_input import TextInputEditor

__all__ = [
    "BaseQuestionEditor",
    "MatchingEditor",
    "OptionsEditor",
    "OrderingEditor",
    "TextInputEditor",
]
