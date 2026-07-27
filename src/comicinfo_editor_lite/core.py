from __future__ import annotations

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


def edit_archive(source: Path, output: Path, patch: dict[str, str | int | None]) -> dict[str, Any]:
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
        os.replace(temporary, output)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    return {
        "version": 1,
        "source": str(source),
        "output": str(output),
        "updated_fields": sorted(patch),
        "preserved_members": len(original_hashes),
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }
