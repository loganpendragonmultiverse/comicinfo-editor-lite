import json
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pytest

from comicinfo_editor_lite.cli import main
from comicinfo_editor_lite.core import (
    directory_batch,
    edit_archive,
    load_batch,
    load_patch,
    plan_archive,
    run_batch,
)


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
    report = json.loads(capsys.readouterr().out)
    assert report["results"][0]["updated_fields"] == ["Title"]
    assert main([str(source), str(patch), "--output", str(output)]) == 1


def test_dry_run_diff_and_transaction_evidence(tmp_path: Path) -> None:
    source = tmp_path / "source.cbz"
    archive(source, b"<ComicInfo><Series>Old</Series><Year>2020</Year></ComicInfo>")
    plan = plan_archive(source, {"Series": "New", "Year": 2020, "Title": None})
    assert plan["changed_fields"] == ["Series"]
    assert {item["action"] for item in plan["changes"]} == {"set", "unchanged"}
    output = tmp_path / "output.cbz"
    result = edit_archive(source, output, {"Series": "New"})
    assert result["rollback_required"] is False
    assert "atomic replacement" in result["transaction"]


def test_json_and_csv_batch_manifests_with_template(tmp_path: Path) -> None:
    first, second = tmp_path / "one.cbz", tmp_path / "two.cbz"
    archive(first)
    archive(second)
    manifest = tmp_path / "batch.json"
    manifest.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "source": str(first),
                        "output": str(tmp_path / "one-out.cbz"),
                        "patch": {"Number": "1"},
                    },
                    {
                        "source": str(second),
                        "output": str(tmp_path / "two-out.cbz"),
                        "patch": {"Number": "2"},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    report = run_batch(load_batch(manifest), {"Series": "Example"}, dry_run=True)
    assert report["succeeded"] == 2 and report["dry_run"] is True
    csv_path = tmp_path / "batch.csv"
    csv_path.write_text(
        f"source,output,Title,Year\n{first},{tmp_path / 'csv-out.cbz'},Arrival,2026\n",
        encoding="utf-8",
    )
    csv_jobs = load_batch(csv_path)
    assert csv_jobs[0]["patch"] == {"Title": "Arrival", "Year": 2026}


def test_directory_discovery_and_partial_failure_report(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    archive(source_dir / "good.cbz")
    jobs = directory_batch(source_dir, tmp_path / "out", {"Publisher": "Forge"}, False)
    jobs.append(
        {
            "source": str(source_dir / "missing.cbz"),
            "output": str(tmp_path / "missing-out.cbz"),
            "patch": {"Publisher": "Forge"},
        }
    )
    report = run_batch(jobs)
    assert report["succeeded"] == 1 and report["failed"] == 1
    assert report["all_succeeded"] is False


def test_batch_cli_dry_run_and_invalid_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source.cbz"
    archive(source)
    manifest = tmp_path / "batch.json"
    manifest.write_text(
        json.dumps({"jobs": [{"source": str(source), "patch": {"Title": "X"}}]}), encoding="utf-8"
    )
    assert main(["--batch", str(manifest), "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True
    assert main([]) == 2


def test_batch_manifest_validation_and_remove_marker(tmp_path: Path) -> None:
    invalid_csv = tmp_path / "invalid.csv"
    invalid_csv.write_text("source,Title\na.cbz,X\n", encoding="utf-8")
    with pytest.raises(ValueError, match="source and output"):
        load_batch(invalid_csv)
    csv_path = tmp_path / "remove.csv"
    csv_path.write_text("source,output,Title\na.cbz,b.cbz,__REMOVE__\n", encoding="utf-8")
    assert load_batch(csv_path)[0]["patch"]["Title"] is None
    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty jobs"):
        load_batch(invalid_json)
    with pytest.raises(ValueError, match="at least one"):
        run_batch([])


def test_directory_mode_cli_and_single_dry_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source_dir = tmp_path / "source"
    nested = source_dir / "nested"
    nested.mkdir(parents=True)
    source = nested / "one.cbz"
    archive(source)
    template = tmp_path / "template.json"
    template.write_text(json.dumps({"Publisher": "Forge"}), encoding="utf-8")
    assert (
        main(
            [
                "--source-dir",
                str(source_dir),
                "--output-dir",
                str(tmp_path / "out"),
                "--template",
                str(template),
                "--recursive",
                "--dry-run",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["succeeded"] == 1
    patch = tmp_path / "patch.json"
    patch.write_text(json.dumps({"Title": "Planned"}), encoding="utf-8")
    assert main([str(source), str(patch), "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True
    assert main([str(source), str(patch)]) == 2
    assert main(["--source-dir", str(source_dir), "--output-dir", str(tmp_path / "out")]) == 2


def test_empty_directory_and_missing_batch_output(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="no CBZ"):
        directory_batch(empty, tmp_path / "out", {"Title": "X"}, False)
    source = tmp_path / "source.cbz"
    archive(source)
    report = run_batch([{"source": str(source), "patch": {"Title": "X"}}])
    assert report["failed"] == 1
