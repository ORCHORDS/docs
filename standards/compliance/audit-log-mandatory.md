# audit-log-mandatory

**Issue:** What events must be audit-logged for compliance
**Date:** 2026-08-09
**Status:** documented (compliance checklist)

## Symptom
A regulator asks "show me every time user X's data was
accessed in the last 12 months." You query your audit log and
get a partial answer — many actions weren't logged because the
engineering team didn't know they were required.

## Root cause
Most jurisdictions + standards require a specific minimum set
of events to be audit-logged. The list is non-obvious; it's
spelled out across GDPR, SOC 2, HIPAA, PCI DSS, ISO 27001, and
various regional laws. Engineering teams that don't have a
checklist miss events.

**Source:** various — summarized from:
- GDPR Article 30 (records of processing activities)
- SOC 2 CC7.2 (system monitoring)
- ISO 27001 A.12.4.1 (event logging)
- PCI DSS 10 (track and monitor access)
- HIPAA §164.312(b) (audit controls)

## Fix
Mandatory audit log events for a consumer platform:

### Authentication events
- `user.login` — every successful login (actor, IP, UA)
- `user.login_failed` — every failed login (actor if known, IP, UA)
- `user.logout` — explicit logout
- `user.session_revoked` — session killed (admin or self)
- `user.mfa_enrolled` — MFA added
- `user.mfa_removed` — MFA removed
- `user.password_reset` — password reset (target user, hash prefix)

### Account events
- `user.created` — new user
- `user.deleted` — soft delete
- `user.erased` — GDPR Article 17 erasure
- `user.role_changed` — role update (old + new)
- `user.email_changed` — email update
- `user.verified` — email/phone verification

### Authorization events
- `access.granted` — access to a resource (per-resource, with
  resource_kind + resource_id)
- `access.denied` — denied access (with the reason: forbidden,
  not_found, etc.)
- `api_key.created` / `api_key.revoked`

### Data events
- `data.read` — read of PII (profile view, post fetch, etc.)
- `data.exported` — user data export (GDPR Article 15, CCPA, etc.)
- `data.modified` — PII change
- `data.deleted` — soft delete of user-generated content
- `data.shared` — data shared with a third party (analytics,
  ad network, etc.)

### Financial events
- `payment.created` — payment intent
- `payment.completed` — payment success
- `payment.failed` — payment failure
- `payment.refunded` — refund
- `payout.initiated` / `payout.completed`

### Compliance events
- `gdpr.erasure_requested` — user submitted Article 17 request
- `gdpr.erasure_completed` — controller completed the erasure
- `gdpr.export_requested` — user submitted Article 15 request
- `gdpr.export_completed` — controller completed the export
- `ccpa.opted_out` — user opted out of sale/share
- `csam.detected` — CSAM match (sensitive, restricted access)
- `csam.reported_to_ncmec` — NCMEC report filed

### Admin / operator events
- `admin.user_action` — any admin action on a user
- `admin.config_changed` — system config change
- `admin.feature_flag_changed` — feature flag toggle
- `admin.data_access` — operator viewing user data (for support)
- `admin.export_run` — bulk export

## What NOT to log

- **PII in metadata.** The audit log is itself PII. Don't put
  raw user content in the metadata field. Reference by ID.
- **Passwords, tokens, or secrets.** Ever.
- **Full request/response bodies.** Hash or summarize, don't
  store the full payload (storage cost + PII risk).
- **High-frequency read events without aggregation.** Don't log
  every `GET /api/posts/123` — it floods the audit log. Log
  significant reads (admin access, GDPR export, etc.).

## Verification
- **Test:** `test/audit-events.test.ts > all mandatory events
  trigger log writes` — passes
- **Audit:** Annual review of event list vs. compliance requirements
- **Pen test:** Third-party review confirms no missing event types

## Gotchas
- **The list grows over time.** New laws + new product features
  add event types. Schedule a quarterly review.
- **The audit log is itself a target.** A motivated attacker
  will try to access the audit log. Treat it as PII-grade
  (encrypted at rest, access-controlled, audit-the-auditors).
- **The Merkle chain is part of the audit log.** Don't separate
  them; chain all events together.
- **Async writes are risky.** If the audit write fails, the
  operation should fail (or roll back). "Fire and forget" loses
  events. Use a Durable Object for serialized writes.

## Related
- `audit-chain-durable-object.md` (the technical implementation)
- `soft-delete-pattern.md` (the `user.erased` event source)
- `patterns/per-tenant-durable-object.md` (the writer)
- GDPR Article 30: https://gdpr-info.eu/art-30-gdpr/
- SOC 2 CC7.2: https://www.aicpa.org/soc2
