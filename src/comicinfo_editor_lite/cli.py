from __future__ import annotations

import argparse
import csv
import json
import lzma
import sys
import zipfile
import zlib
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from .core import directory_batch, load_batch, load_patch, plan_archive, run_batch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Plan or write focused ComicInfo metadata changes."
    )
    parser.add_argument("archive", nargs="?", type=Path)
    parser.add_argument("metadata", nargs="?", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch", type=Path, help="JSON or CSV batch manifest")
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--template", type=Path, help="reusable JSON metadata patch")
    parser.add_argument("--expected-sha256")
    parser.add_argument(
        "--expected-fields", type=Path, help="JSON object of old values; null means absent"
    )
    args = parser.parse_args(argv)
    try:
        if (args.batch or args.source_dir or args.output_dir) and (
            args.expected_sha256 is not None or args.expected_fields is not None
        ):
            raise ValueError(
                "use per-job preconditions in batch manifests; single-archive flags require an archive"
            )
        conditions: dict[str, Any] = {
            "expected_sha256": args.expected_sha256,
            "expected_fields": json.loads(args.expected_fields.read_text(encoding="utf-8"))
            if args.expected_fields
            else None,
        }
        template = load_patch(args.template) if args.template else None
        if args.batch:
            jobs = load_batch(args.batch)
            report = run_batch(jobs, template, args.dry_run)
        elif args.source_dir or args.output_dir:
            if not args.source_dir or not args.output_dir or template is None:
                raise ValueError(
                    "directory mode requires --source-dir, --output-dir, and --template"
                )
            report = run_batch(
                directory_batch(args.source_dir, args.output_dir, template, args.recursive),
                dry_run=args.dry_run,
            )
        elif args.archive and args.metadata:
            patch = load_patch(args.metadata)
            if args.dry_run:
                report = plan_archive(args.archive, patch, **conditions)
            else:
                if not args.output:
                    raise ValueError("single-archive write mode requires --output")
                report = run_batch(
                    [
                        {
                            "source": str(args.archive),
                            "output": str(args.output),
                            "patch": patch,
                            **conditions,
                        }
                    ]
                )
        else:
            raise ValueError("provide an archive and patch, --batch, or directory mode")
        sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    except (
        csv.Error,
        OSError,
        RuntimeError,
        NotImplementedError,
        EOFError,
        zlib.error,
        lzma.LZMAError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        zipfile.BadZipFile,
        ElementTree.ParseError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 1 if isinstance(report, dict) and report.get("failed", 0) else 0
