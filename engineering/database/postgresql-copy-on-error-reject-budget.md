# PostgreSQL COPY ON_ERROR reject budgets

**Issue:** Bulk imports either abort on one malformed value or silently discard an unlimited amount of bad input when error tolerance is left unbounded.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

On supported versions, use `COPY FROM ... ON_ERROR ignore` only with an explicit positive `REJECT_LIMIT` derived from the ingestion contract. Choose `LOG_VERBOSITY` deliberately: verbose is useful for controlled diagnosis but may expose row content in logs; silent reduces disclosure but requires independent reject accounting. Stage high-risk feeds, reconcile source rows against inserted and rejected totals, and retain a quarantined source object rather than inventing corrected data.

## Verification

Test a clean file, a file at the reject limit, and one exceeding it. Verify transaction behavior, row counts, alerting, and that logs do not contain prohibited fields. Pin guidance to the deployed PostgreSQL major version.

## Gotchas

- Confirm behavior against the exact deployed version; feature state and defaults can change.
- Preserve logs and artifacts needed to reproduce failures without recording secrets or personal data.
- Roll out behind a reversible change and define the rollback trigger before production use.

## Official source

- [Primary documentation](https://www.postgresql.org/docs/current/sql-copy.html)
