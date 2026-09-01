# Network Packet Loss Support Triage

## Purpose and scope

This runbook handles **Network Packet Loss Support Triage**. Intake records source, destination, direction, interface, transport, start time, loss method and percentage, latency, jitter, VPN, geography, and application symptom. Support separates observations from telemetry, timestamps evidence, minimizes sensitive collection, and confirms business impact. It does not authorize policy bypass, unsafe investigation, legal conclusions, or guarantees of recovery.

## Intake and diagnosis

Capture source, destination, protocol, time, path, medium, sample, latency, jitter and counters. Establish whether one user, tenant, version, location, protocol, or the wider service is affected. Request the narrowest artifact answering a defined question; prefer identifiers, structured events, and redacted output over bulk payloads. Check incidents, maintenance, and recent changes before disruptive tests.

Build a timeline from first observation through the latest attempt and identify each clock. Compare the failure with a nearby successful control. Reproduce only with approved synthetic data in a supported environment. Never alter production merely to observe the symptom or ask a reporter to bypass protection. Record environmental assumptions, because an apparently identical test from another network or tool may exercise a different path.

## Operational workflow

The exact sequence is to define endpoints, check interface errors, drops, signal, duplex, utilization and queues, compare bidirectional and control tests, run bounded probes, correlate routes and provider telemetry, then retest identically. Make one authorized reversible change at a time with an expected result, stop condition, and rollback. Verify the original operation and a nearby control; task acceptance alone is not recovery evidence.

After correction, repeat the original operation and a non-failing control. Validate the business result, not only a green response. Remove test objects, debug settings, exceptions, temporary access, and elevated privilege. Route durable correction to the owning backlog with impact and reproduction. Communication must state facts, uncertainty, effect, safe action, checkpoint, and decision owner.

Where several systems participate, identify the boundary at which observed behavior changes. Correlation IDs and synchronized timestamps should connect each layer without collecting full content. Do not apply a broad configuration relaxation to prove that one narrow control caused the problem; use a controlled test path or owner-approved temporary diagnostic instead.

## Controls and evidence

Retain intake parameters, original error, correlation IDs, relevant configuration, diagnostic output, approvals, changes and results, rollback status, and before-and-after validation. Use approved systems and content-appropriate access. Do not copy secrets, payloads, or unrelated personal information into ordinary notes. Existing schedules apply.

Validation must be repeatable. Use least privilege and separate approval from execution for destructive or broad actions. Automation identifies actor, target, time, action, result, and correlation ID. For sampling, record population, method, exclusions, and limitations. Exercise success, partial failure, contradictory telemetry, after-hours ownership, and failed rollback. Trend recurrence and workaround age.

Quality review should confirm that raw observations remain available, diagnostic conclusions cite those observations, and the tested path matches the affected path. A dashboard summary is useful for detection but cannot substitute for protocol- or object-level evidence when deciding cause. Document monitoring gaps as control gaps rather than treating silence as successful operation.

## Failure handling

Stop and escalate for misleading ICMP, one-sided evidence, sensitive capture, or widespread impact. Preserve conflicting observations rather than choosing the convenient one. Increased privilege, scope, exposure, cost, or irreversibility requires owner approval. Stop retries that can duplicate work, worsen saturation, overwrite state, or hide the first error.

If no safe workaround exists, preserve state and use only owner-approved continuity options. A failed rollback, unintended change, wrong target, or bypass is a new incident. State residual uncertainty; never assert safety, completeness, compliance, or absence of compromise from one test. If another organization controls the failing dependency, provide reproducible timestamps and identifiers, track acknowledgement, and avoid presenting an unconfirmed external cause as fact.

## Closure validation

Confirm the original symptom no longer occurs under recorded conditions, the adjacent control works, logs show the intended target, temporary measures are removed or owned, residual limits are documented, and recurrence will produce useful telemetry. Review both directions or both ends where applicable. Keep every unknown visible as an assigned exception.


## Escalation, recovery validation, and failure handling

Escalate for cross-tenant or widespread impact, unclear authority, suspected compromise or exposure, safety concerns, irreversible action, failed rollback, or residual risk outside the service owner’s delegation. Provide identifiers, timeline, evidence locations, containment, attempted actions, unresolved questions, and the decision needed. Support continues coordinated customer communication until technical ownership is acknowledged.

Validate recovery by repeating the original business operation safely, checking durable state at the authoritative system, reviewing error and security telemetry, and testing an unaffected path. Remove temporary access, test artifacts, flags, and exceptions. Document recovered time, residual impact, monitoring interval, acceptance, and corrective owner. A workaround requires a stated risk, expiration, and tracked permanent correction.

When a diagnostic action fails, stop harmful repetition, preserve the exact error and correlation ID, execute rollback, and return to the last safe state. If rollback is unavailable, declare or update the incident. Communicate partial results and missing evidence honestly. Outcomes are limited by architecture, telemetry, retention, connectivity, third-party behavior, and locally tested procedures.

## Authority and internal recommendations

**Authoritative guidance** consists only of the cited standards or platform publications within their scope. **Internal recommendations** are this article’s intake fields, approval gates, evidence expectations, routing, and communication checkpoints. Local policy and accountable owners remain controlling. No certification, statutory deadline, universal support, or current compliance claim is made.

## Canonical sources

- RFC 2680 Packet Loss Metric: https://www.rfc-editor.org/rfc/rfc2680
- RFC 8085 UDP Usage Guidelines: https://www.rfc-editor.org/rfc/rfc8085
