# Exposed Secret Report Intake

## Purpose and scope

This runbook handles the reported condition for **Exposed Secret Report Intake**. Intake records secret type without its value, owner, environment, exposure URL or path, observation times, public reachability, suspected use, and affected systems. Support separates reporter statements from measured facts, records time zones, minimizes sensitive collection, and confirms the affected business operation. This is an operational procedure, not a promise of recovery, legal characterization, or authorization to bypass local policy.

## Intake and diagnosis

Capture type without value, owner, location, interval, privileges, expiry and audit use. Establish whether one user, tenant, version, location, or the wider service is affected. Request the narrowest artifact that answers a defined question; prefer identifiers, structured events, and redacted output over bulk payloads. Check incidents, maintenance, and recent changes before disruptive tests.

Build a timeline from first observation through the latest attempt and identify each clock. Compare the failure with a nearby successful control. Reproduce only with approved synthetic data in a supported environment. Never alter production merely to observe the symptom or ask a reporter to bypass protection.

## Operational workflow

The exact diagnostic sequence is to restrict the case, preserve location evidence without copying the value, revoke or rotate at the authority, search audit logs, update dependencies, remove exposure, test replacement, and monitor replay. Perform one reversible change at a time, recording authorization, expected result, stop condition, and rollback. Re-run both the failing operation and a nearby known-good control; a queued command or green job alone does not prove recovery.

After correction, repeat the original operation and a non-failing control. Validate the business result, not only a green response. Remove test objects, debug settings, exceptions, temporary access, and elevated privilege. Route durable correction to the owning backlog with impact and reproduction. Communication must state facts, uncertainty, effect, safe action, checkpoint, and decision owner.

## Controls and evidence

Retain intake parameters, original error, correlation IDs, relevant configuration, diagnostic output, approvals, changes and results, rollback status, and before-and-after validation. Use approved systems and content-appropriate access. Do not copy secrets, payloads, or unrelated personal information into ordinary notes. Existing schedules apply.

Validation must be repeatable. Use least privilege and separate approval from execution for destructive or broad actions. Automation identifies actor, target, time, action, result, and correlation ID. For sampling, record population, method, exclusions, and limitations. Exercise success, partial failure, contradictory telemetry, after-hours ownership, and failed rollback. Trend recurrence and workaround age.

## Failure handling

Stop and escalate for unknown ownership or unauthorized use. Preserve conflicting observations rather than choosing the convenient one. Increased privilege, scope, exposure, cost, or irreversibility requires owner approval. Stop retries that can duplicate work, worsen saturation, overwrite state, or hide the first error.

If no safe workaround exists, preserve state and use only owner-approved continuity options. A failed rollback, unintended change, wrong target, or bypass is a new incident. State residual uncertainty; never assert safety, completeness, compliance, or absence of compromise from one test.

## Closure validation

Confirm the original symptom no longer occurs under recorded conditions, the adjacent control works, logs show the intended target, temporary measures are removed or owned, residual limits are documented, and recurrence will produce useful telemetry. Keep every unknown visible as an assigned exception.

## Topic-specific validation

Credential validation must use the owning service, not an application error alone. Confirm that the old value fails at every relevant endpoint and that legitimate consumers use the replacement without falling back to embedded copies. Search deployment variables, build artifacts, package registries, mirrors, caches, and diagnostic systems according to authorized scope. Where a key pair is involved, verify the replacement public key or certificate distribution as well as private-key retirement. Secret-scanning alerts should preserve location and fingerprint, not the value. Review whether excessive privilege, missing expiry, weak ownership, or unavailable audit data increased impact, and assign each finding separately.


## Escalation, recovery, and failure governance

Escalate when impact crosses tenants or regions, authorization is unclear, evidence suggests compromise or data exposure, an irreversible action is proposed, rollback fails, or the service owner cannot accept the residual risk. The handoff includes a timestamped timeline, identifiers, evidence locations, actions taken, current containment, unresolved questions, and the decision requested. Support retains customer-communication ownership until the receiving team acknowledges the handoff.

Validate recovery by repeating the original business operation with safe inputs, checking the durable system of record, reviewing error and security telemetry, and testing an unaffected control path. Remove temporary access, test artifacts, debug flags, exceptions, and staged copies. Record the recovered time, residual impact, monitoring period, customer or owner acceptance, and follow-up owner. A workaround is not closure unless its risk, expiry, and permanent correction are tracked.

If a step fails, stop retries that could amplify harm, preserve the exact error and correlation ID, execute the documented rollback, and return to the last known safe state. Declare or update an incident when rollback is unavailable. State partial recovery and unavailable evidence plainly. Capability remains limited by architecture, telemetry, retention, connectivity, provider behavior, and tested local procedures.

## Authority versus internal recommendation

**Authoritative guidance** is limited to the public standards and platform documentation cited below within their stated scope. **Internal recommendations** are the intake fields, approval gates, evidence package, communication checkpoints, and routing in this article. Teams must map them to local ownership and policy. This article asserts no certification, statutory deadline, universal compatibility, or current compliance status.

## Canonical sources

- OWASP Secrets Management: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- CISA Secure by Design: https://www.cisa.gov/securebydesign
