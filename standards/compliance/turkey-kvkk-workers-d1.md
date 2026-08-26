# Turkey KVKK Personal Data Protection — Cloudflare Workers D1

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

Your service processes personal data of individuals in Turkey or is incorporated in Turkey, triggering the Law on Protection of Personal Data (KVKK, Law No. 6698, in force since 7 April 2016), enforced by the Personal Data Protection Authority (Kişisel Verileri Koruma Kurumu, KVKK Board). Controllers established in Turkey must register in the Data Controllers Registry (VERBİS) before processing, maintain a processing inventory, obtain explicit consent or rely on another lawful basis, and notify the Board of breaches within 72 hours; administrative fines reach TRY 1,000,000 per violation (adjusted annually) and criminal penalties apply for unlawful processing and non-notification.

---

## Context

KVKK Law No. 6698 shares structural DNA with the EU GDPR (it pre-dates GDPR by one month) but differs in key areas:

- **VERBİS registration**: data controllers who meet the Board's thresholds must register their processing activities in the national registry before processing begins.
- **Explicit consent requirements**: similar to GDPR opt-in but with stricter form requirements — consent must be separate, specific, and not bundled with terms of service.
- **Special categories of personal data** (Art. 6): race/ethnic origin, political opinion, philosophical belief, religion/sect/other beliefs, clothing/dress, membership of association/foundation/union, health and sexual life, criminal convictions, biometric and genetic data — require explicit consent **or** Board permission.
- **Cross-border transfers** (Art. 9): restricted to countries that the Board has declared to have adequate protection (the "safe country" list), or with explicit consent, or with an undertaking letter submitted to the Board; standard contractual clauses are now available following a 2024 regulation.
- **Breach notification**: notify the Board within **72 hours** of awareness; notify affected data subjects as soon as practicable when the breach poses a high risk to individuals.
- **VERBİS threshold**: controllers with more than 50 employees or annual revenue exceeding TRY 25 million must register (thresholds updated by Board decision).

On Cloudflare Workers, the consent lifecycle, data subject rights pipeline, and breach notification clock all run in D1; cross-border transfer records and VERBİS inventory exports are stored in R2.

---

## 1. Lawful Basis Gate and Explicit Consent Lifecycle

KVKK Art. 5 lists processing conditions for ordinary personal data: explicit consent, express legal obligation, protection of vital interests, contractual necessity, legitimate interests balancing, and official duty. Art. 6 special-category data requires explicit consent **or** Board permission.

```typescript
// workers/kvkk-consent.ts
import { Env } from './types';

const KVKK_SPECIAL_CATEGORIES = [
  'race_ethnic_origin', 'political_opinion', 'philosophical_belief',
  'religion_sect_other_beliefs', 'clothing_dress',
  'association_foundation_union_membership',
  'health_data', 'sexual_life', 'criminal_conviction',
  'biometric_data', 'genetic_data',
] as const;
type KvkkSpecialCategory = typeof KVKK_SPECIAL_CATEGORIES[number];

type KvkkLawfulBasis =
  | 'explicit_consent' | 'legal_obligation' | 'vital_interests'
  | 'contractual_necessity' | 'legitimate_interests' | 'official_duty';

export async function recordKvkkConsent(
  env: Env,
  dataSubjectId: string,
  purpose: string,
  categories: string[],
  consentText: string,   // Must be a distinct, specific written statement
  isSpecialCategory: boolean,
  request: Request,
): Promise<string> {
  const id = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO kvkk_consent
     (id, data_subject_id, purpose, categories, consent_text,
      is_special_category, granted_at, revoked_at, ip_address, user_agent)
     VALUES (?, ?, ?, ?, ?, ?, datetime('now'), NULL, ?, ?)`,
  ).bind(
    id, dataSubjectId, purpose, JSON.stringify(categories), consentText,
    isSpecialCategory ? 1 : 0,
    request.headers.get('CF-Connecting-IP') ?? 'unknown',
    request.headers.get('User-Agent') ?? 'unknown',
  ).run();
  return id;
}

