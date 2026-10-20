import json
from pathlib import Path
from zipfile import ZipFile, ZipInfo

import pytest

from comicinfo_editor_lite import core


def make_archive(path, metadata=b"<ComicInfo><Title>Old</Title></ComicInfo>"):
    with ZipFile(path, "w") as archive:
        archive.writestr("page.bin", b"page" * 1000)
        archive.writestr("ComicInfo.xml", metadata)


@pytest.mark.parametrize("value", ["New", None], ids=["set", "remove"])
def test_duplicate_patched_fields_refused_before_output(tmp_path, value):
    source = tmp_path / "source.cbz"
    make_archive(source, b"<ComicInfo><Title>A</Title><Title>B</Title></ComicInfo>")
    output = tmp_path / "new" / "output.cbz"
    before = source.read_bytes()
    with pytest.raises(ValueError, match="ambiguous duplicate"):
        core.plan_archive(source, {"Title": value})
    with pytest.raises(ValueError, match="ambiguous duplicate"):
        core.edit_archive(source, output, {"Title": value})
    assert not output.parent.exists()
    assert source.read_bytes() == before


@pytest.mark.parametrize(
    "patch",
    [{"Unsupported": "x"}, {"Year": True}, {}, {"Title": []}],
    ids=["unknown", "bool-year", "empty", "array-title"],
)
def test_direct_api_validates_patch(tmp_path, patch):
    source = tmp_path / "source.cbz"
    make_archive(source)
    with pytest.raises((TypeError, ValueError)):
        core.plan_archive(source, patch)
    with pytest.raises((TypeError, ValueError)):
        core.edit_archive(source, tmp_path / "output.cbz", patch)


def test_streaming_hash_and_page_copy(tmp_path, monkeypatch):
    source = tmp_path / "source.cbz"
    make_archive(source)
    original_read = ZipFile.read

    def read(archive, name, *args, **kwargs):
        filename = name.filename if isinstance(name, ZipInfo) else name
        assert filename == "ComicInfo.xml", "page bytes must stream"
        return original_read(archive, name, *args, **kwargs)

    def whole_file_forbidden(path):
        raise AssertionError("archive hashing must stream")

    monkeypatch.setattr(ZipFile, "read", read)
    monkeypatch.setattr(Path, "read_bytes", whole_file_forbidden)
    output = tmp_path / "output.cbz"
    result = core.edit_archive(source, output, {"Title": "New"})
    assert result["preserved_members"] == 1
    with ZipFile(output) as archive, archive.open("page.bin") as member:
        assert member.read() == b"page" * 1000


@pytest.mark.parametrize("dangling", [False, True], ids=["existing", "dangling"])
def test_output_links_preserved(tmp_path, dangling):
    source = tmp_path / "source.cbz"
    make_archive(source)
    target = tmp_path / "target.cbz"
    if not dangling:
        target.write_bytes(b"valuable")
    output = tmp_path / "output.cbz"
    try:
        output.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError):
        core.edit_archive(source, output, {"Title": "New"})
    assert output.is_symlink()
    assert target.read_bytes() == b"valuable" if not dangling else not target.exists()


def test_concurrent_output_and_temporary_ownership(tmp_path, monkeypatch):
    source = tmp_path / "source.cbz"
    make_archive(source)
    output = tmp_path / "output.cbz"
    other = tmp_path / "unrelated.tmp"
    other.write_bytes(b"keep")
    link = core.os.link

    def raced(temporary, destination):
        destination.write_bytes(b"concurrent")
        return link(temporary, destination)

    monkeypatch.setattr(core.os, "link", raced)
    with pytest.raises(FileExistsError):
        core.edit_archive(source, output, {"Title": "New"})
    assert output.read_bytes() == b"concurrent"
    assert other.read_bytes() == b"keep"
    assert not list(tmp_path.glob(".output.cbz.*.tmp"))


