# Singapore PDPA General Compliance on Cloudflare Workers and D1

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

example project serves users in Singapore whose personal data is protected by the Personal Data Protection Act 2012 (PDPA), as amended by the Personal Data Protection (Amendment) Act 2020. The platform must implement consent, purpose limitation, access and correction rights, and data protection policies or face fines of up to SGD 1 million or 10% of annual Singapore turnover. This article covers general PDPA compliance obligations; for breach notification timing specifically, see `compliance/singapore-pdpa-notifiable-breach-assessment-clock.md`.

## Context

Singapore's PDPA is administered by the Personal Data Protection Commission (PDPC). The 2020 amendments introduced mandatory data breach notification, deemed consent by notification, and new exceptions for legitimate interests and business improvement purposes—reducing reliance on opt-in consent in commercial settings. For example project, the primary obligations are the Consent Obligation (section 13), Purpose Limitation Obligation (section 18), Retention Limitation Obligation (section 25), Protection Obligation (section 24), and Transfer Limitation Obligation (section 26). Legitimate interest under the Third Schedule may be used for fraud detection and platform safety without explicit consent.

## Consent Obligation and Deemed Consent

Section 15A of PDPA (2020 amendment) allows "deemed consent by notification" where users are notified of a new processing purpose and given a reasonable opt-out window. The example project Worker implements both explicit consent and the notification-based deemed consent pathway.

```typescript
// worker/pdpa-consent.ts
export type PdpaConsentType = "explicit" | "deemed_notification" | "legitimate_interest";

export interface PdpaConsentRecord {
  subjectRef: string;
  purpose: string;
  consentType: PdpaConsentType;
  notifiedAt: number | null;   // for deemed consent, when notification was sent
  optOutDeadline: number | null; // 30-day opt-out window for deemed consent
  consentedAt: number | null;
  withdrawnAt: number | null;
}

export async function upsertPdpaConsent(
  db: D1Database,
  record: PdpaConsentRecord,
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO pdpa_consents
         (subject_ref, purpose, consent_type, notified_at,
          opt_out_deadline, consented_at, withdrawn_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT (subject_ref, purpose)
       DO UPDATE SET
         consent_type     = excluded.consent_type,
         notified_at      = excluded.notified_at,
         opt_out_deadline = excluded.opt_out_deadline,
         consented_at     = excluded.consented_at,
         withdrawn_at     = excluded.withdrawn_at`,
    )
    .bind(
      record.subjectRef,
      record.purpose,
      record.consentType,
      record.notifiedAt,
      record.optOutDeadline,
      record.consentedAt,
      record.withdrawnAt,
    )
    .run();
}

export async function isProcessingPermitted(
  db: D1Database,
  subjectRef: string,
  purpose: string,
): Promise<boolean> {
  const row = await db
    .prepare(
      `SELECT consent_type, opt_out_deadline, withdrawn_at
         FROM pdpa_consents
        WHERE subject_ref = ? AND purpose = ?`,
    )
    .bind(subjectRef, purpose)
    .first<{ consent_type: string; opt_out_deadline: number | null; withdrawn_at: number | null }>();

  if (!row || row.withdrawn_at !== null) return false;

  if (row.consent_type === "legitimate_interest") return true;
  if (row.consent_type === "explicit") return true;
  if (row.consent_type === "deemed_notification") {
    // Processing permitted only after opt-out deadline has passed
    return row.opt_out_deadline !== null && Date.now() > row.opt_out_deadline;
  }
  return false;
}
```

## Retention Limitation Obligation

Section 25 of PDPA requires deletion of personal data when the business or legal purpose for retention is fulfilled. The Worker runs a scheduled D1 cleanup job using Cloudflare Cron Triggers.

```typescript
// worker/pdpa-retention.ts – executed by a Cron Trigger
export async function purgeExpiredData(db: D1Database): Promise<number> {
  const nowMs = Date.now();

  // Delete posts beyond 2-year retention window (adjust per privacy notice)
  const postResult = await db
    .prepare(
      `DELETE FROM posts
        WHERE created_at < ?
          AND subject_ref IN (
            SELECT subject_ref FROM pdpa_consents
             WHERE purpose = 'content_hosting'
               AND (withdrawn_at IS NOT NULL OR consented_at < ?)
          )`,
    )
    .bind(nowMs - 2 * 365 * 24 * 60 * 60 * 1000, nowMs - 2 * 365 * 24 * 60 * 60 * 1000)
    .run();

  // Purge stale consent records where user is fully deleted
  await db
    .prepare(
      `DELETE FROM pdpa_consents
        WHERE subject_ref NOT IN (SELECT subject_ref FROM user_profiles)`,
    )
    .run();

  return postResult.meta.changes;
}
```

## Access and Correction Rights

Sections 21 and 22 of PDPA grant data subjects the right to access their personal data and to correct inaccuracies. The rights handler must respond within 30 calendar days.

```typescript
// worker/pdpa-rights.ts
export async function handlePdpaAccessRequest(
  db: D1Database,
  subjectRef: string,
): Promise<Response> {
  const [profile, posts, consents] = await Promise.all([
    db
      .prepare("SELECT display_name, bio, created_at FROM user_profiles WHERE subject_ref = ?")
      .bind(subjectRef)
      .first(),
    db
      .prepare("SELECT post_id, content_hash, created_at FROM posts WHERE subject_ref = ? ORDER BY created_at DESC")
      .bind(subjectRef)
      .all(),
    db
      .prepare("SELECT purpose, consent_type, consented_at FROM pdpa_consents WHERE subject_ref = ?")
      .bind(subjectRef)
      .all(),
  ]);

  return Response.json({
    profile,
    posts: posts.results,
    processingBases: consents.results,
    generatedAt: new Date().toISOString(),
    responseDeadlineDays: 30,
  });
}

