# data-pipeline-architecture

**Issue:** Data moves between systems through fragile, undocumented custom scripts
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
An ETL process fails silently, delivering incomplete data to a downstream analytics table without alerting anyone.

## Pattern / Solution
Use a dedicated orchestration tool such as Airflow, Prefect, or dbt to define pipelines as code. Instrument each step with success/failure metrics. Implement idempotent steps so reruns are safe. Validate output schema and row counts after each stage.

## Gotchas
Pipeline failures in the middle of a multi-step ETL can leave partial writes. Design for idempotency and atomicity at each step. Monitor pipeline freshness, not just success/failure.

## Related
lambda-architecture, kappa-architecture, workflow-orchestration-patterns
