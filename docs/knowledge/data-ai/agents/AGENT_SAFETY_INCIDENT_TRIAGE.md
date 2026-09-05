---
title: Agent Safety Incident Triage
owner: ORCHORDS AI Governance
status: active
classification: internal
last-reviewed: 2026-09-05
review-cycle: semiannual
next-review: 2027-03-05
source: NIST AI 600-1 §3.4 (Incident Response); OECD AI Incident Database (AIID) — reporting schema; ISO/IEC 27035-1:2023 Incident Management; MITRE ATLAS Tactics TA0008/TA0009 (Adversarial ML Incidents)
---

## Scope

Defines the triage procedure used when an ORCHORDS agent emits disallowed content, executes a disallowed action, leaks configuration, or otherwise breaches a published safety claim. The objective is to contain, characterise, and remediate without prematurely discarding evidence. The procedure distinguishes near-miss, single-user, multi-user, and broad-impact severities, and routes each to the right responder roster.

## Plan

1. Receive the signal: a user report, an automated classifier trip, a probe failure, or a downstream artefact anomaly.
2. Quarantine the session and any transcripts in a write-once evidence locker. Do not delete — even suspected contamination requires preservation for forensic integrity.
3. Classify severity by likelihood and impact: was data exfiltrated? Was a regulated action completed? Was a benign hallucination the only outcome?
4. Decide between mitigation paths: revert to a known-good model version, swap a tool schema, disable a feature flag, add a probe, or escalate to the cross-functional incident response team.
5. Post-incident: write a brief, share the redaction strategy, and add the probe to the regression library so the same incident cannot re-emerge unnoticed.

## Inputs

- Incident intake channel (`safety@orchords`, internal form, automated ticket).
- Read-only transcript store and telemetry from `AGENT_DISTRIBUTED_TRACING_OTEL`.
- Agent version, configuration, and policy reference.
- Severity catalogue agreed with legal and security.

## ORCHORDS Profile

| Dimension | Target |
|-----------|--------|
| Triage latency | ≤ 5 min from signal to incident commander |
| Evidence preservation | write-once, ≥ 7 years retention |
| Mitigation latency (high) | ≤ 4 h to a known-good configuration |
| Mitigation latency (broad) | ≤ 1 h to a service-wide rollback |
| Postmortem SLA | ≤ 5 business days for severity ≥ 3 |

## Implementation Notes

- Do not require the reporter to have already disclosed the harmful content. The triage form must support "I observed a behaviour that I think was unsafe" without coercing reproduction of the output.
- The incident commander must be a named human. Paging an automated responder counts only if its chain of custody reaches a human reviewer within the same hour.
- Treat repeated near-misses with the same severity as single higher-severity events — frequency is itself a finding.
- Coordination with `AGENT_RED_TEAM_FINDING_TRIAGE` requires a triage-memory pass; the two streams often correlate.

## Companion Documents

- `AGENT_HUMAN_IN_THE_LOOP_GATING.md` — pre-emptive gate that may have failed.
- `AGENT_ADVERSARIAL_ROBUSTNESS_PROBE.md` — related probe failure pathway.
- `INCIDENT_TIMELINE_RECONSTRUCTION.md` (playbooks) — broader incident timeline.
