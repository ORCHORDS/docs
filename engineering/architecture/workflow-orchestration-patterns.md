# workflow-orchestration-patterns

**Issue:** Multi-step async processes fail silently mid-execution with no retry or state tracking
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A document processing pipeline of five steps fails at step three. There is no record of which documents completed which steps, and reprocessing reruns all five steps unnecessarily.

## Pattern / Solution
Use a workflow orchestration engine (Temporal, Airflow, Step Functions) to track step state durably. Define workflows as code. The orchestrator handles retries, timeouts, and compensation. Each step is idempotent.

## Gotchas
Workflow engines add operational overhead. Temporal requires its own cluster. Avoid encoding business logic in the orchestration layer and keep it thin with logic in activities.

## Related
saga-pattern-orchestration, data-pipeline-architecture, event-driven-architecture
