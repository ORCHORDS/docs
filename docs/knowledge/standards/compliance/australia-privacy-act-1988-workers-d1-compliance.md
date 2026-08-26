# Australia Privacy Act 1988 (APPs) — Cloudflare Workers + D1 Compliance

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

example project has Australian users. The Privacy Act 1988 (Cth), enforced by the Office of the Australian Information Commissioner (OAIC), applies to entities with >AUD 3 M annual turnover **and** to any entity that trades in personal information regardless of turnover. The 13 Australian Privacy Principles (APPs) govern collection, use, disclosure, storage, access, and correction. A separate article covers the 2026 reform bill amendments; this article covers the **current enforceable obligations** as at August 2026 including the Notifiable Data Breaches (NDB) scheme.

---

## Context

Key APPs for a pseudonymous social platform:

| APP | Obligation |
|-----|-----------|
| APP 1 | Open and transparent management — publish a plain-English privacy policy |
| APP 3 | Collect only what is reasonably necessary; no unsolicited collection |
| APP 5 | Notify individuals at or before collection (collection notice) |
| APP 6 | Use/disclose only for the primary purpose or with consent |
| APP 11 | Take reasonable steps to protect personal information from misuse/loss/unauthorised access |
| APP 12 | Provide access to personal information held about an individual on request |
| APP 13 | Correct inaccurate/out-of-date personal information on request |

**NDB scheme (Part IIIC)**: If an eligible data breach is likely to result in serious harm to any individual, notify the OAIC and affected individuals as soon as practicable (no fixed 72-hour deadline, but OAIC expects prompt notification — typically within 30 days of becoming aware).

**Extraterritorial reach**: Applies to overseas organisations that collect personal information from Australian individuals and carry on business in Australia.

---

## 1 — Collection Minimisation and Notice (APP 3 & APP 5)

```typescript
// src/au/collection-notice.ts
// Served as a banner when an Australian IP is detected at sign-up

export const AU_COLLECTION_NOTICE = {
  controller: 'example project Platform Pty Ltd',
  regulator: 'Office of the Australian Information Commissioner (OAIC)',
  data_collected: ['pseudonymous handle', 'hashed email', 'IP country (not stored)', 'post content'],
  primary_purpose: 'Operate an anonymous social discussion platform',
  secondary_purposes: ['abuse prevention', 'legal compliance'],
  disclosure: 'Personal information may be disclosed to law enforcement under a valid court order.',
  overseas_disclosure: 'Data is stored on Cloudflare infrastructure globally; see privacy policy for countries.',
  access_correction: 'Submit requests to privacy@example project.example.com',
  policy_url: 'https://example project.example.com/privacy',
};

export function australianGeoDetected(cfCountry: string | null): boolean {
  return cfCountry === 'AU';
}
```

```typescript
// src/au/schema.sql — run once
CREATE TABLE IF NOT EXISTS au_collection_consents (
  id           TEXT PRIMARY KEY,
  account_id   TEXT NOT NULL,
  notice_shown INTEGER NOT NULL DEFAULT 0,  -- boolean: 1 = notice was shown
  notice_ts    INTEGER,
  created_at   INTEGER NOT NULL DEFAULT (unixepoch())
);
```

---

## 2 — Access Request Handler (APP 12)

```typescript
// src/au/app12-access.ts
import type { D1Database } from '@cloudflare/workers-types';

// Individuals may request access to all personal information held about them.
// The entity must respond within 30 days.

export async function handleAccessRequest(
  db: D1Database,
  accountId: string,
): Promise<Record<string, unknown>> {
  const [profile, posts, consents] = await Promise.all([
    db.prepare(
      `SELECT pseudonym, email_hash, created_at FROM accounts WHERE id = ?`,
    ).bind(accountId).first(),
    db.prepare(
      `SELECT post_id, body_hash, created_at FROM posts WHERE account_id = ?`,
    ).bind(accountId).all(),
    db.prepare(
      `SELECT notice_shown, notice_ts FROM au_collection_consents WHERE account_id = ?`,
    ).bind(accountId).all(),
  ]);

  await db.prepare(
    `INSERT INTO dsr_log (account_id, law, type, requested_at)
     VALUES (?, 'AU-PRIVACY-ACT-1988', 'APP12_ACCESS', ?)`,
  ).bind(accountId, Math.floor(Date.now() / 1000)).run();

  return {
    export_date: new Date().toISOString(),
    law: 'Privacy Act 1988 (Cth) — APP 12',
    profile,
    posts: posts.results,
    collection_consents: consents.results,
  };
}
```

