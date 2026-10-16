# Changelog

## 1.2.0 - 2026-10-16

- Added optional archive SHA-256 and exact old-field-value preconditions for single and batch editing.
- Added synthetic regression fixtures for failure isolation and output preservation.


## 1.1.0 - 2026-08-03

- Added dry-run before/after metadata plans with explicit set, remove, and unchanged actions.
- Added JSON and CSV batch manifests, reusable JSON templates, and recursive CBZ directory discovery.
- Added per-job success and failure reports, source and output fingerprints, field-level change evidence, and transactional write status.
- Preserved source archives and validated temporary outputs before atomic placement.

## 1.0.0 - 2026-07-26

- Added focused ComicInfo.xml field updates and removals.
- Added source-preserving CBZ output with archive-path and size limits.
- Added post-write XML, archive, and unchanged-member verification.
