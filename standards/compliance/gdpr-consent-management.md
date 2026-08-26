# gdpr-consent-management

**Issue:** Capturing, storing, and withdrawing GDPR-compliant consent in a SaaS product
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
GDPR Art. 7 requires controllers to demonstrate that consent was freely given, specific, informed, and unambiguous. Cookie banners that pre-tick boxes, bundle consent for multiple purposes, or make withdrawal harder than opt-in are non-compliant and routinely fined by EU DPAs. This entry covers consent record schema and the withdrawal flow — not the UI banner itself.

## Pattern / Solution
**Consent record schema (PostgreSQL example):**

```sql
CREATE TABLE consent_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id      UUID NOT NULL,
    purpose         TEXT NOT NULL,          -- 'analytics', 'marketing', 'functional'
    legal_basis     TEXT NOT NULL,          -- 'consent', 'legitimate_interest', etc.
    granted         BOOLEAN NOT NULL,
    granted_at      TIMESTAMPTZ,
    withdrawn_at    TIMESTAMPTZ,
    version         TEXT NOT NULL,          -- privacy policy version at time of consent
    ip_address      INET,
    user_agent      TEXT,
    proof_blob      JSONB                   -- serialized form state / click evidence
);
CREATE INDEX ON consent_records (subject_id, purpose, granted_at DESC);
```

**Consent capture flow:**
1. Present granular purpose options — never bundle marketing + analytics into one checkbox.
2. Record `ip_address`, `user_agent`, `version`, and `proof_blob` at capture time.
3. Do **not** start processing until a valid consent record exists for that purpose.

**Withdrawal API:**
```python
def withdraw_consent(subject_id: str, purpose: str):
    db.execute("""
        UPDATE consent_records
        SET granted = false, withdrawn_at = NOW()
        WHERE subject_id = %s AND purpose = %s AND granted = true
    """, (subject_id, purpose))
    # Immediately halt downstream pipelines for this purpose
    event_bus.publish("consent.withdrawn", {"subject_id": subject_id, "purpose": purpose})
```

**Consent wall anti-pattern:** Do not gate access to your core service on consent to non-essential processing. This voids the "freely given" requirement.

## Gotchas
- Consent for children (under 16 in most EU member states, 13 in some) requires parental consent — check jurisdiction-specific thresholds.
- Legitimate interest is **not** a substitute for consent when the processing is high-risk or the data subject would not reasonably expect it.
- Consent obtained through a third party (e.g., a reseller) must still meet the same standard — get documented proof.
- Refreshing consent is required when the purpose changes materially, even if the original consent hasn't expired.
- Store consent records for the full period you may need to defend a complaint — typically the processing period plus your statute of limitations.

## Related
- `gdpr-data-subject-rights-api.md`
- `gdpr-data-retention-policy.md`
- `ccpa-opt-out.md`
- `gdpr-consent-mgmt-implementation-guide-2026.md`
