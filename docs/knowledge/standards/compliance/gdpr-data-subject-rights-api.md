# gdpr-data-subject-rights-api

**Issue:** Implementing a compliant API to handle GDPR data subject requests (access, rectification, erasure, portability, restriction, objection)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Controllers must respond to data subject requests within one month (extendable by two months for complex cases). Without a dedicated API layer, requests are handled ad-hoc, leading to missed deadlines, inconsistent responses, and audit failures. SaaS platforms must expose programmatic endpoints so customer tenants can propagate requests to their own end-users.

## Pattern / Solution
Design a unified DSR (Data Subject Request) orchestration service:

```python
# POST /api/v1/dsr
{
  "type": "access" | "erasure" | "portability" | "rectification" | "restriction" | "objection",
  "subject_email": "user@example.com",
  "requester_verified": true,
  "verification_method": "email_otp",
  "metadata": {}
}

# Response
{
  "request_id": "dsr_01J...",
  "deadline": "2026-09-11T00:00:00Z",   # +30 days
  "status": "pending",
  "estimated_completion": "2026-08-18T00:00:00Z"
}
```

Workflow:
1. **Identity verification** — require OTP or re-authentication before accepting any DSR.
2. **Fan-out** — the orchestrator sends the request to every data store (primary DB, analytics, backups, third-party sub-processors) via an internal event bus.
3. **Aggregation** — collect responses; for access/portability requests compile a machine-readable export (JSON or CSV).
4. **Deadline tracking** — a scheduler fires alerts at day 20 and day 28 if the request is still open.
5. **Audit log** — every state transition is appended to an immutable log with timestamp and operator ID.

```python
# Pseudocode for erasure fan-out
async def handle_erasure(request_id, subject_id):
    tasks = [
        erase_from_postgres(subject_id),
        erase_from_elasticsearch(subject_id),
        erase_from_s3_exports(subject_id),
        notify_subprocessors(subject_id),   # Stripe, Intercom, etc.
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    record_completion(request_id, results)
```

For portability, output must be in a commonly used, machine-readable format (GDPR Art. 20). Prefer JSON with a documented schema over proprietary formats.

## Gotchas
- Erasure does **not** override legal retention obligations — keep a tombstone record proving the erasure happened, even after deleting the data.
- Backup copies must also be purged on the next scheduled backup cycle; document this gap in your response to the requester.
- Automated identity verification must be robust enough to prevent third-party erasure attacks (social engineering someone else's data away).
- Sub-processor notification must happen within your own deadline — their SLA must be shorter than yours.
- Requests made through a representative (e.g., parental consent for a minor) require additional verification steps.
- Right to restriction ≠ erasure; restricted data must be retained but must not be processed further.

## Related
- `gdpr-article-17-erasure.md`
- `gdpr-consent-management.md`
- `gdpr-data-retention-policy.md`
- `audit-log-mandatory.md`
