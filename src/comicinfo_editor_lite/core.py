from __future__ import annotations

import csv
import hashlib
import json
import os
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, cast
from xml.etree import ElementTree

FIELDS = {
    "Title",
    "Series",
    "Number",
    "Volume",
    "Summary",
    "Writer",
    "Penciller",
    "Publisher",
    "Year",
    "Month",
    "PageCount",
    "LanguageISO",
}
INTEGER_FIELDS = {"Volume", "Year", "Month", "PageCount"}
MAX_ENTRIES = 10_000
MAX_UNCOMPRESSED = 2 * 1024 * 1024 * 1024


def load_patch(path: Path) -> dict[str, str | int | None]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return load_patch_data(data)


def _validate_infos(infos: list[zipfile.ZipInfo]) -> None:
    if len(infos) > MAX_ENTRIES:
        raise ValueError("archive exceeds the entry limit")
    if sum(info.file_size for info in infos) > MAX_UNCOMPRESSED:
        raise ValueError("archive exceeds the uncompressed-size limit")
    seen: set[str] = set()
    for info in infos:
        path = PurePosixPath(info.filename.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError(f"unsafe archive member path: {info.filename}")
        key = path.as_posix().casefold()
        if key in seen:
            raise ValueError(f"duplicate archive member path: {info.filename}")
        seen.add(key)


def _xml(existing: bytes | None, patch: dict[str, str | int | None]) -> bytes:
    if existing is None:
        root = ElementTree.Element("ComicInfo")
    else:
        root = ElementTree.fromstring(existing)
        if root.tag != "ComicInfo":
            raise ValueError("ComicInfo.xml root must be ComicInfo")
    for field, value in patch.items():
        element = root.find(field)
        if value is None:
            if element is not None:
                root.remove(element)
            continue
        if element is None:
            element = ElementTree.SubElement(root, field)
        element.text = str(value)
    return cast(bytes, ElementTree.tostring(root, encoding="utf-8", xml_declaration=True))


def _metadata(source: Path) -> tuple[dict[str, str], list[zipfile.ZipInfo], bytes | None]:
    with zipfile.ZipFile(source, "r") as archive:
        infos = archive.infolist()
        _validate_infos(infos)
        metadata_infos = [
            info
            for info in infos
            if PurePosixPath(info.filename).name.casefold() == "comicinfo.xml"
        ]
        if len(metadata_infos) > 1:
            raise ValueError("archive contains multiple ComicInfo.xml files")
        existing = archive.read(metadata_infos[0]) if metadata_infos else None
    if existing is None:
        return {}, infos, None
    root = ElementTree.fromstring(existing)
    if root.tag != "ComicInfo":
        raise ValueError("ComicInfo.xml root must be ComicInfo")
    return {child.tag: child.text or "" for child in root}, infos, existing


def plan_archive(
    source: Path,
    patch: dict[str, str | int | None],
    *,
    expected_sha256: str | None = None,
    expected_fields: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    source = source.resolve()
    if not source.is_file() or source.suffix.casefold() not in {".cbz", ".zip"}:
        raise ValueError("source must be a CBZ or ZIP file")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if expected_sha256 is not None:
        if (
            not isinstance(expected_sha256, str)
            or len(expected_sha256) != 64
            or any(c not in "0123456789abcdefABCDEF" for c in expected_sha256)
        ):
            raise ValueError("expected_sha256 must be a 64-character SHA-256 hex digest")
        if source_hash != expected_sha256.lower():
            raise ValueError("archive SHA-256 precondition mismatch")
    current, infos, _existing = _metadata(source)
    if expected_fields is not None:
        if not isinstance(expected_fields, dict):
            raise TypeError("expected_fields must be an object")
        for field, expected in expected_fields.items():
            if field not in FIELDS or (expected is not None and not isinstance(expected, str)):
                raise ValueError("expected_fields values must be text or null for supported fields")
            if _existing is not None and len(ElementTree.fromstring(_existing).findall(field)) > 1:
                raise ValueError(f"ambiguous old field precondition: {field}")
            if current.get(field) != expected:
                raise ValueError(f"old field precondition mismatch: {field}")
    if hashlib.sha256(source.read_bytes()).hexdigest() != source_hash:
        raise ValueError("source changed while checking preconditions")
    changes: list[dict[str, Any]] = []
    for field, value in sorted(patch.items()):
        before = current.get(field)
        after = None if value is None else str(value)
        action = (
            "remove"
            if value is None and before is not None
            else "set"
            if after != before
            else "unchanged"
        )
        if value is None and before is None:
            action = "unchanged"
        changes.append({"field": field, "before": before, "after": after, "action": action})
    return {
        "source": str(source),
        "source_sha256": source_hash,
        "member_count": len(infos),
        "changes": changes,
        "changed_fields": [item["field"] for item in changes if item["action"] != "unchanged"],
        "dry_run": True,
    }


def load_batch(path: Path) -> list[dict[str, Any]]:
    if path.suffix.casefold() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        jobs: list[dict[str, Any]] = []
        for row in rows:
            if not row.get("source") or not row.get("output"):
                raise ValueError("each CSV row requires source and output")
            patch: dict[str, str | int | None] = {}
            for field in FIELDS:
                raw = row.get(field, "")
                if raw == "":
                    continue
                if raw == "__REMOVE__":
                    patch[field] = None
                elif field in INTEGER_FIELDS:
                    patch[field] = int(raw)
                else:
                    patch[field] = raw
            job: dict[str, Any] = {"source": row["source"], "output": row["output"], "patch": patch}
            if row.get("expected_sha256"):
                job["expected_sha256"] = row["expected_sha256"]
            if row.get("expected_fields"):
                job["expected_fields"] = json.loads(row["expected_fields"])
            jobs.append(job)
        return jobs
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(raw_jobs, list) or not raw_jobs:
        raise ValueError("batch JSON must contain a non-empty jobs array")
    return [dict(item) for item in raw_jobs]


def directory_batch(
    source_dir: Path, output_dir: Path, patch: dict[str, str | int | None], recursive: bool
) -> list[dict[str, Any]]:
    source_dir, output_dir = source_dir.resolve(), output_dir.resolve()
    if not source_dir.is_dir():
        raise ValueError("source directory does not exist")
    iterator = source_dir.rglob("*") if recursive else source_dir.glob("*")
    sources = [
        path for path in sorted(iterator) if path.is_file() and path.suffix.casefold() == ".cbz"
    ]
    if not sources:
        raise ValueError("source directory contains no CBZ archives")
    return [
        {
            "source": str(source),
            "output": str(output_dir / source.relative_to(source_dir)),
            "patch": patch,
        }
        for source in sources
    ]


def edit_archive(
    source: Path,
    output: Path,
    patch: dict[str, str | int | None],
    *,
    expected_sha256: str | None = None,
    expected_fields: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    source = source.resolve()
    output = output.resolve()
    if source == output:
        raise ValueError("output must differ from source")
    if output.exists():
        raise ValueError("output already exists")
    if not source.is_file() or source.suffix.casefold() not in {".cbz", ".zip"}:
        raise ValueError("source must be a CBZ or ZIP file")
    temporary = output.with_name(f".{output.name}.tmp")
    if temporary.exists():
        raise ValueError("temporary output already exists")
    original_hashes: dict[str, str] = {}
    plan = plan_archive(
        source, patch, expected_sha256=expected_sha256, expected_fields=expected_fields
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(source, "r") as archive:
            infos = archive.infolist()
            _validate_infos(infos)
            metadata_infos = [
                info
                for info in infos
                if PurePosixPath(info.filename).name.casefold() == "comicinfo.xml"
            ]
            if len(metadata_infos) > 1:
                raise ValueError("archive contains multiple ComicInfo.xml files")
            existing = archive.read(metadata_infos[0]) if metadata_infos else None
            updated_xml = _xml(existing, patch)
            with zipfile.ZipFile(temporary, "w") as target:
                for info in infos:
                    if metadata_infos and info.filename == metadata_infos[0].filename:
                        continue
                    content = archive.read(info)
                    original_hashes[info.filename] = hashlib.sha256(content).hexdigest()
                    target.writestr(info, content)
                target.writestr("ComicInfo.xml", updated_xml, compress_type=zipfile.ZIP_DEFLATED)
        with zipfile.ZipFile(temporary, "r") as completed:
            _validate_infos(completed.infolist())
            if completed.testzip() is not None:
                raise ValueError("completed archive failed CRC validation")
            ElementTree.fromstring(completed.read("ComicInfo.xml"))
            for name, expected in original_hashes.items():
                if hashlib.sha256(completed.read(name)).hexdigest() != expected:
                    raise ValueError(f"member changed unexpectedly: {name}")
        if hashlib.sha256(source.read_bytes()).hexdigest() != plan["source_sha256"]:
            raise ValueError("source changed during edit")
        os.replace(temporary, output)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    return {
        "version": 2,
        "source": str(source),
        "output": str(output),
        "updated_fields": sorted(patch),
        "changes": plan["changes"],
        "preserved_members": len(original_hashes),
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "transaction": "temporary output validated before atomic replacement",
        "rollback_required": False,
    }


def run_batch(
    jobs: list[dict[str, Any]],
    template: dict[str, str | int | None] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not jobs:
        raise ValueError("batch requires at least one job")
    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for index, job in enumerate(jobs, 1):
        try:
            source = Path(str(job["source"]))
            patch_raw = {**(template or {}), **dict(job.get("patch", {}))}
            patch = load_patch_data(patch_raw)
            conditions: dict[str, Any] = {
                "expected_sha256": job.get("expected_sha256"),
                "expected_fields": job.get("expected_fields"),
            }
            if dry_run:
                result = plan_archive(source, patch, **conditions)
                result["output"] = (
                    str(Path(str(job.get("output", ""))).resolve()) if job.get("output") else None
                )
            else:
                if not job.get("output"):
                    raise ValueError("each write job requires output")
                result = edit_archive(source, Path(str(job["output"])), patch, **conditions)
            result["job"] = index
            results.append(result)
        except (OSError, TypeError, ValueError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
            failures.append(
                {"job": str(index), "source": str(job.get("source", "")), "error": str(exc)}
            )
    return {
        "schema_version": 2,
        "dry_run": dry_run,
        "jobs": len(jobs),
        "succeeded": len(results),
        "failed": len(failures),
        "results": results,
        "failures": failures,
        "all_succeeded": not failures,
    }


def load_patch_data(data: dict[str, Any]) -> dict[str, str | int | None]:
    if not isinstance(data, dict) or not data:
        raise TypeError("metadata patch must be a non-empty object")
    result: dict[str, str | int | None] = {}
    for field, value in data.items():
        if field not in FIELDS:
            raise ValueError(f"unsupported ComicInfo field: {field}")
        if value is None:
            result[field] = None
        elif field in INTEGER_FIELDS:
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise TypeError(f"field {field} must be a non-negative integer or null")
            result[field] = value
        elif not isinstance(value, str):
            raise TypeError(f"field {field} must be text or null")
        else:
            result[field] = value
    return result
