# Delaware Personal Data Privacy Act (DPDPA) — Cloudflare Workers D1

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

Your service processes personal data of Delaware residents and meets either threshold under the Delaware Personal Data Privacy Act (DPDPA, House Bill 154, 6 Del. C. §§ 12D-101 et seq., effective 1 January 2025): (a) control or process personal data of 35,000+ Delaware consumers per calendar year, or (b) control or process data of 10,000+ Delaware consumers while deriving over 20 % of gross revenue from selling personal data. The DPDPA includes some of the lowest population thresholds in US state privacy law and extends obligations to nonprofit organisations, making it unusually broad in applicability.

---

## Context

The DPDPA is enforced by the Delaware AG with a **60-day cure period** expiring 31 December 2025 — after that date, the AG may bring suit without prior written notice. Civil penalties reach USD 10,000 per violation. Key characteristics distinguishing DPDPA from peer laws:

- **Nonprofit inclusion**: unlike most state laws, the DPDPA applies to nonprofits meeting the thresholds (with limited exceptions for public-benefit purposes).
- **Lower thresholds**: 35,000 consumers (vs 100,000 in many states) and 10,000 + 20 % revenue trigger (vs 25,000 + 50 % in Virginia/Indiana).
- **Sensitive data** (§ 12D-101(20)): racial/ethnic origin, religious beliefs, mental/physical health diagnosis, sexual orientation, citizenship/immigration status, genetic/biometric data, children's data under 13, precise geolocation, status as transgender/nonbinary — requires **opt-in consent**.
- **Consumer rights**: access, correct, delete, port, opt out of sale, targeted advertising, and profiling with legal or substantial effects.
- **Response deadline**: 45 days, extendable once by 45 days with notice.
- **Children**: enhanced protections for data of consumers under 18 known to be minors — no targeted advertising or profiling without opt-in.

---

## 1. Threshold Evaluation at Runtime

Because the DPDPA thresholds are lower than most peer laws, a service may be subject to DPDPA while not yet subject to other state laws. A Worker computes running counts in D1.

```typescript
// workers/dpdpa-threshold-check.ts
import { Env } from './types';

interface ThresholdResult {
  subject: boolean;
  consumerCount: number;
  revenuePercent: number | null;
  basis: 'consumer_count' | 'revenue_and_count' | 'not_subject';
}

export async function checkDpdpaThreshold(env: Env): Promise<ThresholdResult> {
  const yearStart = new Date(new Date().getFullYear(), 0, 1).toISOString();

  const countRow = await env.DB.prepare(
    `SELECT COUNT(DISTINCT consumer_id) AS cnt
     FROM consumer_events
     WHERE state_code = 'DE'
       AND occurred_at >= ?`,
  )
    .bind(yearStart)
    .first<{ cnt: number }>();

  const consumerCount = countRow?.cnt ?? 0;

  if (consumerCount >= 35000) {
    return { subject: true, consumerCount, revenuePercent: null, basis: 'consumer_count' };
  }

  if (consumerCount >= 10000) {
    const revRow = await env.DB.prepare(
      `SELECT sale_revenue_pct FROM annual_revenue_snapshots
       WHERE year = ? ORDER BY recorded_at DESC LIMIT 1`,
    )
      .bind(new Date().getFullYear())
      .first<{ sale_revenue_pct: number }>();

    const pct = revRow?.sale_revenue_pct ?? 0;
    if (pct >= 20) {
      return { subject: true, consumerCount, revenuePercent: pct, basis: 'revenue_and_count' };
    }
  }

  return { subject: false, consumerCount, revenuePercent: null, basis: 'not_subject' };
}
```

---

## 2. Sensitive Data Opt-In Consent (Including Transgender/Nonbinary Status)

The DPDPA adds transgender or nonbinary status to its sensitive data list — a category not present in most peer laws. Consent must be granular per category.

