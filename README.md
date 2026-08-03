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
