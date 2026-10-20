# ComicInfo.xml Editor Lite

[![CI](https://github.com/loganpendragonmultiverse/comicinfo-editor-lite/actions/workflows/ci.yml/badge.svg)](https://github.com/loganpendragonmultiverse/comicinfo-editor-lite/actions/workflows/ci.yml)

Plan or apply focused ComicInfo.xml metadata changes while preserving comic page bytes. Version 1.1 supports single archives, dry-run field diffs, JSON or CSV batch manifests, reusable JSON templates, recursive CBZ discovery, per-archive results, and transaction evidence. Writes always create separate validated CBZ archives.

## Three-minute start

```bash
python -m pip install .
comicinfo-edit issue.cbz examples/metadata.json --dry-run
comicinfo-edit issue.cbz examples/metadata.json --output issue-metadata.cbz
comicinfo-edit --batch examples/batch.csv --template examples/metadata.json --dry-run
comicinfo-edit --source-dir comics --output-dir updated --template examples/metadata.json --recursive
```

CSV batches require `source` and `output` columns and may include any supported ComicInfo field. Empty cells inherit the template or make no per-row change; `__REMOVE__` explicitly removes a field. JSON batches contain a `jobs` array with `source`, optional `output` for dry runs, and a `patch` object.

## Safety and evidence

Supported fields are Title, Series, Number, Volume, Summary, Writer, Penciller, Publisher, Year, Month, PageCount, and LanguageISO. JSON `null` removes an element. Dry runs report before, after, and set/remove/unchanged actions without writing an archive.

Every write validates archive paths, duplicate members, entry and uncompressed-size limits, XML, CRCs, unchanged non-metadata hashes, and the final output hash. A temporary archive is fully checked before atomic placement. Failed jobs remove their temporary output and appear separately in the batch report; successful jobs are not rolled back when another independent batch job fails.

## Limitations

Only ZIP-based CBZ archives are supported. The tool does not edit CBR or CB7, fetch metadata, modify images, normalize the full ComicInfo schema, infer issue numbers from filenames, overwrite sources or outputs, or make a multi-archive batch globally atomic. Keep backups of valuable archives. Python 3.10 or newer is required.

Part of the [Logan Pendragon Forge open-source collection](https://www.loganpendragonforge.com/open-source/). Licensed under the [MIT License](LICENSE).

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

CSV quoting is strict; malformed quoting and oversized fields produce actionable CLI errors. Valid quoted commas and multiline field text remain supported.