---

## 3 — Correction Request Handler (APP 13)

```typescript
// src/au/app13-correction.ts

export interface CorrectionRequest {
  accountId: string;
  field: 'pseudonym' | 'email_hash';
  newValue: string;
  reason: string;
}

export async function handleCorrectionRequest(
  db: D1Database,
  req: CorrectionRequest,
): Promise<{ corrected: boolean; note?: string }> {
  const allowed = ['pseudonym', 'email_hash'] as const;
  if (!allowed.includes(req.field)) {
    return { corrected: false, note: 'Field not correctable via this endpoint.' };
  }

  // example project may refuse correction of post content if it relates to ongoing moderation
  const modAction = await db.prepare(
    `SELECT id FROM moderation_actions WHERE account_id = ? AND status = 'active' LIMIT 1`,
  ).bind(req.accountId).first();
  if (modAction) {
    await db.prepare(
      `INSERT INTO dsr_log (account_id, law, type, requested_at, outcome)
       VALUES (?, 'AU-PRIVACY-ACT-1988', 'APP13_CORRECTION', ?, 'refused_moderation')`,
    ).bind(req.accountId, Math.floor(Date.now() / 1000)).run();
    return { corrected: false, note: 'Correction refused during active moderation review.' };
  }

  await db.prepare(
    `UPDATE accounts SET ${req.field} = ?, updated_at = ? WHERE id = ?`,
  ).bind(req.newValue, Math.floor(Date.now() / 1000), req.accountId).run();

  await db.prepare(
    `INSERT INTO dsr_log (account_id, law, type, requested_at, outcome)
     VALUES (?, 'AU-PRIVACY-ACT-1988', 'APP13_CORRECTION', ?, 'corrected')`,
  ).bind(req.accountId, Math.floor(Date.now() / 1000)).run();

  return { corrected: true };
}
```

---

## 4 — Notifiable Data Breach (NDB) Assessment and Notification

```typescript
// src/au/ndb.ts
// Privacy Act 1988 Part IIIC — Notifiable Data Breaches scheme

export interface NDBEvent {
  incident_id: string;
  detected_at: number;           // Unix epoch
  data_categories: string[];
  estimated_affected_au: number; // Australian users specifically
  description: string;
  serious_harm_likely: boolean;  // Must assess this
}

export async function assessAndEnqueueNDB(
  env: { example project_DB: D1Database; NDB_QUEUE: Queue<NDBEvent> },
  event: NDBEvent,
): Promise<void> {
  // Only notifiable if serious harm to at least one individual is "likely"
  if (!event.serious_harm_likely) {
    await env.example project_DB.prepare(
      `INSERT INTO ndb_assessments (incident_id, outcome, assessed_at)
       VALUES (?, 'no_notification_required', ?)`,
    ).bind(event.incident_id, Math.floor(Date.now() / 1000)).run();
    return;
  }

  // OAIC expects notification "as soon as practicable" — target <30 days
  await env.NDB_QUEUE.send(event, { delaySeconds: 0 });
  await env.example project_DB.prepare(
    `INSERT INTO ndb_assessments (incident_id, outcome, assessed_at, queued_at)
     VALUES (?, 'notification_required', ?, ?)`,
  ).bind(
    event.incident_id,
    event.detected_at,
    Math.floor(Date.now() / 1000),
  ).run();
}

export function buildOAICNotificationPayload(event: NDBEvent): Record<string, unknown> {
  return {
    entity_name: 'example project Platform',
    abn: process.env.AU_ABN,
    contact_email: 'privacy@example project.example.com',
    incident_id: event.incident_id,
    date_detected: new Date(event.detected_at * 1000).toISOString(),
    description: event.description,
    data_categories: event.data_categories,
    estimated_affected_au: event.estimated_affected_au,
    recommended_action_for_individuals: 'Monitor accounts for unusual activity.',
    oaic_notification_form_url: 'https://www.oaic.gov.au/privacy/notifiable-data-breaches/notify',
  };
}
```

---

## 5 — APP 11 Security — Encryption at Rest for D1

