import hashlib
import json
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest
from test_core_cli import archive

from comicinfo_editor_lite.cli import main
from comicinfo_editor_lite.core import edit_archive, load_batch, plan_archive, run_batch


def test_hash_and_old_fields_fail_before_output(tmp_path):
    source = tmp_path / "one.cbz"
    archive(
        source, b"<ComicInfo><Title/><Series>Old</Series><Unknown x='1'>Keep</Unknown></ComicInfo>"
    )
    before = source.read_bytes()
    output = tmp_path / "new" / "out.cbz"
    for conditions in (
        {"expected_sha256": "0" * 64},
        {"expected_fields": {"Title": None}},
        {"expected_fields": {"Writer": ""}},
        {"expected_fields": {"Series": "New"}},
    ):
        with pytest.raises(ValueError, match="precondition mismatch"):
            edit_archive(source, output, {"Series": None}, **conditions)
        assert not output.parent.exists()
    digest = hashlib.sha256(before).hexdigest()
    plan = plan_archive(
        source,
        {"Series": None},
        expected_sha256=digest.upper(),
        expected_fields={"Title": "", "Writer": None, "Series": "Old"},
    )
    assert plan["changes"][0]["action"] == "remove"
    edit_archive(
        source, output, {"Series": None}, expected_sha256=digest, expected_fields={"Series": "Old"}
    )
    with ZipFile(output) as target:
        assert target.read("001.jpg") == b"page-one"
        xml = ElementTree.fromstring(target.read("ComicInfo.xml"))
        assert xml.find("Series") is None
        assert xml.find("Unknown").attrib == {"x": "1"}
        assert xml.findtext("Unknown") == "Keep"
    assert source.read_bytes() == before


@pytest.mark.parametrize(
    "conditions",
    [
        {"expected_sha256": "x"},
        {"expected_fields": []},
        {"expected_fields": {"Title": 3}},
        {"expected_fields": {"Unknown": None}},
    ],
)
def test_bad_preconditions(tmp_path, conditions):
    source = tmp_path / "one.cbz"
    archive(source)
    with pytest.raises((ValueError, TypeError)):
        plan_archive(source, {"Title": "X"}, **conditions)


def test_batch_isolation_json_csv_and_cli(tmp_path, capsys):
    source = tmp_path / "one.cbz"
    archive(source)
    jobs = [
        {
            "source": str(source),
            "output": str(tmp_path / "bad" / "out.cbz"),
            "patch": {"Title": "X"},
            "expected_sha256": "0" * 64,
        },
        {
            "source": str(source),
            "output": str(tmp_path / "good.cbz"),
            "patch": {"Title": "X"},
            "expected_fields": {"Title": None},
        },
    ]
    manifest = tmp_path / "jobs.json"
    manifest.write_text(json.dumps({"jobs": jobs}))
    dry = run_batch(load_batch(manifest), dry_run=True)
    assert dry["succeeded"] == dry["failed"] == 1
    report = run_batch(load_batch(manifest))
    assert report["succeeded"] == report["failed"] == 1
    assert not (tmp_path / "bad").exists()
    patch = tmp_path / "patch.json"
    patch.write_text('{"Title":"X"}')
    fields = tmp_path / "fields.json"
    fields.write_text('{"Title":null}')
    assert main([str(source), str(patch), "--dry-run", "--expected-fields", str(fields)]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"]
    assert (
        main(
            [
                str(source),
                str(patch),
                "--output",
                str(tmp_path / "cli.cbz"),
                "--expected-sha256",
                "0" * 64,
            ]
        )
        == 1
    )
    assert not (tmp_path / "cli.cbz").exists()
    assert main(["--batch", str(manifest), "--expected-sha256", "0" * 64]) == 2
    import csv

    csv_path = tmp_path / "jobs.csv"
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["source", "output", "Title", "expected_sha256", "expected_fields"]
        )
        writer.writeheader()
        writer.writerow(
            {
                "source": str(source),
                "output": str(tmp_path / "csv.cbz"),
                "Title": "X",
                "expected_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "expected_fields": '{"Title":null}',
            }
        )
    assert run_batch(load_batch(csv_path))["all_succeeded"]


def test_ambiguous_old_field_is_refused(tmp_path):
    source = tmp_path / "one.cbz"
    archive(source, b"<ComicInfo><Title>First</Title><Title>Last</Title></ComicInfo>")
    with pytest.raises(ValueError, match="ambiguous old field"):
        edit_archive(
            source, tmp_path / "new" / "out.cbz", {"Title": "X"}, expected_fields={"Title": "Last"}
        )
    assert not (tmp_path / "new").exists()