```typescript
// workers/dpdpa-sensitive-consent.ts
import { Env } from './types';

type DpdpaSensitiveCategory =
  | 'racial_ethnic_origin'
  | 'religious_beliefs'
  | 'mental_physical_health'
  | 'sexual_orientation'
  | 'transgender_nonbinary_status'
  | 'citizenship_immigration'
  | 'genetic_data'
  | 'biometric_data'
  | 'childrens_data'
  | 'precise_geolocation';

export async function hasDpdpaSensitiveConsent(
  env: Env,
  consumerId: string,
  category: DpdpaSensitiveCategory,
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM dpdpa_sensitive_consents
     WHERE consumer_id = ?
       AND category = ?
       AND revoked_at IS NULL
       AND expires_at > datetime('now')
     LIMIT 1`,
  )
    .bind(consumerId, category)
    .first<{ 1: number }>();
  return row !== null;
}

export async function grantDpdpaSensitiveConsent(
  env: Env,
  consumerId: string,
  category: DpdpaSensitiveCategory,
  consentText: string,
): Promise<void> {
  const expiresAt = new Date(Date.now() + 365 * 24 * 60 * 60 * 1000).toISOString();
  const textHash = await sha256(consentText);
  await env.DB.prepare(
    `INSERT INTO dpdpa_sensitive_consents
     (id, consumer_id, category, consent_text_hash, granted_at, expires_at)
     VALUES (?, ?, ?, ?, datetime('now'), ?)`,
  )
    .bind(crypto.randomUUID(), consumerId, category, textHash, expiresAt)
    .run();
}

async function sha256(text: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
}
```

---

## 3. Minor Consumer Protections (Under 18)

The DPDPA prohibits targeted advertising or profiling of consumers under 18 without opt-in consent — stricter than the children-under-13 threshold in most peer laws.

```typescript
// workers/dpdpa-minor-guard.ts
import { Env } from './types';

export async function isDpdpaMinor(env: Env, consumerId: string): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT birth_year FROM consumer_profiles WHERE consumer_id = ? LIMIT 1`,
  )
    .bind(consumerId)
    .first<{ birth_year: number }>();

  if (!row) return false; // unknown age: treat as adult, but see Gotchas
  return new Date().getFullYear() - row.birth_year < 18;
}

export async function hasDpdpaMinorAdConsent(
  env: Env,
  consumerId: string,
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM dpdpa_minor_ad_consents
     WHERE consumer_id = ? AND revoked_at IS NULL LIMIT 1`,
  )
    .bind(consumerId)
    .first<{ 1: number }>();
  return row !== null;
}

// Gate: block targeted ad targeting of known minors without consent
export async function dpdpaAdGuard(
  env: Env,
  consumerId: string,
): Promise<{ allowed: boolean; reason: string }> {
  if (await isDpdpaMinor(env, consumerId)) {
    if (!(await hasDpdpaMinorAdConsent(env, consumerId))) {
      return { allowed: false, reason: 'dpdpa_minor_no_consent' };
    }
  }
  return { allowed: true, reason: 'ok' };
}
```

---

## 4. Consumer Rights Fulfilment Pipeline

```typescript
// workers/dpdpa-rights-pipeline.ts
import { Env } from './types';

type DpdpaRight =
  | 'access'
  | 'correct'
  | 'delete'
  | 'port'
  | 'opt_out_sale'
  | 'opt_out_targeted_ads'
  | 'opt_out_profiling';

export async function submitDpdpaRightsRequest(
  env: Env,
  consumerId: string,
  right: DpdpaRight,
  payload: Record<string, unknown>,
): Promise<{ requestId: string; deadline: string }> {
  const requestId = crypto.randomUUID();
  const deadline = new Date(Date.now() + 45 * 24 * 60 * 60 * 1000).toISOString();

  await env.DB.prepare(
    `INSERT INTO dpdpa_rights_requests
     (id, consumer_id, right_type, payload_json, status, submitted_at, deadline_at)
     VALUES (?, ?, ?, ?, 'open', datetime('now'), ?)`,
  )
    .bind(requestId, consumerId, right, JSON.stringify(payload), deadline)
    .run();

  await env.RIGHTS_QUEUE.send({ source: 'dpdpa', requestId, consumerId, right });
  return { requestId, deadline };
}

export async function closeDpdpaRightsRequest(
  env: Env,
  requestId: string,
  outcome: 'fulfilled' | 'denied' | 'extended',
  note: string,
): Promise<void> {
  await env.DB.prepare(
    `UPDATE dpdpa_rights_requests
     SET status = ?, outcome_note = ?, closed_at = datetime('now')
     WHERE id = ?`,
  )
    .bind(outcome, note, requestId)
    .run();
}
```

---

## 5. Nonprofit Applicability Check

The DPDPA's nonprofit inclusion is unusual. The Worker checks entity type stored at configuration time to decide whether DPDPA obligations apply.

```typescript
// workers/dpdpa-entity-check.ts
import { Env } from './types';

