# ComicInfo.xml Editor Lite

[![CI](https://github.com/loganpendragonmultiverse/comicinfo-editor-lite/actions/workflows/ci.yml/badge.svg)](https://github.com/loganpendragonmultiverse/comicinfo-editor-lite/actions/workflows/ci.yml)

ComicInfo.xml Editor Lite applies a focused JSON metadata patch to a CBZ archive and writes a separate validated CBZ. Page bytes remain unchanged, existing unknown ComicInfo elements are retained, removed fields are explicit, and the source archive is never rewritten.

## Three-minute start

```bash
python -m pip install .
comicinfo-edit issue.cbz examples/metadata.json --output issue-metadata.cbz
```

Supported fields are Title, Series, Number, Volume, Summary, Writer, Penciller, Publisher, Year, Month, PageCount, and LanguageISO. A JSON `null` removes that element. The editor validates archive paths, duplicate members, entry and uncompressed-size limits, the XML document, unchanged non-metadata hashes, and the completed output archive.

Only ZIP-based CBZ archives are supported. The tool does not edit CBR or CB7, fetch metadata, modify page images, normalize every ComicInfo schema field, or replace an existing output. Keep backups of valuable archives. Requires Python 3.10 or newer.

Part of the [Logan Pendragon Forge open-source collection](https://www.loganpendragonforge.com/open-source/). Licensed under the [MIT License](LICENSE).
