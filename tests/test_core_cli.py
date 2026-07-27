import json
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pytest

from comicinfo_editor_lite.cli import main
from comicinfo_editor_lite.core import edit_archive, load_patch


def archive(path: Path, xml: bytes | None = None) -> None:
    with zipfile.ZipFile(path, "w") as handle:
        handle.writestr("001.jpg", b"page-one")
        if xml is not None:
            handle.writestr("ComicInfo.xml", xml)


def test_edit_preserves_pages_and_unknown_fields(tmp_path: Path) -> None:
    source = tmp_path / "source.cbz"
    archive(source, b"<ComicInfo><Series>Old</Series><Unknown>Keep</Unknown></ComicInfo>")
    output = tmp_path / "output.cbz"
    report = edit_archive(source, output, {"Series": "North Signal", "Year": 2026, "Title": None})
    assert report["preserved_members"] == 1
    with zipfile.ZipFile(output) as handle:
        assert handle.read("001.jpg") == b"page-one"
        root = ElementTree.fromstring(handle.read("ComicInfo.xml"))
        assert root.findtext("Series") == "North Signal"
        assert root.findtext("Unknown") == "Keep"
    assert source.is_file()


def test_new_metadata_and_safety(tmp_path: Path) -> None:
    source = tmp_path / "source.cbz"
    archive(source)
    output = tmp_path / "output.cbz"
    edit_archive(source, output, {"Title": "Arrival"})
    with pytest.raises(ValueError, match="already exists"):
        edit_archive(source, output, {"Title": "Again"})
    with pytest.raises(ValueError, match="differ"):
        edit_archive(source, source, {"Title": "Again"})
    with pytest.raises(ValueError, match="CBZ or ZIP"):
        edit_archive(tmp_path / "missing.cbr", tmp_path / "x.cbz", {"Title": "X"})


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "non-empty"),
        ({"Unsupported": "x"}, "unsupported"),
        ({"Year": "2026"}, "non-negative integer"),
        ({"Year": -1}, "non-negative integer"),
        ({"Title": 3}, "text or null"),
    ],
)
def test_patch_validation(tmp_path: Path, payload: dict[str, Any], message: str) -> None:
    path = tmp_path / "patch.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises((TypeError, ValueError), match=message):
        load_patch(path)


def test_bad_archive_paths_and_xml(tmp_path: Path) -> None:
    unsafe = tmp_path / "unsafe.cbz"
    with zipfile.ZipFile(unsafe, "w") as handle:
        handle.writestr("../page.jpg", b"bad")
    with pytest.raises(ValueError, match="unsafe"):
        edit_archive(unsafe, tmp_path / "out.cbz", {"Title": "X"})
    malformed = tmp_path / "malformed.cbz"
    archive(malformed, b"<Other />")
    with pytest.raises(ValueError, match="root"):
        edit_archive(malformed, tmp_path / "malformed-out.cbz", {"Title": "X"})


def test_duplicate_metadata_bad_suffix_and_temporary_output(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.cbz"
    with zipfile.ZipFile(duplicate, "w") as handle:
        handle.writestr("ComicInfo.xml", b"<ComicInfo />")
        handle.writestr("meta/ComicInfo.xml", b"<ComicInfo />")
    with pytest.raises(ValueError, match="multiple ComicInfo"):
        edit_archive(duplicate, tmp_path / "duplicate-out.cbz", {"Title": "X"})
    wrong = tmp_path / "source.txt"
    wrong.write_text("not an archive", encoding="utf-8")
    with pytest.raises(ValueError, match="CBZ or ZIP"):
        edit_archive(wrong, tmp_path / "wrong-out.cbz", {"Title": "X"})
    source = tmp_path / "source.cbz"
    archive(source)
    temporary = tmp_path / ".output.cbz.tmp"
    temporary.write_bytes(b"occupied")
    with pytest.raises(ValueError, match="temporary"):
        edit_archive(source, tmp_path / "output.cbz", {"Title": "X"})


def test_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "source.cbz"
    archive(source)
    patch = tmp_path / "patch.json"
    patch.write_text(json.dumps({"Title": "Arrival"}), encoding="utf-8")
    output = tmp_path / "output.cbz"
    assert main([str(source), str(patch), "--output", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["updated_fields"] == ["Title"]
    assert main([str(source), str(patch), "--output", str(output)]) == 2
