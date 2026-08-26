# CI matrix rows need evidence owners

**Lesson:** A matrix dimension without an owner, expected artifact, and failure policy becomes decorative coverage that nobody notices when it stops running.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Operationalization

For every row record target, risk, owner, cadence, timeout, artifacts, retention, and escalation; review changes like production interfaces.

## Verification

Delete, rename, and force-fail each row; confirm dashboards and owners detect the missing evidence.

## Gotchas

Matrix expansion can dilute attention while increasing cost; count verified properties, not YAML combinations.

## Official sources

- https://docs.github.com/en/actions/using-jobs/using-a-matrix-for-your-jobs
