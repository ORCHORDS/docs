# pytest temporary-path retention policy

**Issue**

Unbounded retained temporary directories fill runners, while deleting every failure artifact removes evidence.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Set `tmp_path_retention_count` and policy explicitly.
- Preserve only failed-session evidence within disk budgets.
- Upload approved diagnostics before host cleanup.

## Verification

1. Run passing, failing, interrupted, and retried sessions.
2. Verify oldest retained roots expire.
3. Exercise parallel workers and long paths.

## Gotchas

- Retention is per pytest policy, not archival.
- Artifacts may contain secrets.
- Host cleanup can race test processes.

## Official source

- [Official documentation](https://docs.pytest.org/en/stable/how-to/tmp_path.html)
