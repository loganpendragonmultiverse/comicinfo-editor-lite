from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
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
    args = parser.parse_args(argv)
    try:
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
                report = plan_archive(args.archive, patch)
            else:
                if not args.output:
                    raise ValueError("single-archive write mode requires --output")
                report = run_batch(
                    [{"source": str(args.archive), "output": str(args.output), "patch": patch}]
                )
        else:
            raise ValueError("provide an archive and patch, --batch, or directory mode")
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
    return 1 if isinstance(report, dict) and report.get("failed", 0) else 0
