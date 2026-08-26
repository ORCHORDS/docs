# github-actions-python-ci

**Issue:** Standard Python CI pipeline with lint, type-check, and test steps
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Python projects need reproducible CI covering multiple interpreter versions with fast dependency caching.

## Pattern / Solution
```yaml
jobs:
  ci:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: mypy src/
      - run: pytest --tb=short
```
For `uv`-based projects:
```yaml
      - uses: astral-sh/setup-uv@v4
        with:
          version: "latest"
      - run: uv sync --all-extras
      - run: uv run pytest
```

## Gotchas
- Quote Python versions (`"3.11"`) — bare `3.11` parses as float `3.1` in YAML.
- `cache: pip` hashes `requirements*.txt`; switch to `cache-dependency-path` for `pyproject.toml`.
- `setup-python` with `uv` still works but `astral-sh/setup-uv` is faster.
- `PYTHONDONTWRITEBYTECODE=1` and `PYTHONUNBUFFERED=1` are useful env vars for CI.

## Related
- `github-actions-cache-dependencies.md`
- `github-actions-matrix-2026.md`