@pytest.mark.parametrize(
    "csv",
    [
        "source,source,output\\na,b,c\\n",
        "source,output,Unknown\\na,b,c\\n",
        "source,output\\na\\n",
        "source,output\\na,b,c\\n",
    ],
    ids=["duplicate-header", "unknown-header", "short-row", "long-row"],
)
def test_csv_structure(tmp_path, csv):
    path = tmp_path / "jobs.csv"
    path.write_text(csv.replace("\\n", chr(10)))
    with pytest.raises(ValueError):
        core.load_batch(path)


def test_json_structure_and_individual_job_isolation(tmp_path):
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps({"jobs": [None]}))
    with pytest.raises(ValueError, match="object"):
        core.load_batch(path)
    source = tmp_path / "source.cbz"
    make_archive(source)
    report = core.run_batch(
        [
            None,
            {},
            {"source": str(source), "patch": []},
            {"source": str(source), "output": 1, "patch": {"Title": "x"}},
            {
                "source": str(source),
                "output": str(tmp_path / "good.cbz"),
                "patch": {"Title": "New"},
            },
        ]
    )
    assert report["failed"] == 4
    assert report["succeeded"] == 1


def test_unsupported_header_isolated_in_batch(tmp_path):
    source = tmp_path / "source.cbz"
    make_archive(source)
    bad = tmp_path / "bad.cbz"
    info = ZipInfo("page.txt")
    info.extract_version = 99
    info.create_version = 99
    with ZipFile(bad, "w") as archive:
        archive.writestr(info, b"page")
    report = core.run_batch(
        [
            {"source": str(bad), "output": str(tmp_path / "bad-out.cbz"), "patch": {"Title": "x"}},
            {
                "source": str(source),
                "output": str(tmp_path / "good-out.cbz"),
                "patch": {"Title": "x"},
            },
        ]
    )
    assert report["failed"] == 1 and report["succeeded"] == 1
    assert not (tmp_path / "bad-out.cbz").exists()


def test_windows_drive_member_and_xml_size_limit(tmp_path, monkeypatch):
    source = tmp_path / "source.cbz"
    with ZipFile(source, "w") as archive:
        archive.writestr("C:/page.txt", b"page")
    with pytest.raises(ValueError, match="unsafe"):
        core.plan_archive(source, {"Title": "x"})
    make_archive(source)
    monkeypatch.setattr(core, "MAX_XML_BYTES", 8)
    with pytest.raises(ValueError, match="metadata limit"):
        core.plan_archive(source, {"Title": "x"})
    assert not (tmp_path / "output.cbz").exists()


def test_strict_csv_quoting_and_cli_error(tmp_path, capsys):
    import csv

    from comicinfo_editor_lite.cli import main

    path = tmp_path / "bad.csv"
    path.write_text("source,output,Title" + chr(10) + '"source.cbz"junk,output.cbz,Title')
    with pytest.raises(csv.Error):
        core.load_batch(path)
    assert main(["--batch", str(path), "--dry-run"]) == 2
    assert "error:" in capsys.readouterr().err


def test_csv_field_limit_is_actionable(tmp_path, capsys):
    import csv

    from comicinfo_editor_lite.cli import main

    path = tmp_path / "large.csv"
    path.write_text("source,output,Title" + chr(10) + "a.cbz,b.cbz," + "x" * 100)
    previous = csv.field_size_limit(64)
    try:
        assert main(["--batch", str(path), "--dry-run"]) == 2
        assert "field larger" in capsys.readouterr().err
    finally:
        csv.field_size_limit(previous)


def test_valid_csv_quoted_commas_and_multiline_preserved(tmp_path):
    import csv

    path = tmp_path / "valid.csv"
    value = "A, title" + chr(10) + "second line"
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["source", "output", "Title"])
        writer.writerow(["source.cbz", "output.cbz", value])
    jobs = core.load_batch(path)
    assert jobs[0]["patch"]["Title"] == value
