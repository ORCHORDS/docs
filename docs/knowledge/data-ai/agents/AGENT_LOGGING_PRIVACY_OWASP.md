# Privacy-Preserving Security Logging for Agent Systems

## Scope

Agent logs can contain prompts, retrieved passages, tool arguments, model outputs, identity claims, authorization decisions, and human review notes. These records are useful for security and reliability but can become a concentrated source of secrets and personal data. OWASP's Logging Cheat Sheet recommends consistent security events while explicitly excluding or masking sensitive data.

This article concerns security logging and evidence design, not distributed tracing semantics or metric naming. The goal is to preserve who did what, through which controlled path, with what outcome, while avoiding default capture of content. Logging must follow applicable organizational, contractual, and legal requirements.

## Implementation workflow

Start from investigation questions rather than available fields. Define events for authentication, authorization decisions, tool requests and outcomes, approval transitions, policy changes, memory writes and deletion, data export, configuration releases, security-control failures, and administrative access. Assign each event an owner, severity, required fields, retention, and access class.

Use a structured event schema. Include event time with clock source, service and environment, release manifest ID, pseudonymous actor or workload reference, tenant boundary, action type, target class, policy decision ID, outcome, reason code, and correlation identifiers. Keep payload references separate and access-controlled. Prefer one-way or tokenized subject references where investigators can resolve them only through an authorized process.

Create a data classification table for every field. Explicitly prohibit access tokens, session IDs, passwords, private keys, raw authorization headers, complete prompts, full tool responses, and unnecessary personal data. Apply redaction at the producer before the event leaves process memory. Collector-side filters are a secondary safeguard, not the primary control.

## Controls

Prevent log injection by structured serialization, length limits, and handling of control characters. Authenticate producers and encrypt transport to the collector. Restrict write, query, export, and deletion privileges separately. Make security logs append-oriented and integrity-protected according to the threat model; record administrative changes and exports in an independent audit path.

Use sampling cautiously. Routine success events may be sampled under policy, but denials, privilege changes, approval bypass attempts, and control failures generally need deterministic capture. Sampling must never be attacker-controlled through trace flags. Apply retention by event class and verify deletion in hot, archive, and analytics copies.

When content capture is temporarily required for a bounded investigation, use explicit approval, narrow cohort, short duration, strong access controls, visible activation state, and automatic expiry. Do not silently turn debug logging on globally.

## Validation evidence

Maintain the event catalog, field classifications, redaction rules, access matrix, retention schedule, and threat model. Automated tests inject credential-like canaries, multiline values, oversized fields, Unicode controls, malformed structures, and personal identifiers, then verify they are rejected, redacted, or tokenized as specified. Confirm that investigators can reconstruct a test tool action without raw content.

Exercise access reviews and export monitoring. Test clock drift, collector outage, queue overflow, disk exhaustion, and duplicate delivery. Verify integrity controls and restoration from archive. Search stored events periodically for prohibited patterns and high-cardinality accidental payload fields. Record false positives and remediation rather than declaring a scanner perfect.

## Failure handling

Logging failure must not silently disable security controls. Define which operations fail closed, which continue with a local bounded buffer, and which enter a reduced-capability mode. Protect availability by capping buffers and avoiding synchronous logging dependencies for low-risk events. Emit health signals through an independent channel when the primary collector is unavailable.

If sensitive data is logged, stop the producer, restrict affected indexes, identify viewers and exports, rotate exposed credentials, and follow privacy incident procedures. Delete or cryptographically retire copies where policy permits, correct the producer-side schema, and add a canary regression. If audit integrity is uncertain, state the evidence gap explicitly during investigation.

## Canonical sources

- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- NIST SP 800-92, *Guide to Computer Security Log Management*: https://doi.org/10.6028/NIST.SP.800-92
- OpenTelemetry security guidance: https://opentelemetry.io/docs/security/
