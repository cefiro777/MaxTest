"""Собирает страницу сайта из шаблона и картинок.

Из одного шаблона получаются два разных файла:

* ``index.html`` — для своего сервера. Своя обвязка ``<head>`` (без
  ``<meta charset>`` браузер угадывает кодировку и ломает кириллицу),
  картинки — **отдельными файлами** в ``assets/`` и микроразметка schema.org.
  Картинки внешними файлами дают три вещи: страница весит ~20 КБ вместо 370 КБ,
  картинки кешируются браузером и попадают в поиск по картинкам.
* ``artifact.html`` — для артефакта на claude.ai: там обвязку добавляет сам
  артефакт, а страница обязана быть самодостаточной, поэтому картинки остаются
  внутри как data URI.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

SITE = "https://infomaxtest.ru"
VERSION = "1.0.0"
INSTALLER = f"MaxTest-Setup-{VERSION}.exe"

DESCRIPTION = (
    "MaxTest — бесплатная программа для тестирования и аттестации сотрудников "
    "на одном компьютере с Windows: конструктор тестов с картинками, 5 типов "
    "вопросов, отчёты в Excel. Работает без интернета, данные не уходят на "
    "чужие серверы."
)

#: Подписи к картинкам — они же alt-тексты и названия файлов.
IMAGE_FILES = {
    "main": "glavnoe-okno.jpg",
    "player": "prohozhdenie-testa.jpg",
    "editor": "konstruktor-testov.jpg",
    "results": "rezultaty-attestacii.jpg",
    "attempt": "razbor-popytki.jpg",
    "multiline": "razvernutyy-otvet.jpg",
    "qr": "podderzhat-proekt.png",
}

#: Счётчик Яндекс.Метрики. Вставляется только в версию для сайта: в артефакте
#: на claude.ai внешние скрипты запрещены политикой безопасности, и считать
#: посещения там нечего. Вставка идёт заменой, а не через str.format —
#: в коде счётчика есть фигурные скобки, format их бы съел.
METRIKA = """<!-- Yandex.Metrika counter -->
<script type="text/javascript">
    (function(m,e,t,r,i,k,a){
        m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
        m[i].l=1*new Date();
        for (var j = 0; j < document.scripts.length; j++) {if (document.scripts[j].src === r) { return; }}
        k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)
    })(window, document,'script','https://mc.yandex.ru/metrika/tag.js?id=110946682', 'ym');

    ym(110946682, 'init', {ssr:true, webvisor:true, clickmap:true, ecommerce:"dataLayer", referrer: document.referrer, url: location.href, accurateTrackBounce:true, trackLinks:true});
</script>
<noscript><div><img src="https://mc.yandex.ru/watch/110946682" style="position:absolute; left:-9999px;" alt="" /></div></noscript>
<!-- /Yandex.Metrika counter -->
"""

SKELETON = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{description}">
<meta name="color-scheme" content="light dark">
<link rel="canonical" href="{site}/">
<link rel="icon" href="/favicon.ico" sizes="any">
<meta property="og:site_name" content="MaxTest">
<meta property="og:title" content="MaxTest — программа для аттестации сотрудников офлайн">
<meta property="og:description" content="{description}">
<meta property="og:type" content="website">
<meta property="og:url" content="{site}/">
<meta property="og:locale" content="ru_RU">
<meta property="og:image" content="{site}/assets/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{site}/assets/og-image.png">
{title}
<script type="application/ld+json">
{jsonld}
</script>
</head>
<body>
{body}
</body>
</html>
"""


