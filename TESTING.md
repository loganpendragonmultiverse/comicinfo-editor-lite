# Testing

Run `python -m pip install -e ".[dev]"`, then `ruff format --check .`, `ruff check .`, `mypy src`, `pytest`, `python -m pip_audit`, and `python -m build`.

Tests cover metadata creation, modification, removal and preservation; page-byte hashes; unsafe and duplicate archive paths; malformed XML; dry-run diffs; JSON and CSV batches; templates; recursive discovery; partial batch failures; temporary cleanup; replacement safety; and CLI exit behavior.