```typescript
// src/au/app11-security.ts
// APP 11 requires "reasonable steps" — encryption of PII columns in D1 satisfies this.

export async function encryptPII(value: string, key: CryptoKey): Promise<string> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encoded = new TextEncoder().encode(value);
  const cipher = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, encoded);
  const combined = new Uint8Array(iv.byteLength + cipher.byteLength);
  combined.set(iv, 0);
  combined.set(new Uint8Array(cipher), iv.byteLength);
  return btoa(String.fromCharCode(...combined));
}

export async function decryptPII(cipherB64: string, key: CryptoKey): Promise<string> {
  const raw = Uint8Array.from(atob(cipherB64), (c) => c.charCodeAt(0));
  const iv = raw.slice(0, 12);
  const cipher = raw.slice(12);
  const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, cipher);
  return new TextDecoder().decode(plain);
}

// Usage: store encryptPII(email, AES_KEY) in D1; decrypt only for DSR responses.
```

---

## 6 — Overseas Disclosure Register (APP 8)

```typescript
// src/au/overseas-disclosure.ts
// APP 8: Before disclosing PI overseas, take reasonable steps to ensure the
// overseas recipient complies with APPs, OR rely on explicit consent.

export const OVERSEAS_RECIPIENTS = [
  { name: 'Cloudflare Inc.', country: 'US', basis: 'contractual_safeguards', dpa_in_place: true },
  { name: 'Cloudflare D1 (EU region)', country: 'EU', basis: 'contractual_safeguards', dpa_in_place: true },
];

export async function logOverseasDisclosure(
  db: D1Database,
  accountId: string,
  recipientName: string,
  country: string,
): Promise<void> {
  await db.prepare(
    `INSERT INTO overseas_disclosures (account_id, recipient, country, disclosed_at)
     VALUES (?, ?, ?, ?)`,
  ).bind(accountId, recipientName, country, Math.floor(Date.now() / 1000)).run();
}
```

---

## Anti-patterns

- **Assuming pseudonymous = not personal information**: Under Australian law, if a handle can be linked back to an identifiable individual, it is personal information. example project email-to-handle mappings must be protected under the APPs.
- **No collection notice for Australian IPs**: APP 5 requires notification at or before the point of collection. A post-registration email does not satisfy "at collection time."
- **Treating NDB as having a fixed 72-hour window**: The Australian scheme says "as soon as practicable." OAIC guidance indicates this is usually within 30 days of awareness, but deliberate delay is penalised.
- **Missing records of overseas disclosures**: APP 8 liability extends to the overseas recipient's actions if you have not taken reasonable steps before disclosing.

---

## Gotchas

- **Small business exemption does not apply to data brokers**: If example project sells or monetises personal information in any way, the <$3 M exemption is lost.
- **Sensitive information** (health, political opinion, sexual orientation, biometric) requires explicit consent for collection — even if a user volunteers it in a post.
- **Employee records exemption is narrow**: example project staff records are partially exempt, but only for employment-relationship purposes.
- **OAIC can investigate on its own initiative**: No individual complaint needed. High-profile breaches trigger OAIC-initiated investigations.
- **Repeat contraventions**: Multiple serious or repeated interferences carry civil penalties up to AUD 50 M (as amended by the Privacy Legislation Amendment Act 2022).

---

## Verification

```bash
# Confirm AU DSR log exists
wrangler d1 execute example project_DB \
  --command "SELECT law, type, COUNT(*) FROM dsr_log WHERE law = 'AU-PRIVACY-ACT-1988' GROUP BY type;"

# Check NDB assessments
wrangler d1 execute example project_DB \
  --command "SELECT incident_id, outcome FROM ndb_assessments ORDER BY assessed_at DESC LIMIT 10;"

# Verify overseas disclosure log
wrangler d1 execute example project_DB \
  --command "SELECT recipient, country, COUNT(*) c FROM overseas_disclosures GROUP BY country;"
```

---

## Related

- `australia-privacy-act-reform-2026.md` — Upcoming amendments (enhanced rights, mandatory DPIA, etc.)
- `gdpr-right-to-erasure-d1-r2-pipeline.md` — Erasure pipeline applicable to APP 12 deletion
- `data-retention-automated-deletion-workers.md` — Auto-purge aligns with APP 11 data minimisation
- `cross-border-data-transfer-mechanisms.md` — APP 8 safeguards

---

## Sources

- Privacy Act 1988 (Cth): <https://www.legislation.gov.au/Series/C2004A03712>
- OAIC — Australian Privacy Principles Guidelines: <https://www.oaic.gov.au/privacy/australian-privacy-principles-guidelines>
- OAIC — Notifiable Data Breaches Scheme: <https://www.oaic.gov.au/privacy/notifiable-data-breaches>
- Privacy Legislation Amendment (Enhancing Online Privacy and Other Measures) Act 2022
