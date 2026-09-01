# Lost or Stolen Managed Device Intake

## Purpose and scope

This runbook handles **Lost or Stolen Managed Device Intake**. Intake records asset tag, assigned user, last known time and place, lock and connectivity state, sensitive access, management status, and immediate personal-safety concern. Support separates observations from telemetry, timestamps evidence, minimizes sensitive collection, and confirms business impact. It does not authorize policy bypass, unsafe investigation, legal conclusions, or guarantees of recovery.

The coordinator should minimize collected content, distinguish reported observations from measured facts, and record time zones. Use authoritative inventory and telemetry rather than assumptions. A workaround must be reversible, documented, limited in scope, and assigned an expiry or permanent owner.

## Intake and diagnosis

Capture asset tag, custodian, inventory serial, last-known place and time, discovery time, power and unlock state, encryption, enrollment, and locally stored data. Establish whether one device or a wider theft event is involved. Request the narrowest artifact that answers a defined question; prefer identifiers and structured events over screenshots. Check active incidents and recent inventory changes before asking the reporter to repeat steps.

Build a timeline from last confirmed possession through the latest management check-in. Identify the clock behind each timestamp. Never disclose location telemetry to an unapproved person or encourage physical confrontation. For immediate personal danger, use local safety channels. Do not assume that a device is encrypted merely because encryption is organizational policy.

## Operational workflow

1. Mark the asset missing in the authoritative inventory and route the report to security and privacy owners as policy requires.
2. Confirm management enrollment, encryption state, operating-system compliance, last check-in, and assigned user from authoritative systems.
3. Revoke device-bound sessions, certificates, VPN material, and managed application tokens through approved administration. Credential owners decide wider rotation.
4. Apply the preauthorized action—lock, lost mode, restriction, or wipe. Record the target identifiers, authorizer, issue time, expected result, and command acknowledgement. A queued command is not completed containment.
5. Preserve relevant management, authentication, network, and data-access logs. Security determines investigative scope and use of location information.
6. Provide approved replacement and continuity steps. If the device returns, record custody and route it for inspection, management reconciliation, credential review, and formal clearance before reuse.

Perform one controlled action at a time. A destructive command requires independent resolution of the target and the authority defined by policy. Remove temporary access and exceptions when their purpose ends.

## Controls and validation evidence

Retain the initial report, inventory snapshot, encryption and enrollment state, original timestamps, last check-in, revocation events, management commands and acknowledgements, approvals, impact assessment, and return or disposal result. Evidence belongs in approved systems with access appropriate to location and personal information. Existing schedules govern retention.

Validation must be repeatable by another authorized operator. Missing telemetry is an unknown state, not proof of success. Use least privilege and separate approval from execution for destructive or broad actions. Automation should identify actor, target, time, requested action, result, and correlation identifier.

Exercise an offline laptop, an unlocked phone, removable storage, an overseas loss, conflicting inventory identifiers, and a device recovered after wipe initiation. Review whether staff respected decision boundaries rather than rewarding fast closure. Reconcile exercise findings with endpoint-management and inventory owners.

## Failure handling

Conflicting asset identifiers require a stop before any destructive command. An offline device remains uncontained even if a command is queued. Unknown encryption requires explicit risk assessment. If active account use or extortion is reported, preserve the message and increase incident priority without engaging the sender.

If the device is recovered with broken custody, failed tamper checks, or unexplained configuration changes, require forensic clearance. A command sent to the wrong target is a new incident. Privacy and security owners decide notification consequences; support must not claim that encryption removes all risk without confirming implementation and key protection.

Tell affected people what remains unknown. Never assert safety, completeness, compliance, or absence of compromise from one successful check. If no safe administrative action is available, preserve the current state, document the gap, and maintain escalation.

## Closure validation

Confirm inventory status, known command result, session revocation, continuity arrangements, residual uncertainty, and the owner of any ongoing investigation. If the asset returned, require documented clearance. Keep unknown items visible as exceptions rather than silently treating them as passed.


## Escalation, recovery validation, and failure handling

Escalate for cross-tenant or widespread impact, unclear authority, suspected compromise or exposure, safety concerns, irreversible action, failed rollback, or residual risk outside the service owner’s delegation. Provide identifiers, timeline, evidence locations, containment, attempted actions, unresolved questions, and the decision needed. Support continues coordinated customer communication until technical ownership is acknowledged.

Validate recovery by repeating the original business operation safely, checking durable state at the authoritative system, reviewing error and security telemetry, and testing an unaffected path. Remove temporary access, test artifacts, flags, and exceptions. Document recovered time, residual impact, monitoring interval, acceptance, and corrective owner. A workaround requires a stated risk, expiration, and tracked permanent correction.

When a diagnostic action fails, stop harmful repetition, preserve the exact error and correlation ID, execute rollback, and return to the last safe state. If rollback is unavailable, declare or update the incident. Communicate partial results and missing evidence honestly. Outcomes are limited by architecture, telemetry, retention, connectivity, third-party behavior, and locally tested procedures.

## Limitations, authority, and internal recommendations

**Authoritative guidance** consists only of the cited standards or platform publications within their scope. **Internal recommendations** are this article’s intake fields, approval gates, evidence expectations, routing, and communication checkpoints. Local policy and accountable owners remain controlling. No certification, statutory deadline, universal support, or current compliance claim is made.

## Canonical sources

- NIST SP 800-124 Rev. 2: https://csrc.nist.gov/pubs/sp/800/124/r2/final
- CISA Mobile Device Cybersecurity Checklist: https://www.cisa.gov/resources-tools/resources/mobile-device-cybersecurity-checklist
