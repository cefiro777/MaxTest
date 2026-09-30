"""Модель данных теста.

Ключевые правила (см. PLAN.md §2.3):

* у каждого вопроса и варианта есть стабильный ``id``; правильность привязана
  к ``id``, а НИКОГДА к позиции в списке — иначе перемешивание вариантов
  разнесёт всю привязку;
* путь к картинке — относительный внутри бандла (``media/...``), абсолютных
  путей в модели быть не может.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from .enums import (
    MultiMode,
    QuestionType,
    ScaleType,
    SelectionMode,
    TextMatch,
)


def new_id(prefix: str = "") -> str:
    """Короткий стабильный идентификатор."""
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


# --------------------------------------------------------------------------
# Составные части вопроса
# --------------------------------------------------------------------------


@dataclass
class Option:
    """Вариант ответа для single/multi."""

    id: str = field(default_factory=lambda: new_id("o_"))
    text: str = ""
    correct: bool = False
    no_shuffle: bool = False  # «все перечисленное» — держать на месте


@dataclass
class TextAnswer:
    """Эталоны для вопроса с вводом текста.

    ``accepted`` — список ДОПУСТИМЫХ ВАРИАНТОВ ответа (каждый сам по себе
    верный), а не строки одного длинного ответа.
    """

    accepted: list[str] = field(default_factory=list)
    match: TextMatch = TextMatch.NORMALIZED
    #: Поле ввода на несколько строк — для развёрнутых ответов.
    multiline: bool = False


@dataclass
class MatchPair:
    """Пара для установления соответствия: left ↔ right."""

    id: str = field(default_factory=lambda: new_id("p_"))
    left: str = ""
    right: str = ""


@dataclass
class OrderItem:
    """Элемент упорядочивания. Правильный порядок = порядок в списке."""

    id: str = field(default_factory=lambda: new_id("i_"))
    text: str = ""


@dataclass
class Question:
    id: str = field(default_factory=lambda: new_id("q_"))
    type: QuestionType = QuestionType.SINGLE
    text: str = ""
    weight: float = 1.0
    section_id: str | None = None
    image: str | None = None
    options: list[Option] = field(default_factory=list)
    answer_text: TextAnswer | None = None
    pairs: list[MatchPair] | None = None
    order: list[OrderItem] | None = None
    explanation: str = ""
    #: Ручная проверка ответа: ``None`` — как задано в настройках теста,
    #: ``True``/``False`` — решение для конкретного вопроса. Короткий ответ
    #: «220 В» проверять вручную не нужно, а развёрнутый — нужно.
    manual_review: bool | None = None

    def option_by_id(self, option_id: str) -> Option | None:
        return next((o for o in self.options if o.id == option_id), None)

    def correct_option_ids(self) -> set[str]:
        return {o.id for o in self.options if o.correct}

    def needs_manual_review(self, test_default: bool) -> bool:
        """Проверять ли ответ вручную с учётом настройки теста."""
        return test_default if self.manual_review is None else self.manual_review


# --------------------------------------------------------------------------
# Настройки теста
# --------------------------------------------------------------------------


@dataclass
class Section:
    id: str = field(default_factory=lambda: new_id("s_"))
    title: str = ""
    take_count: int | None = None  # сколько вопросов брать при selection_mode=by_section


@dataclass
class TestSettings:
    shuffle_questions: bool = True
    shuffle_options: bool = True
    questions_to_ask: int | None = None  # None = все
    selection_mode: SelectionMode = SelectionMode.ALL
    time_limit_sec: int | None = None
    time_limit_per_question_sec: int | None = None
    allow_back: bool = False
    show_result_to_user: bool = True
    show_review_to_user: bool = False


@dataclass
class Threshold:
    """Порог шкалы. Проценты — только целые (см. PLAN.md §5.2)."""

    min_percent: int = 0
    label: str = ""
    passed: bool = False


@dataclass
class Scale:
    type: ScaleType = ScaleType.PASS_FAIL
    thresholds: list[Threshold] = field(default_factory=list)

    def grade(self, percent: int) -> Threshold:
        """Порог для целого процента. Порядок в списке не важен."""
        ordered = sorted(self.thresholds, key=lambda t: t.min_percent, reverse=True)
        for t in ordered:
            if percent >= t.min_percent:
                return t
        # Страховка: шкала без нулевого порога — считаем «не сдал».
        return Threshold(min_percent=0, label="Не сдал", passed=False)

    @staticmethod
    def default_pass_fail(pass_percent: int = 70) -> "Scale":
        return Scale(
            type=ScaleType.PASS_FAIL,
            thresholds=[
                Threshold(pass_percent, "Сдал", True),
                Threshold(0, "Не сдал", False),
            ],
        )

    @staticmethod
    def default_five_point() -> "Scale":
        return Scale(
            type=ScaleType.FIVE_POINT,
            thresholds=[
                Threshold(85, "Отлично", True),
                Threshold(70, "Хорошо", True),
                Threshold(55, "Удовлетворительно", True),
                Threshold(0, "Неудовлетворительно", False),
            ],
        )


@dataclass
class GradingRules:
    multi_mode: MultiMode = MultiMode.PARTIAL
    partial_penalty: bool = True
    text_manual_review: bool = False
    scale: Scale = field(default_factory=Scale.default_pass_fail)


# --------------------------------------------------------------------------
# Тест
# --------------------------------------------------------------------------


@dataclass
class Test:
    # Класс называется Test — иначе pytest пытается собрать его как тест-класс.
    __test__ = False

    id: str = field(default_factory=lambda: new_id("t_"))
    title: str = "Новый тест"
    description: str = ""
    author: str = ""
    created_at: str = field(default_factory=now_iso)
    modified_at: str = field(default_factory=now_iso)
    revision: int = 1
    settings: TestSettings = field(default_factory=TestSettings)
    grading: GradingRules = field(default_factory=GradingRules)
    sections: list[Section] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)

    def question_by_id(self, question_id: str) -> Question | None:
        return next((q for q in self.questions if q.id == question_id), None)

    def section_by_id(self, section_id: str) -> Section | None:
        return next((s for s in self.sections if s.id == section_id), None)

    def questions_of_section(self, section_id: str | None) -> list[Question]:
        return [q for q in self.questions if q.section_id == section_id]

    def used_images(self) -> set[str]:
        """Пути картинок, на которые ссылаются вопросы (для очистки media/)."""
        return {q.image for q in self.questions if q.image}
