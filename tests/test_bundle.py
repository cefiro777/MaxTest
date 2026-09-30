"""Тесты формата .qtest: round-trip, атомарность, медиа, битые файлы."""

from __future__ import annotations

import json
import zipfile

import pytest

from maxtest.core.bundle import MANIFEST_NAME, Bundle, BundleError
from maxtest.core.schema import SCHEMA_VERSION, dump_test

from .test_schema import make_full_test

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000d49444154789c6360000002000100ffff03000006"
    "00057dd4b1cb0000000049454e44ae426082"
)


def test_save_and_load_round_trip(tmp_path):
    bundle = Bundle(make_full_test())
    path = bundle.save(tmp_path / "demo.qtest", bump_revision=False)

    assert path.exists()
    loaded = Bundle.load(path)
    assert dump_test(loaded.test) == dump_test(bundle.test)
    assert loaded.path == path


def test_saved_file_is_a_zip_with_manifest(tmp_path):
    path = Bundle(make_full_test()).save(tmp_path / "demo.qtest")
    with zipfile.ZipFile(path) as zf:
        data = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
    assert data["schema_version"] == SCHEMA_VERSION


def test_cyrillic_survives_windows_default_encoding(tmp_path):
    path = Bundle(make_full_test()).save(tmp_path / "кириллица.qtest")
    with zipfile.ZipFile(path) as zf:
        raw = zf.read(MANIFEST_NAME).decode("utf-8")
    assert "Охрана труда" in raw
    assert Bundle.load(path).test.sections[0].title == "Охрана труда"


def test_extension_added_automatically(tmp_path):
    path = Bundle(make_full_test()).save(tmp_path / "no_ext")
    assert path.suffix == ".qtest"


def test_overwrite_self_works(tmp_path):
    """На Windows перезапись открытого zip «поверх себя» — классический PermissionError."""
    target = tmp_path / "demo.qtest"
    bundle = Bundle(make_full_test())
    bundle.save(target, bump_revision=False)

    reopened = Bundle.load(target)
    reopened.test.title = "Изменённый"
    reopened.save()  # без указания пути — поверх себя

    assert Bundle.load(target).test.title == "Изменённый"


def test_save_bumps_revision_and_mtime(tmp_path):
    bundle = Bundle(make_full_test())
    before = bundle.test.revision
    bundle.save(tmp_path / "demo.qtest")
    assert bundle.test.revision == before + 1


def test_no_temp_files_left_after_save(tmp_path):
    Bundle(make_full_test()).save(tmp_path / "demo.qtest")
    assert [p.name for p in tmp_path.iterdir()] == ["demo.qtest"]


def test_media_round_trip(tmp_path):
    bundle = Bundle.new("С картинкой")
    rel = bundle.add_image_bytes(PNG_1PX, ".png")
    q = make_full_test().questions[0]
    q.image = rel
    bundle.test.questions = [q]

    path = bundle.save(tmp_path / "img.qtest")
    loaded = Bundle.load(path)

    assert loaded.get_image_bytes(rel) == PNG_1PX
    assert loaded.missing_media == []


def test_same_image_stored_once():
    bundle = Bundle.new("Дубли")
    a = bundle.add_image_bytes(PNG_1PX, ".png")
    b = bundle.add_image_bytes(PNG_1PX, ".png")
    assert a == b
    assert len(bundle.media) == 1


def test_missing_media_reported(tmp_path):
    bundle = Bundle(make_full_test())  # вопрос ссылается на несуществующий файл
    path = bundle.save(tmp_path / "broken.qtest")
    loaded = Bundle.load(path)
    assert loaded.missing_media == ["media/img_ab12cd34.jpg"]


def test_prune_media_removes_orphans():
    bundle = Bundle.new("Мусор")
    rel = bundle.add_image_bytes(PNG_1PX, ".png")
    assert bundle.prune_media() == [rel]
    assert bundle.media == {}


def test_load_broken_zip(tmp_path):
    path = tmp_path / "broken.qtest"
    path.write_bytes(b"not a zip at all")
    with pytest.raises(BundleError, match="повреждён"):
        Bundle.load(path)


def test_load_zip_without_manifest(tmp_path):
    path = tmp_path / "alien.qtest"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("readme.txt", "hello")
    with pytest.raises(BundleError, match="не файл теста"):
        Bundle.load(path)


def test_load_missing_file(tmp_path):
    with pytest.raises(BundleError, match="не найден"):
        Bundle.load(tmp_path / "nope.qtest")


def test_zip_slip_entries_ignored(tmp_path):
    path = tmp_path / "evil.qtest"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(MANIFEST_NAME, json.dumps(dump_test(make_full_test())))
        zf.writestr("../evil.exe", b"payload")
        zf.writestr("media/../../evil2.exe", b"payload")
    loaded = Bundle.load(path)
    assert loaded.media == {}


def test_save_without_path_raises():
    with pytest.raises(BundleError, match="Не указан путь"):
        Bundle.new("Без пути").save()


def test_add_image_missing_file(tmp_path):
    with pytest.raises(BundleError, match="не найдена"):
        Bundle.new("t").add_image(tmp_path / "nope.jpg")


def test_add_image_resizes_large_photo(tmp_path):
    """Фото 3000px должно ужаться до 1200px и стать JPEG."""
    Image = pytest.importorskip("PIL.Image")
    src = tmp_path / "photo.png"
    Image.new("RGB", (3000, 2000), "red").save(src)

    bundle = Bundle.new("Фото")
    rel = bundle.add_image(src)

    assert rel.endswith(".jpg")
    from io import BytesIO

    with Image.open(BytesIO(bundle.media[rel])) as img:
        assert max(img.size) == 1200
    assert len(bundle.media[rel]) < src.stat().st_size or len(bundle.media[rel]) < 500_000


def test_add_image_keeps_png_with_alpha(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    src = tmp_path / "logo.png"
    Image.new("RGBA", (100, 100), (255, 0, 0, 128)).save(src)

    rel = Bundle.new("Лого").add_image(src)
    assert rel.endswith(".png")