interface EntityConfig {
  entityType: 'for_profit' | 'nonprofit' | 'government' | 'small_business';
  deExemptNonprofit: boolean; // true only for specific public-benefit exemptions
}

export async function isDpdpaApplicable(env: Env): Promise<boolean> {
  const cfg = await env.DB.prepare(
    `SELECT entity_type, de_exempt_nonprofit
     FROM entity_config LIMIT 1`,
  ).first<{ entity_type: string; de_exempt_nonprofit: number }>();

  if (!cfg) throw new Error('entity_config not initialised');

  // Government entities are exempt
  if (cfg.entity_type === 'government') return false;

  // Nonprofits that qualify for the specific DE public-benefit exemption are excluded
  if (cfg.entity_type === 'nonprofit' && cfg.de_exempt_nonprofit === 1) return false;

  // All other entities (including most nonprofits) are subject if thresholds are met
  return true;
}
```

---

## Anti-patterns

- **Assuming nonprofits are exempt**: the DPDPA explicitly covers nonprofits in scope — verify whether your organisation qualifies for one of the narrow public-benefit carve-outs.
- **Applying a 100,000-consumer threshold**: the DPDPA's primary threshold is only 35,000 consumers — implement monitoring before reaching that lower bar.
- **Treating transgender/nonbinary status as non-sensitive**: this category requires opt-in consent in Delaware even though most peer state laws omit it.
- **Applying only a 13-year-old threshold for minor protections**: the DPDPA extends enhanced protections to all consumers known to be under 18, not just under 13.

---

## Gotchas

- **Cure sunset**: the 60-day cure right expired 31 December 2025 — any violation after that date may be pursued by the AG without prior notice.
- **Unknown age**: if your platform does not collect age and cannot determine whether a consumer is under 18, adopt a conservative posture for Delaware residents exposed to profiling and targeted advertising.
- **Revenue percentage threshold**: the 20 % revenue trigger is lower than most peer laws (which use 50 %) — a platform monetising through any personal-data sale should check this threshold carefully.
- **example project anonymous posts**: posts that cannot be linked back to an individual fall outside scope, but any telemetry, device fingerprints, or IP addresses collected alongside a post remain personal data subject to DPDPA.

---

## Verification

```sql
-- Check current Delaware consumer count against threshold
SELECT COUNT(DISTINCT consumer_id) AS de_count
FROM consumer_events
WHERE state_code = 'DE'
  AND occurred_at >= datetime('now', 'start of year');

-- Confirm all open requests are within 45-day deadline
SELECT id, right_type, deadline_at
FROM dpdpa_rights_requests
WHERE status = 'open'
  AND deadline_at < datetime('now');

-- Audit sensitive consent for transgender/nonbinary category
SELECT consumer_id, granted_at, expires_at
FROM dpdpa_sensitive_consents
WHERE category = 'transgender_nonbinary_status'
  AND revoked_at IS NULL
  AND expires_at > datetime('now');
```

---

## Related

- `indiana-idcpa-workers-d1.md` — comparable threshold and opt-in sensitive data structure
- `connecticut-ctdpa-data-rights-workers.md` — another early-effective northeast US state law
- `childrens-privacy-2026-coppa-2-state-laws.md` — under-18 protections across state laws
- `us-state-privacy-laws-2026-multi-state-compliance.md` — multi-state orchestration
- `data-minimization-workers-d1-pii-redaction.md` — minimisation best practices

---

## Sources

- Delaware House Bill 154 (2023), 6 Del. C. §§ 12D-101 – 12D-121, effective 1 January 2025
- Delaware Department of Justice — Consumer Protection: <https://attorneygeneral.delaware.gov/fraud/cpu/>
- IAPP US State Privacy Law Tracker: <https://iapp.org/resources/article/us-state-privacy-legislation-tracker/>
- National Conference of State Legislatures — Consumer Data Privacy Laws: <https://www.ncsl.org/technology-and-communication/consumer-data-protection-legislation>