export async function revokeKvkkConsent(
  env: Env,
  dataSubjectId: string,
  purpose: string,
): Promise<void> {
  await env.DB.prepare(
    `UPDATE kvkk_consent SET revoked_at = datetime('now')
     WHERE data_subject_id = ? AND purpose = ? AND revoked_at IS NULL`,
  ).bind(dataSubjectId, purpose).run();
}

export async function hasActiveKvkkConsent(
  env: Env,
  dataSubjectId: string,
  purpose: string,
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM kvkk_consent
     WHERE data_subject_id = ? AND purpose = ? AND revoked_at IS NULL
     LIMIT 1`,
  ).bind(dataSubjectId, purpose).first();
  return row !== null;
}

export async function hasKvkkSpecialCategoryConsent(
  env: Env,
  dataSubjectId: string,
  category: KvkkSpecialCategory,
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM kvkk_consent
     WHERE data_subject_id = ? AND is_special_category = 1
       AND revoked_at IS NULL
       AND categories LIKE '%' || ? || '%'
     LIMIT 1`,
  ).bind(dataSubjectId, category).first();
  return row !== null;
}
```

---

## 2. Data Subject Rights — 30-Day Response Clock

KVKK Art. 11 grants data subjects the right to: learn whether data is processed, request information, learn the purpose and whether it is used in accordance with its purpose, know domestic/foreign recipients, request rectification, request erasure/destruction, object to automated processing producing an adverse result, and request compensation for damages. The controller must respond within **30 days** from the data subject's application; rejection is subject to appeal to the Board within 30 days of the controller's response.

```typescript
// workers/kvkk-dsr.ts
type KvkkRight =
  | 'learn_processing' | 'request_information' | 'learn_purpose'
  | 'learn_recipients' | 'rectification' | 'erasure_destruction'
  | 'object_automated_processing' | 'compensation_request';

interface KvkkDsrTicket {
  id: string;
  dataSubjectId: string;
  right: KvkkRight;
  receivedAt: string;
  deadlineAt: string;   // 30 days
  status: 'open' | 'completed' | 'denied';
  denialReason: string | null;
  completedAt: string | null;
}

export async function openKvkkRequest(
  env: Env,
  dataSubjectId: string,
  right: KvkkRight,
): Promise<KvkkDsrTicket> {
  const id = crypto.randomUUID();
  const now = new Date();
  const deadline = new Date(now.getTime() + 30 * 86_400_000);

  await env.DB.prepare(
    `INSERT INTO kvkk_dsr
     (id, data_subject_id, right, received_at, deadline_at, status)
     VALUES (?, ?, ?, ?, ?, 'open')`,
  ).bind(id, dataSubjectId, right, now.toISOString(), deadline.toISOString()).run();

  return {
    id, dataSubjectId, right,
    receivedAt: now.toISOString(),
    deadlineAt: deadline.toISOString(),
    status: 'open',
    denialReason: null,
    completedAt: null,
  };
}

export async function fulfillKvkkErasure(
  env: Env,
  ticketId: string,
  dataSubjectId: string,
): Promise<void> {
  // Anonymise in place; retain audit record per KVKK Art. 7
  await env.DB.prepare(
    `UPDATE users SET email = 'ERASED-' || id, name = 'ERASED',
      phone = NULL, address = NULL, erased_at = datetime('now')
     WHERE id = ?`,
  ).bind(dataSubjectId).run();

  await env.DB.prepare(
    `UPDATE kvkk_dsr SET status = 'completed', completed_at = datetime('now')
     WHERE id = ?`,
  ).bind(ticketId).run();
}