def structured_data(faq: list[tuple[str, str]], steps: list[tuple[str, str]]) -> str:
    """Микроразметка: карточка программы, инструкция и вопросы-ответы.

    Поисковики и ИИ-ассистенты берут отсюда факты в готовом виде — версию,
    цену, систему, ссылку на установщик — не пытаясь вычитать их из вёрстки.
    """
    graph = [
        {
            "@type": "SoftwareApplication",
            "@id": f"{SITE}/#software",
            "name": "MaxTest",
            "alternateName": "МаксТест",
            "description": DESCRIPTION,
            "url": f"{SITE}/",
            "applicationCategory": "BusinessApplication",
            "applicationSubCategory": "Тестирование и аттестация персонала",
            "operatingSystem": "Windows 10, Windows 11",
            "softwareVersion": VERSION,
            "downloadUrl": f"{SITE}/download/{INSTALLER}",
            "installUrl": f"{SITE}/",
            "fileSize": "28.4 MB",
            "inLanguage": "ru",
            "license": "https://opensource.org/licenses/MIT",
            "codeRepository": "https://github.com/cefiro777/MaxTest",
            "sameAs": ["https://github.com/cefiro777/MaxTest"],
            "isAccessibleForFree": True,
            "offers": {"@type": "Offer", "price": "0", "priceCurrency": "RUB"},
            "image": f"{SITE}/assets/og-image.png",
            "screenshot": [
                f"{SITE}/assets/{IMAGE_FILES[key]}"
                for key in ("main", "player", "editor", "results")
            ],
            "featureList": [
                "Конструктор тестов с картинками",
                "Пять типов вопросов: один ответ, несколько ответов, ввод текста, "
                "установление соответствия, упорядочивание",
                "Перемешивание вопросов и вариантов ответа",
                "Случайная выборка вопросов из банка и разделы по темам",
                "Ограничение времени на тест с автоматической сдачей",
                "Гибкая шкала оценок и веса вопросов",
                "Ручная проверка развёрнутых текстовых ответов",
                "Отчёты в Excel и разбор попытки по вопросам",
                "PIN-код на административные разделы",
                "Работа без интернета, данные хранятся локально",
            ],
        },
        {
            "@type": "HowTo",
            "@id": f"{SITE}/#howto",
            "name": "Как провести аттестацию сотрудников в MaxTest",
            "description": "От установки программы до готового протокола в Excel.",
            "inLanguage": "ru",
            "totalTime": "PT30M",
            "step": [
                {
                    "@type": "HowToStep",
                    "position": index,
                    "name": name,
                    "text": text,
                    "url": f"{SITE}/#guide",
                }
                for index, (name, text) in enumerate(steps, start=1)
            ],
        },
        {
            "@type": "FAQPage",
            "@id": f"{SITE}/#faq",
            "inLanguage": "ru",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": question,
                    "acceptedAnswer": {"@type": "Answer", "text": answer},
                }
                for question, answer in faq
            ],
        },
    ]
    return json.dumps(
        {"@context": "https://schema.org", "@graph": graph},
        ensure_ascii=False, indent=1,
    )


def extract_faq(html: str) -> list[tuple[str, str]]:
    """Вопросы и ответы берутся из самой страницы.

    Микроразметка обязана совпадать с видимым текстом — иначе это разметка
    того, чего на странице нет, и поисковик вправе счесть её обманом.
    """
    import re

    pairs = []
    for block in re.findall(r"<details[^>]*>(.*?)</details>", html, re.S):
        question = re.search(r"<summary>(.*?)</summary>", block, re.S)
        answer = re.search(r"<p>(.*?)</p>", block, re.S)
        if question and answer:
            pairs.append((clean(question.group(1)), clean(answer.group(1))))
    return pairs


def extract_steps(html: str) -> list[tuple[str, str]]:
    import re

    steps = []
    for block in re.findall(r'<article class="step">(.*?)</article>', html, re.S):
        name = re.search(r"<h3>(.*?)</h3>", block, re.S)
        text = re.search(r"<p>(.*?)</p>", block, re.S)
        if name and text:
            steps.append((clean(name.group(1)), clean(text.group(1))))
    return steps


def clean(text: str) -> str:
    import html as html_module
    import re

    text = re.sub(r"<[^>]+>", "", text)
    return html_module.unescape(" ".join(text.split()))


def write_assets(images: dict[str, str], assets: Path) -> None:
    assets.mkdir(parents=True, exist_ok=True)
    for key, name in IMAGE_FILES.items():
        header, payload = images[key].split(",", 1)
        (assets / name).write_bytes(base64.b64decode(payload))


def main() -> None:
    here = Path(__file__).parent
    template = (here / "template.html").read_text(encoding="utf-8")
    images = json.loads((here / "images.json").read_text(encoding="utf-8"))

    write_assets(images, here / "assets")

    # --- вариант для артефакта: картинки внутри файла
    artifact = template
    for key, uri in images.items():
        artifact = artifact.replace("{{%s}}" % key, uri)
    assert "{{" not in artifact
    (here / "artifact.html").write_text(artifact, encoding="utf-8")

    # --- вариант для сайта: картинки ссылками
    page = template
    for key, name in IMAGE_FILES.items():
        page = page.replace("{{%s}}" % key, f"/assets/{name}")
    assert "{{" not in page

    start = page.index("<title>")
    end = page.index("</title>") + len("</title>")
    title = page[start:end]
    body = (page[:start] + page[end:]).strip()

    jsonld = structured_data(extract_faq(template), extract_steps(template))
    site_page = SKELETON.format(
        description=DESCRIPTION, site=SITE, title=title, body=body, jsonld=jsonld
    )
    site_page = site_page.replace("</head>", METRIKA + "</head>", 1)
    (here / "index.html").write_text(site_page, encoding="utf-8")

    print(f"index.html:    {(here / 'index.html').stat().st_size / 1024:.0f} КБ "
          f"(картинки отдельно)")
    print(f"artifact.html: {(here / 'artifact.html').stat().st_size / 1024:.0f} КБ "
          f"(картинки внутри)")
    total = sum(f.stat().st_size for f in (here / "assets").iterdir())
    print(f"assets/:       {total / 1024:.0f} КБ, файлов: {len(list((here / 'assets').iterdir()))}")


if __name__ == "__main__":
    main()