export async function handlePdpaCorrectionRequest(
  db: D1Database,
  subjectRef: string,
  field: string,
  newValue: string,
): Promise<Response> {
  const CORRECTABLE = new Set(["display_name", "bio"]);
  if (!CORRECTABLE.has(field)) {
    return new Response("Field cannot be corrected via self-service", { status: 422 });
  }

  await db
    .prepare(`UPDATE user_profiles SET ${field} = ?, updated_at = ? WHERE subject_ref = ?`)
    .bind(newValue, Date.now(), subjectRef)
    .run();

  return Response.json({ corrected: field, updatedAt: new Date().toISOString() });
}
```

## Transfer Limitation Obligation

Section 26 of PDPA restricts personal data transfers to countries outside Singapore unless the recipient provides comparable protection. The PDPC whitelist of approved countries is checked at transfer time; for unlisted countries, PDPC-approved contractual clauses apply.

```typescript
// worker/pdpa-transfer.ts
// Countries with PDPC-recognised adequate protection (illustrative list – verify with PDPC)
const ADEQUATE_COUNTRIES = new Set(["EU", "UK", "NZ", "AU", "JP", "KR"]);

export type PdpaTransferBasis = "adequacy" | "contractual_clauses" | "consent" | "necessity";

export async function checkAndLogTransfer(
  db: D1Database,
  subjectRef: string,
  destinationCountry: string,
  purpose: string,
): Promise<PdpaTransferBasis> {
  const basis: PdpaTransferBasis = ADEQUATE_COUNTRIES.has(destinationCountry)
    ? "adequacy"
    : "contractual_clauses";

  await db
    .prepare(
      `INSERT INTO pdpa_transfer_log
         (subject_ref, destination_country, basis, purpose, logged_at)
       VALUES (?, ?, ?, ?, ?)`,
    )
    .bind(subjectRef, destinationCountry, basis, purpose, Date.now())
    .run();

  return basis;
}
```

## Anti-patterns

- Relying solely on deemed-consent-by-notification without actually sending the notification email/in-app message; the notification must be demonstrably received or dispatched.
- Using a single retention period for all data categories; Singapore law requires purpose-specific retention windows tied to each processing purpose in the privacy notice.
- Processing sensitive personal data (financial information, health data) under a general platform-operation purpose without a separate, explicit consent item.

## Gotchas

- The PDPA "legitimate interest" exception under the Third Schedule is narrower than GDPR Article 6(1)(f); it requires that the legitimate interest not be outweighed by "adverse effects on the individual", and the PDPC guidance explicitly lists cases where it cannot be used (e.g., direct marketing to non-customers).
- Singapore's PDPC issues advisory guidelines that are not legally binding but are treated as authoritative in enforcement decisions—reviewing relevant PDPC guidelines (e.g., Advisory Guidelines on the PDPA for Selected Topics) is essential before finalising a compliance design.

## Verification

```bash
# Confirm consent records include deemed-consent expiry dates
wrangler d1 execute example project-prod \
  --command "SELECT purpose, consent_type, opt_out_deadline FROM pdpa_consents WHERE consent_type='deemed_notification' LIMIT 10;"

# Test access rights endpoint
curl -si -H "Authorization: Bearer $TEST_TOKEN" \
  https://example project.example.com/pdpa/access | jq .profile

# Check retention purge metrics from last cron run
wrangler d1 execute example project-prod \
  --command "SELECT * FROM cron_audit_log WHERE task='pdpa_retention' ORDER BY run_at DESC LIMIT 3;"
```

## Related

- `compliance/singapore-pdpa-notifiable-breach-assessment-clock.md`
- `compliance/cross-border-data-transfer-mechanisms.md`
- `compliance/data-retention-automated-deletion-workers.md`

## Sources

- https://www.pdpc.gov.sg/Overview-of-PDPA/The-Legislation/Personal-Data-Protection-Act
- https://www.pdpc.gov.sg/Guidelines-and-Consultation/Advisory-Guidelines-Main
- https://sso.agc.gov.sg/Act/PDPA2012
