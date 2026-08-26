# Illinois BIPA: Biometric Data Compliance in Workers + D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You collect fingerprints, face geometry, iris scans, or voiceprints for authentication or fraud prevention and need to comply with Illinois' Biometric Information Privacy Act (740 ILCS 14), which carries a private right of action and statutory damages up to $5,000 per wilful violation.

## Context
BIPA applies to any private entity collecting biometric identifiers or information from Illinois residents regardless of where the entity is located. Workers/D1 must enforce written consent before capture, maintain a publicly available retention policy, and destroy data on schedule. Cloudflare Workers acts as the API layer that intercepts biometric template uploads and enforces policy checks before committing data to D1. Cron Triggers drive automated deletion when the 3-year window closes.

## Consent Gate Middleware

Every biometric collection endpoint must verify prior written consent before processing data. A 451 response signals the legal reason for refusal.

```typescript
// src/bipa-consent.ts
interface Env {
  DB: D1Database;
}

type BiometricType = 'fingerprint' | 'face_geometry' | 'iris' | 'voice';

interface ConsentRecord {
  user_id: string;
  consent_type: BiometricType;
  purpose: string;
  retention_period_years: number;
  consented_at: string;
  written_consent_doc_url: string;
}

export async function requireBipaConsent(
  env: Env,
  userId: string,
  biometricType: BiometricType
): Promise<Response | null> {
  const existing = await env.DB.prepare(`
    SELECT id FROM bipa_consents
    WHERE user_id = ? AND consent_type = ? AND revoked_at IS NULL
    LIMIT 1
  `).bind(userId, biometricType).first();

  if (!existing) {
    return Response.json(
      {
        error: 'BIPA_CONSENT_REQUIRED',
        message:
          'Written consent required before biometric collection under 740 ILCS 14/15(b)',
        consent_url: '/biometric-consent',
      },
      { status: 451 }
    );
  }
  return null; // consent present — proceed
}

export async function recordBipaConsent(
  env: Env,
  consent: ConsentRecord,
  requestIp: string
): Promise<void> {
  await env.DB.prepare(`
    INSERT INTO bipa_consents
      (user_id, consent_type, purpose, retention_period_years,
       consented_at, ip_address, written_consent_doc_url)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `).bind(
    consent.user_id,
    consent.consent_type,
    consent.purpose,
    consent.retention_period_years,
    consent.consented_at,
    requestIp,
    consent.written_consent_doc_url
  ).run();
}

export async function revokeBipaConsent(
  env: Env,
  userId: string,
  biometricType: BiometricType,
  reason: string
): Promise<void> {
  await env.DB.prepare(`
    UPDATE bipa_consents
    SET revoked_at = ?, revocation_reason = ?
    WHERE user_id = ? AND consent_type = ? AND revoked_at IS NULL
  `).bind(new Date().toISOString(), reason, userId, biometricType).run();
}
```

## Retention Enforcement via Cron Trigger

BIPA §15(a) requires destruction within 3 years of collection or when the initial purpose is fulfilled, whichever is first. Wire `handleBipaRetentionPurge` to a `scheduled` handler firing daily.

```typescript
// src/bipa-retention.ts
export async function handleBipaRetentionPurge(env: Env): Promise<void> {
  const cutoff = new Date();
  cutoff.setFullYear(cutoff.getFullYear() - 3);

  const expired = await env.DB.prepare(`
    SELECT id AS consent_id, user_id, consent_type
    FROM bipa_consents
    WHERE consented_at < ?
      AND revoked_at IS NULL
  `).bind(cutoff.toISOString()).all<{
    consent_id: number;
    user_id: string;
    consent_type: string;
  }>();

  const stmts: D1PreparedStatement[] = [];

  for (const row of expired.results) {
    // Remove biometric template
    stmts.push(
      env.DB.prepare(`
        DELETE FROM biometric_templates
        WHERE user_id = ? AND template_type = ?
      `).bind(row.user_id, row.consent_type)
    );

    // Mark consent expired
    stmts.push(
      env.DB.prepare(`
        UPDATE bipa_consents
        SET revoked_at = ?, revocation_reason = 'retention_period_expired'
        WHERE id = ?
      `).bind(new Date().toISOString(), row.consent_id)
    );

    // Append audit record
    stmts.push(
      env.DB.prepare(`
        INSERT INTO bipa_audit_log (user_id, action, detail, occurred_at)
        VALUES (?, 'biometric_purge', ?, ?)
      `).bind(
        row.user_id,
        JSON.stringify({
          type: row.consent_type,
          cite: '740_ILCS_14_15a',
          reason: '3_year_limit',
        }),
        new Date().toISOString()
      )
    );
  }

  if (stmts.length > 0) {
    await env.DB.batch(stmts);
  }
}
```

