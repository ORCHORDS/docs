---
title: Temporal Durable Execution Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-07
review-cycle: 180 days
next-review: 2027-03-06
source: https://temporal.io ; https://github.com/temporalio/temporal ; https://docs.temporal.io
---

# Temporal Durable Execution Version Governance

## 1. Purpose

This reference card governs the lifecycle of the Temporal durable-execution platform when used as an orchestration and reliability layer for microservices, AI agent workflows, and long-running business processes. It applies to self-hosted Temporal deployments, Temporal Cloud, and derivatives (such as Temporalite for development).

## 2. Scope

In scope:

- **Temporal Server** ≥ 1.24.x (UI, history, matching, frontend, worker services).
- **Namespace** topology and **Task Queues**.
- Persistence backends: Cassandra, MySQL/PostgreSQL ≥ 8.0, Elasticsearch ≥ 8.
- SDKs: Go, Java, Python, TypeScript, .NET — pinned per repo.
- Encryption: **payload-level AES-256-GCM** with KMS-managed keys, mTLS for inter-service traffic.

Out of scope:

- The legacy "Cadence" code path (Temporal forked from Cadence in 2020).
- Webhooks and third-party integrations other than Slack/Email.

## 3. Versioning policy

- Pin the Temporal Server image to a specific patch release (e.g. `temporalio/server:1.24.3`) and SHA-256 digest.
- Maintain **3 namespaces per environment** (development, staging, production) per business unit; namespaces are not shared across BUs.
- Always run with `dynamic-config.yaml` under version control; do not apply changes via the UI without recording the change in the config repo.
- Run server in **HA** mode with at least 3 hosts and a quorum-aware persistence store.

## 4. Compatibility matrix

| Temporal Server | Persistence | Go SDK | Java SDK | Python SDK | Notes |
| --- | --- | --- | --- | --- | --- |
| 1.22.x | Postgres ≥ 14 | ≥ 1.26 | ≥ 1.24 | ≥ 1.9 | Worker v2 protocol default |
| 1.23.x | Postgres ≥ 15 | ≥ 1.27 | ≥ 1.25 | ≥ 1.10 | Upsert workflow search attributes |
| 1.24.x | Postgres ≥ 15 | ≥ 1.28 | ≥ 1.26 | ≥ 1.11 | Per-namespace rate limits; priority queues |

## 5. Namespace and Task Queue design

- One Task Queue per workload class (e.g. `orders.fifo`, `billing.retry`).
- Use `WorkflowId` policies: `Partitioned` for throughput, `Unpartitioned` for ordering.
- Set `workflowExecutionTimeout` ≤ 24 hours by default; longer workflows must use ContinueAsNew.

## 6. Workflow versioning

- Use **workflow.getVersion** (per SDK) when changing non-deterministic workflow code.
- Tag workflow types with a `vN` semantic version; treat changes that alter control flow as **non-deterministic** and use versioning markers.
- Replay tests are mandatory for any change to a workflow type with active executions.

## 7. Upgrade procedure

1. Roll the Temporal Server image to the target version with `dynamic-config.yaml` pre-validated in staging.
2. Upgrade SDKs in worker code; release workers before server upgrades for compatibility.
3. Watch `temporal_workflow_start_failed_total` and `temporal_task_schedule_to_start_latency_seconds` for regressions.
4. Promote after 24 h of green metrics.

## 8. Rollback procedure

- `kubectl rollout undo deployment/temporal-server` reverts to the previous image; no data loss because the persistence store keeps history records.
- Workflows mid-execution replay against the previous server version automatically on the next event.

## 9. Observability

- Required metrics: `temporal_workflow_started_total{namespace}`, `temporal_workflow_completed_total{namespace}`, `temporal_task_schedule_to_start_latency_seconds{namespace,task_queue}`, `temporal_pending_activities{namespace}`.
- Alert on `rate(temporal_workflow_start_failed_total[5m]) > 0` and on `temporal_task_schedule_to_start_latency_seconds > 30` for sustained periods.

## 10. References

- Temporal documentation — https://docs.temporal.io
- Temporal release notes — https://github.com/temporalio/temporal/releases
- Versioning in Temporal — https://docs.temporal.io/workflows#versioning
