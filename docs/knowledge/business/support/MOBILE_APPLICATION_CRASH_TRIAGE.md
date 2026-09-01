# Mobile Application Crash Triage

## Purpose and scope

This runbook handles **Mobile Application Crash Triage**. Intake records app build and channel, OS, device model, crash time, foreground action, frequency, account scope, network and storage state, and crash identifier. Support separates observations from telemetry, timestamps evidence, minimizes sensitive collection, and confirms business impact. It does not authorize policy bypass, unsafe investigation, legal conclusions, or guarantees of recovery.

## Intake and diagnosis

Capture build, OS, model, steps, frequency, network, storage, signature and data-loss impact. Establish whether one user, tenant, version, location, or the wider service is affected. Request the narrowest artifact that answers a defined question; prefer identifiers, structured events, and redacted output over bulk payloads. Check incidents, maintenance, and recent changes before disruptive tests.

Build a timeline from first observation through the latest attempt and identify each clock. Compare the failure with a nearby successful control. Reproduce only with approved synthetic data in a supported environment. Never alter production merely to observe the symptom or ask a reporter to bypass protection.

## Operational workflow

The exact sequence is to check release health, correlate the crash ID, classify exception, watchdog or memory termination, compare versions and devices, reproduce with synthetic data, inspect feature flags, symbolicate, and test rollback or fix. Make one authorized reversible change at a time with an expected result, stop condition, and rollback. Verify the original operation and a nearby control; task acceptance alone is not recovery evidence.

After correction, repeat the original operation and a non-failing control. Validate the business result, not only a green response. Remove test objects, debug settings, exceptions, temporary access, and elevated privilege. Route durable correction to the owning backlog with impact and reproduction. Communication must state facts, uncertainty, effect, safe action, checkpoint, and decision owner.

## Controls and evidence

Retain intake parameters, original error, correlation IDs, relevant configuration, diagnostic output, approvals, changes and results, rollback status, and before-and-after validation. Use approved systems and content-appropriate access. Do not copy secrets, payloads, or unrelated personal information into ordinary notes. Existing schedules apply.

Validation must be repeatable. Use least privilege and separate approval from execution for destructive or broad actions. Automation identifies actor, target, time, action, result, and correlation ID. For sampling, record population, method, exclusions, and limitations. Exercise success, partial failure, contradictory telemetry, after-hours ownership, and failed rollback. Trend recurrence and workaround age.

## Failure handling

Stop and escalate for unsynchronized data, sensitive diagnostics, or payment-flow crash. Preserve conflicting observations rather than choosing the convenient one. Increased privilege, scope, exposure, cost, or irreversibility requires owner approval. Stop retries that can duplicate work, worsen saturation, overwrite state, or hide the first error.

If no safe workaround exists, preserve state and use only owner-approved continuity options. A failed rollback, unintended change, wrong target, or bypass is a new incident. State residual uncertainty; never assert safety, completeness, compliance, or absence of compromise from one test.

## Closure validation

Confirm the original symptom no longer occurs under recorded conditions, the adjacent control works, logs show the intended target, temporary measures are removed or owned, residual limits are documented, and recurrence will produce useful telemetry. Keep every unknown visible as an assigned exception.

## Topic-specific validation

For mobile validation, retain the exact build-to-symbol or mapping-file relationship; a stack trace interpreted with the wrong symbols can send engineering to the wrong component. Compare foreground crashes, background terminations, hangs, and operating-system watchdog events separately. Test cold start, warm start, interrupted network, rotation, low storage, and return from background only when relevant to the reported path. Confirm that a workaround does not discard drafts, repeat transactions, or conceal an endless retry. During staged release, compare the affected cohort with the previous build and record rollout percentage. Product owners—not frontline support—decide pause, rollback, or accelerated release.


## Escalation, recovery validation, and failure handling

Escalate for cross-tenant or widespread impact, unclear authority, suspected compromise or exposure, safety concerns, irreversible action, failed rollback, or residual risk outside the service owner’s delegation. Provide identifiers, timeline, evidence locations, containment, attempted actions, unresolved questions, and the decision needed. Support continues coordinated customer communication until technical ownership is acknowledged.

Validate recovery by repeating the original business operation safely, checking durable state at the authoritative system, reviewing error and security telemetry, and testing an unaffected path. Remove temporary access, test artifacts, flags, and exceptions. Document recovered time, residual impact, monitoring interval, acceptance, and corrective owner. A workaround requires a stated risk, expiration, and tracked permanent correction.

When a diagnostic action fails, stop harmful repetition, preserve the exact error and correlation ID, execute rollback, and return to the last safe state. If rollback is unavailable, declare or update the incident. Communicate partial results and missing evidence honestly. Outcomes are limited by architecture, telemetry, retention, connectivity, third-party behavior, and locally tested procedures.

## Authority and internal recommendations

**Authoritative guidance** consists only of the cited standards or platform publications within their scope. **Internal recommendations** are this article’s intake fields, approval gates, evidence expectations, routing, and communication checkpoints. Local policy and accountable owners remain controlling. No certification, statutory deadline, universal support, or current compliance claim is made.

## Canonical sources

- Apple crash reports: https://developer.apple.com/documentation/xcode/diagnosing-issues-using-crash-reports-and-device-logs
- Android crash diagnosis: https://developer.android.com/games/optimize/crash