## Public Retention Policy Endpoint

BIPA §15(a) requires a written policy, made available to the public, governing the retention schedule and guidelines for permanently destroying biometric data.

```typescript
// src/bipa-policy.ts
export function serveBipaPolicy(): Response {
  const policy = {
    statute: 'Illinois Biometric Information Privacy Act, 740 ILCS 14',
    last_updated: '2026-08-23',
    biometric_identifiers_collected: ['face_geometry'],
    retention_schedule: {
      rule: 'Destroyed within 3 years of collection, or when the initial purpose is fulfilled, whichever occurs first.',
      cite: '740 ILCS 14/15(a)',
    },
    destruction_method:
      'Cryptographic erasure of the AES-256 key wrapping each stored template, followed by hard deletion from D1.',
    sale_prohibition:
      'No biometric identifier or information is sold, leased, traded, or otherwise profited from. 740 ILCS 14/15(c).',
    disclosure_prohibition:
      'No disclosure to third parties without a written release or legal compulsion. 740 ILCS 14/15(d).',
    security:
      'Stored using protections at least as protective as those applied to other confidential and sensitive data. 740 ILCS 14/15(e).',
    contact: 'privacy@example.com',
  };

  return Response.json(policy, {
    headers: { 'Cache-Control': 'public, max-age=86400' },
  });
}
```

## Anti-patterns
- Collecting biometric data before written consent is received and logged — §15(b) requires *prior* consent
- Storing biometric templates indefinitely — a §15(a) violation accrues after the 3-year window
- Disclosing biometric data to a SaaS vendor without a separate written release per §15(d)
- Treating face geometry from uploaded photos as ordinary profile pictures requiring no consent
- Bundling biometric consent inside general terms of service without explicit, prominent notice
- Using biometric data for a new purpose not disclosed at initial consent time

## Gotchas
- BIPA applies to Illinois *residents* even when your company has no Illinois presence
- "Biometric identifier" includes face geometry extracted server-side from photos — not just fingerprint readers
- Private right of action: any aggrieved person may sue without waiting for state AG action
- Statutory damages: $1,000 per negligent violation, $5,000 per intentional or reckless violation, plus attorneys' fees
- The Illinois Supreme Court held in *Cothron v. White Castle* (2023) that each separate scan is a discrete violation, multiplying exposure dramatically
- Consent must state the specific purpose and retention period *before* any data is captured
- Employees are covered — workplace timekeeping systems are a primary litigation target

## Verification

```sql
-- Identify any biometric template stored without a matching active consent (BIPA §15(b) gap)
SELECT bt.user_id, bt.template_type, bt.created_at
FROM biometric_templates bt
LEFT JOIN bipa_consents bc
  ON bt.user_id = bc.user_id
  AND bt.template_type = bc.consent_type
  AND bc.revoked_at IS NULL
WHERE bc.id IS NULL;

-- Templates approaching 3-year destruction deadline (next 30 days)
SELECT user_id, consent_type,
       consented_at,
       DATE(consented_at, '+3 years') AS destroy_by
FROM bipa_consents
WHERE revoked_at IS NULL
  AND DATE(consented_at, '+3 years') BETWEEN DATE('now') AND DATE('now', '+30 days');

-- Recent purge audit trail
SELECT user_id, action, detail, occurred_at
FROM bipa_audit_log
WHERE action = 'biometric_purge'
ORDER BY occurred_at DESC
LIMIT 50;
```

## Related
- `data-retention-automated-deletion-workers.md`
- `gdpr-consent-management-cloudflare-workers.md`
- `hipaa-technical-safeguards-web-api.md`
- `age-verification-eu-digital-services-act.md`
- `audit-log-mandatory.md`

## Sources
- https://www.ilga.gov/legislation/ilcs/ilcs3.asp?ActID=3004&ChapterID=57
- https://ilga.gov/legislation/publicacts/fulltext.asp?Name=095-0994 (BIPA original text)
- https://law.justia.com/cases/illinois/supreme-court/2023/126004.html (Cothron v. White Castle, 2023)
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
