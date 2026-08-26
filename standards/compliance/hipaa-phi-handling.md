# hipaa-phi-handling

**Issue:** Implementing technical safeguards for Protected Health Information (PHI) in a SaaS application under HIPAA Security Rule (45 CFR §164.312)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Any SaaS that creates, receives, maintains, or transmits PHI on behalf of a covered entity (hospital, insurer, provider) is a Business Associate and must implement the HIPAA Security Rule's technical safeguards. Violations carry tiered civil monetary penalties up to $1.9M per category per year (2024 adjusted figures). This entry focuses on engineering controls, not the administrative/physical safeguards.

## Pattern / Solution
**What counts as PHI:** 18 identifiers combined with health information — including name, email, IP address, dates, device identifiers, account numbers, and biometrics when linked to health data. De-identification requires either expert determination or safe-harbor removal of all 18 identifiers.

**Required technical safeguards (§164.312):**

```
(a)(1) Access Control
  → Unique user identification (no shared accounts)
  → Automatic logoff after inactivity (≤15 min recommended)
  → Encryption/decryption: AES-256 for data at rest

(b) Audit Controls
  → Log all access, creation, modification, deletion of PHI
  → Logs must be tamper-evident and retained ≥6 years

(c) Integrity
  → Verify PHI has not been altered in transit (TLS + checksums)
  → File integrity monitoring for stored PHI

(d) Person Authentication
  → MFA required for remote access to PHI systems

(e)(1) Transmission Security
  → TLS 1.2+ for all PHI in transit
  → No PHI in URL parameters (logged in web server access logs)
  → No PHI in email without encryption agreement
```

**PHI in application code — common mistakes:**

```python
# BAD: PHI in log line
logger.info(f"User {patient_name} ({ssn}) accessed record {record_id}")

# GOOD: log correlation IDs only
logger.info(f"PHI access: user_id={user_id} record_id={record_id} action=read")

# BAD: PHI in URL
GET /records?patient_name=John+Smith&dob=1980-01-01

# GOOD: opaque record IDs only
GET /records/rec_01J...
```

**Business Associate Agreement (BAA):**
- Must be signed before any PHI is shared with the covered entity.
- Must include breach notification obligation (60-day deadline to covered entity under Breach Notification Rule).
- Cloud providers: AWS, GCP, Azure all offer BAAs — enable it in writing before storing PHI.

**Minimum necessary standard:** Only access, use, or disclose the minimum PHI necessary for the stated purpose. Implement field-level access controls — a billing module should not read clinical notes.

## Gotchas
- Sending PHI to a third-party analytics or error monitoring tool (Sentry, Datadog) without a BAA is a violation — mask PHI before sending to these services.
- Test environments must not contain real PHI unless identical security controls are in place — use synthetic data generators.
- The Breach Notification Rule requires notification to covered entity within 60 days of discovery; the covered entity then notifies patients within 60 days of their own discovery.
- "De-identified" data under HIPAA is not the same as GDPR pseudonymised data — safe-harbor de-identification removes all 18 identifiers including geographic subdivision smaller than state.
- Workforce training is a required administrative safeguard — document completion annually.

## Related
- `hipaa-compliance.md`
- `data-classification-policy.md`
- `gdpr-breach-notification-72h.md`
- `audit-log-mandatory.md`
