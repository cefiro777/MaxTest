"""Собирает samples/demo.qtest — образец теста для отладки конструктора.

Запуск:  python -m tools.make_demo
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from maxtest.core.bundle import Bundle  # noqa: E402
from maxtest.core.enums import QuestionType, TextMatch  # noqa: E402
from maxtest.core.models import (  # noqa: E402
    MatchPair,
    Option,
    OrderItem,
    Question,
    Scale,
    Section,
    TextAnswer,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "samples" / "demo.qtest"


def make_sample_image(path: Path) -> Path:
    """Рисует простую схему, чтобы в демо-тесте была настоящая картинка."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (900, 500), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([50, 50, 850, 450], outline="black", width=4)
    d.line([50, 250, 850, 250], fill="red", width=6)
    d.ellipse([400, 180, 500, 280], outline="blue", width=6)
    d.text((60, 20), "Schema: fragment of the circuit", fill="black")
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def build() -> Bundle:
    bundle = Bundle.new("Демо-тест: электробезопасность")
    test = bundle.test
    test.description = "Образец для отладки конструктора и проигрывателя"
    test.author = "MaxTest"
    test.grading.scale = Scale.default_pass_fail(70)

    s_ot = Section(title="Охрана труда", take_count=2)
    s_eq = Section(title="Оборудование", take_count=2)
    test.sections = [s_ot, s_eq]

    tmp_img = ROOT / "samples" / "_tmp_schema.png"
    rel = bundle.add_image(make_sample_image(tmp_img))
    tmp_img.unlink(missing_ok=True)

    test.questions = [
        Question(
            type=QuestionType.SINGLE,
            text="Что нужно сделать в первую очередь при обнаружении оголённого провода?",
            section_id=s_ot.id,
            weight=2.0,
            image=rel,
            explanation="ПОТЭЭ, п. 3.2: сначала снимается напряжение.",
            options=[
                Option(text="Обесточить участок", correct=True),
                Option(text="Изолировать провод подручными средствами"),
                Option(text="Сообщить в конце смены"),
                Option(text="Все перечисленное", no_shuffle=True),
            ],
        ),
        Question(
            type=QuestionType.MULTI,
            text="Какие средства защиты относятся к основным при работе до 1000 В?",
            section_id=s_ot.id,
            options=[
                Option(text="Диэлектрические перчатки", correct=True),
                Option(text="Изолирующий инструмент", correct=True),
                Option(text="Диэлектрические ковры"),
                Option(text="Защитные очки"),
            ],
        ),
        Question(
            type=QuestionType.TEXT,
            text="Какое напряжение в однофазной бытовой сети? (в вольтах)",
            section_id=s_eq.id,
            answer_text=TextAnswer(accepted=["220", "220 В", "220в"], match=TextMatch.NORMALIZED),
        ),
        Question(
            type=QuestionType.MATCHING,
            text="Сопоставьте прибор и измеряемую величину",
            section_id=s_eq.id,
            pairs=[
                MatchPair(left="Амперметр", right="Сила тока"),
                MatchPair(left="Вольтметр", right="Напряжение"),
                MatchPair(left="Мегаомметр", right="Сопротивление изоляции"),
            ],
        ),
        Question(
            type=QuestionType.ORDERING,
            text="Расставьте технические мероприятия по порядку выполнения",
            section_id=s_eq.id,
            order=[
                OrderItem(text="Отключение и видимый разрыв"),
                OrderItem(text="Вывешивание запрещающих плакатов"),
                OrderItem(text="Проверка отсутствия напряжения"),
                OrderItem(text="Наложение заземления"),
            ],
        ),
    ]
    return bundle


if __name__ == "__main__":
    bundle = build()
    path = bundle.save(OUT, bump_revision=False)
    size_kb = path.stat().st_size / 1024
    print(f"Готово: {path}  ({size_kb:.1f} КБ, вопросов: {len(bundle.test.questions)})")
