from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from .core import edit_archive, load_patch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write focused ComicInfo metadata to a new CBZ.")
    parser.add_argument("archive", type=Path)
    parser.add_argument("metadata", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = edit_archive(args.archive, args.output, load_patch(args.metadata))
        sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    except (
        OSError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        zipfile.BadZipFile,
        ElementTree.ParseError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0
