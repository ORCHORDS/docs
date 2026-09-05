---
title: "Agent Bias Fairness Probing"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# Agent Bias Fairness Probing

## Scope

Defines how ORCHORDS agents probe, measure, and remediate bias and fairness regressions across model revisions, retrieval snapshots, and prompt revisions, so that protected attributes do not produce discriminatory outcomes.

## Identifier table

| Field | Value |
|---|---|
| Topic | Bias and fairness probing for agent behavior |
| Inputs | Probe dataset, agent revision, fairness rubric, model card |
| Outputs | Bias report, remediation actions, attestation |
| Audience | AI Platform, AIMS governance, Service Owners |
| Trigger | Model change, prompt change, quarterly review, regression finding |
| Companion | AGENT_EVALUATION_PATTERNS.md, AGENT_RED_TEAM_FINDING_TRIAGE.md |

## Plan

1. Maintain a documented probe dataset with representative queries across protected attributes defined by the applicable jurisdictions.
2. Run the probe dataset against the current agent revision in a controlled environment; record inputs, retrieved context, model outputs, and tool calls.
3. Compute fairness metrics for each protected attribute group: disparate impact ratio, equal opportunity difference, calibration gap, and any custom metric relevant to the use case.
4. Compare results against documented acceptance thresholds; flag any group with results outside threshold.
5. Open remediation tickets for any flagged group, with owner and deadline, and link to the risk register.
6. Validate that the bias probing covers not only the model but also retrieval and post-processing, since bias can enter at any layer.
7. Publish the bias report alongside the model card so consumers can read the current fairness posture.

## Inputs

- Probe dataset with documented attribute coverage
- Agent revision identifiers
- Fairness rubric with thresholds

## ORCHORDS Profile

| Metric | Threshold |
|---|---|
| Disparate impact ratio | At least 0.80 between any two groups |
| Equal opportunity difference | At most 0.10 in absolute value |
| Calibration gap | At most 0.05 in absolute value |
| Probe dataset size | At least 1,000 items per protected attribute |
| Re-run cadence | On every model or prompt revision; quarterly otherwise |

## Implementation Notes

- Treat probe datasets as evaluation data; apply the same leakage prevention controls.
- When remediation is incomplete, document the residual risk and the compensating control in the model card.

## Companion Documents

- AGENT_EVALUATION_PATTERNS.md
- AGENT_RED_TEAM_FINDING_TRIAGE.md
- AGENT_EVAL_LEAKAGE_PREVENTION.md