// Cron: alert on tickets approaching deadline
export async function alertKvkkDeadlines(env: Env): Promise<void> {
  const horizon = new Date(Date.now() + 5 * 86_400_000).toISOString();
  const { results } = await env.DB.prepare(
    `SELECT id, data_subject_id, right, deadline_at
     FROM kvkk_dsr WHERE status = 'open' AND deadline_at <= ?`,
  ).bind(horizon).all<{ id: string; data_subject_id: string; right: string; deadline_at: string }>();

  for (const r of results) {
    await env.ALERTS_QUEUE.send({ type: 'kvkk_deadline_warning', ...r });
  }
}
```

---

## 3. Breach Notification — 72-Hour Board Clock

KVKK Art. 12 requires notification to the Board within **72 hours** of becoming aware of a personal data breach. Notification to affected data subjects follows as soon as practicable and is published on the Board's website.

```typescript
// workers/kvkk-breach.ts
type KvkkBreachSeverity = 'low' | 'medium' | 'high' | 'critical';

interface KvkkBreachRecord {
  id: string;
  description: string;
  dataSubjectsAffected: number;
  dataCategories: string[];
  severity: KvkkBreachSeverity;
  discoveredAt: string;
  boardNotificationDeadline: string;  // 72 hours from discovery
  boardNotifiedAt: string | null;
  subjectsNotifiedAt: string | null;
  remediationSteps: string;
}

export async function recordKvkkBreach(
  env: Env,
  description: string,
  affectedCount: number,
  dataCategories: string[],
  severity: KvkkBreachSeverity,
  remediationSteps: string,
): Promise<KvkkBreachRecord> {
  const id = crypto.randomUUID();
  const discoveredAt = new Date().toISOString();
  const boardDeadline = new Date(Date.now() + 72 * 3_600_000).toISOString();

  await env.DB.prepare(
    `INSERT INTO kvkk_breach_log
     (id, description, data_subjects_affected, data_categories, severity,
      discovered_at, board_notification_deadline, remediation_steps)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
  ).bind(
    id, description, affectedCount, JSON.stringify(dataCategories),
    severity, discoveredAt, boardDeadline, remediationSteps,
  ).run();

  await env.ALERTS_QUEUE.send({
    type: 'kvkk_breach_72h_clock_started',
    breachId: id, boardDeadline, severity,
  });

  return {
    id, description, dataSubjectsAffected: affectedCount, dataCategories,
    severity, discoveredAt, boardNotificationDeadline: boardDeadline,
    boardNotifiedAt: null, subjectsNotifiedAt: null, remediationSteps,
  };
}

export async function markKvkkBreachBoardNotified(
  env: Env,
  breachId: string,
): Promise<void> {
  await env.DB.prepare(
    `UPDATE kvkk_breach_log SET board_notified_at = datetime('now') WHERE id = ?`,
  ).bind(breachId).run();
}
```

---

## 4. Cross-Border Transfer Record

KVKK Art. 9 prohibits transfers to foreign countries unless the destination country appears on the Board's adequacy list, or explicit consent is obtained, or an undertaking letter (taahhütname) is filed with the Board, or — since 2024 — standard contractual clauses approved by the Board are in place.

```typescript
// workers/kvkk-transfer.ts
type KvkkTransferMechanism =
  | 'adequacy_decision' | 'explicit_consent' | 'undertaking_letter' | 'standard_contractual_clauses';

interface KvkkTransferRecord {
  id: string;
  destinationCountry: string;
  recipientName: string;
  dataCategories: string[];
  purpose: string;
  mechanism: KvkkTransferMechanism;
  mechanismReference: string;   // adequacy country code, consent ID, undertaking ref, or SCC reference
  approvedAt: string;
  nextReviewAt: string;
}

export async function recordKvkkTransfer(
  env: Env,
  record: Omit<KvkkTransferRecord, 'id' | 'approvedAt'>,
): Promise<string> {
  const id = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO kvkk_transfer_register
     (id, destination_country, recipient_name, data_categories, purpose,
      mechanism, mechanism_reference, approved_at, next_review_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)`,
  ).bind(
    id, record.destinationCountry, record.recipientName,
    JSON.stringify(record.dataCategories), record.purpose,
    record.mechanism, record.mechanismReference, record.nextReviewAt,
  ).run();
  return id;
}

