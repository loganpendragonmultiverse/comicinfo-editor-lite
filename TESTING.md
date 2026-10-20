# Testing

Run `python -m pip install -e ".[dev]"`, then `ruff format --check .`, `ruff check .`, `mypy src`, `pytest`, `python -m pip_audit`, and `python -m build`.

Tests cover metadata creation, modification, removal and preservation; page-byte hashes; unsafe and duplicate archive paths; malformed XML; dry-run diffs; JSON and CSV batches; templates; recursive discovery; partial batch failures; temporary cleanup; replacement safety; and CLI exit behavior.

## 1.2.0: Edit preconditions

Optional preconditions prevent applying a patch to an unexpected source. `--expected-sha256` accepts a full archive SHA-256; `--expected-fields examples/expected-fields.json` reads an object of supported field names and exact old XML text values. A null expected value requires an absent field; an empty string requires a present empty field. Numeric XML values are compared as strings. Checks run for both planning and writes before creating output directories or archives. JSON batch jobs accept `expected_sha256` and `expected_fields`; CSV supports the same columns, with JSON text in expected_fields. Each failed job remains isolated. Single-archive flags are refused in batch/directory modes to avoid silently ignoring them. Keep source files stable during editing; the source hash is checked again before output placement. Unknown XML elements and page bytes remain preserved.

```bash
comicinfo-edit issue.cbz examples/metadata.json --dry-run --expected-fields examples/expected-fields.json
```

The supplied `examples/expected-fields.json` requires an absent Title. Replace its
values with the old values you intend to check before using it with your archive.

## 1.2.1 preservation contract

Patched XML fields must be unambiguous: duplicate occurrences are refused in plans
and writes, including removals. Direct Python entry points validate patches too.
CSV manifests require unique supported headers and rows of matching width; JSON
jobs must be objects. Invalid individual jobs and unsupported/encrypted/corrupt
archives are reported separately so later independent jobs can finish.

Archive fingerprints and page copies are streamed. XML metadata loads in
memory with a separate 16 MiB limit; the declared expanded-archive budget remains 2 GiB. Keep sources
stable; preconditions are checked before creating output directories and the
source hash is checked again before publication.

Outputs use owned unique temporary files and exclusive hard-link publication.
Existing files and symbolic links, including dangling links, are refused; an
output created while the archive is being edited is preserved. The destination
filesystem must support hard links; otherwise the write fails without replacing
the destination. This handles accidental collisions, not a hostile concurrent
filesystem. Temporary files owned by a failed job are removed; unrelated files
are preserved.

Both packages install the four authority documents and examples beneath
share/doc/comicinfo-editor-lite in the installation prefix.

Installed acceptance must run the full unchanged coverage gate against separate
fresh wheel and source-package installs outside the checkout. Check import
provenance, all installed document/example bytes, real single/batch/dry-run CLI,
source/page preservation and exclusive output placement. Repeat against the
exact successful tag-workflow artifacts before public release.

CSV quoting is strict; malformed quoting and oversized fields produce actionable CLI errors. Valid quoted commas and multiline field text remain supported.
