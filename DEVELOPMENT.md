# Development contract

Plan and apply focused ComicInfo.xml patches into separate, validated CBZ archives without altering page bytes or source files.

Preserve explicit removal semantics, dry-run evidence, bounded archive handling, unknown XML fields, per-job batch isolation, validated temporary files, and output collision protection. Every feature release must update tests, version metadata, changelog, README claims, repository metadata, release assets, and the Forge catalog together.

## 1.2.0: Edit preconditions

Optional preconditions prevent applying a patch to an unexpected source. `--expected-sha256` accepts a full archive SHA-256; `--expected-fields examples/expected-fields.json` reads an object of supported field names and exact old XML text values. A null expected value requires an absent field; an empty string requires a present empty field. Numeric XML values are compared as strings. Checks run for both planning and writes before creating output directories or archives. JSON batch jobs accept `expected_sha256` and `expected_fields`; CSV supports the same columns, with JSON text in expected_fields. Each failed job remains isolated. Single-archive flags are refused in batch/directory modes to avoid silently ignoring them. Keep source files stable during editing; the source hash is checked again before output placement. Unknown XML elements and page bytes remain preserved.

```bash
comicinfo-edit issue.cbz examples/metadata.json --dry-run --expected-fields examples/expected-fields.json
```

The supplied `examples/expected-fields.json` requires an absent Title. Replace its
values with the old values you intend to check before using it with your archive.