export async function exportKvkkTransferRegisterToR2(env: Env): Promise<string> {
  const { results } = await env.DB.prepare(
    `SELECT * FROM kvkk_transfer_register ORDER BY approved_at DESC`,
  ).all();
  const key = `kvkk/transfer-register-${new Date().toISOString().slice(0, 10)}.json`;
  await env.R2.put(key, JSON.stringify(results), {
    httpMetadata: { contentType: 'application/json' },
  });
  return key;
}
```

---

## Anti-patterns

- **Bundling KVKK consent with general terms of service.** The Board considers bundled consent invalid — the data subject must be shown a separate, standalone consent form for each processing purpose.
- **Processing special category data based only on "legitimate interests."** Legitimate interests is not a valid basis for special category data under KVKK; only explicit consent or a narrow list of Board-approved derogations apply.
- **Assuming VERBİS registration is a one-time act.** Controllers must update the VERBİS register whenever processing activities, categories, or purposes materially change; stale entries constitute a separate violation.
- **Sending data to countries not on the Board's adequacy list without an undertaking or SCC.** The Board's adequacy list is shorter than the GDPR list; a country deemed adequate under GDPR is not automatically safe under KVKK.
- **Counting 72 hours from containment rather than from awareness of the breach.** The clock starts at awareness of the security incident — it does not pause during forensic investigation.

---

## Gotchas

- The KVKK Board has extra-territorial reach for controllers targeting individuals in Turkey even when not established there, though enforcement mechanisms against foreign controllers remain limited in practice.
- VERBİS registration is **mandatory before processing begins** for threshold-meeting controllers — unlike GDPR's ROPA, which is an internal record, VERBİS is a public government registry.
- Health and sexual life data have a dual special-category status; processing them for health services requires separate Board authorisation in addition to explicit consent in many contexts.
- Cloudflare's Istanbul PoP (IST) may serve Turkish user requests; ensure that data written to D1 is stored in a region that does not trigger unintended cross-border transfer obligations under KVKK.
- Turkish law uses a 30-day DSR response period (not 45), and data subjects may appeal denied requests directly to the KVKK Board — maintaining a clear denial-reason audit trail is therefore critical.

---

## Verification

```bash
# 1. Open DSR tickets approaching 30-day deadline
wrangler d1 execute DB --command \
  "SELECT id, right, deadline_at FROM kvkk_dsr
   WHERE status = 'open' AND deadline_at <= datetime('now', '+5 days')
   ORDER BY deadline_at;"

# 2. Breach records without Board notification
wrangler d1 execute DB --command \
  "SELECT id, severity, board_notification_deadline, board_notified_at
   FROM kvkk_breach_log WHERE board_notified_at IS NULL
   ORDER BY discovered_at DESC;"

# 3. Cross-border transfer register
wrangler d1 execute DB --command \
  "SELECT destination_country, recipient_name, mechanism, next_review_at
   FROM kvkk_transfer_register ORDER BY next_review_at;"

# 4. Special category consent in force
wrangler d1 execute DB --command \
  "SELECT data_subject_id, categories, purpose, granted_at
   FROM kvkk_consent WHERE is_special_category = 1 AND revoked_at IS NULL
   ORDER BY granted_at DESC LIMIT 20;"
```

---

## Related

- `gdpr-data-subject-rights-api.md`
- `gdpr-breach-notification-72h.md`
- `cross-border-data-transfer-cloudflare-workers.md`
- `gdpr-consent-management-cloudflare-workers.md`
- `south-africa-popia-workers-d1.md`

---

## Sources

- Law on Protection of Personal Data (Law No. 6698): https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=6698&MevzuatTur=1&MevzuatTertip=5
- Personal Data Protection Authority (KVKK Board): https://www.kvkk.gov.tr/
- KVKK Cross-Border Transfer Regulation 2024: https://www.kvkk.gov.tr/Icerik/7333/Cross-Border-Transfer-Regulation
