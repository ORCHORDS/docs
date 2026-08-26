# Texas TDPSA Consumer Privacy — Cloudflare Workers D1

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

Your service conducts business in Texas or produces products and services targeted to Texas residents, processes or sells personal data, and does not qualify as a "small business" as defined by the US Small Business Administration — triggering the Texas Data Privacy and Security Act (TDPSA, HB 4, Tex. Bus. & Com. Code Ch. 541, effective 1 July 2024). The TDPSA grants Texans rights of access, correction, deletion, portability, and opt-out of sale, targeted advertising, and profiling with legal or similarly significant effects; the Texas AG enforces the law with civil penalties up to USD 7,500 per violation, plus actual damages, after a 30-day cure window.

---

## Context

TDPSA is unique in its **small-business exemption structure**: rather than setting a numerical consumer-volume threshold, it exempts businesses that the SBA classifies as a "small business" in their industry — a controller must affirmatively determine it does not qualify before assuming the Act applies. Once the Act applies, the obligations closely track VCDPA with notable differences:

- **Biometric data** is explicitly listed as sensitive and requires opt-in consent.
- **Cure period**: 30 days written notice required before the AG may bring an action (no sunset — the cure period does not expire unlike Connecticut).
- **Appeal**: controllers must establish an internal appeal process; the consumer has the right to appeal a denied DSR.
- **Universal opt-out**: controllers must respect universal opt-out mechanisms (e.g., browser signals) if adopted — not mandated by statute but implementation-ready.
- **Data protection assessments (DPAs)**: required before targeted advertising, sale, profiling with significant effects, sensitive data processing, and any other high-risk processing.
- **Response deadline**: 45 calendar days, extendable once by 45 days with written notice.

---

## 1. SBA Small-Business Exemption Check

Before applying TDPSA controls, verify that your business exceeds the SBA size standard for your NAICS code. Log the determination for compliance records.

```typescript
// workers/tdpsa-threshold.ts
import { Env } from './types';

interface TdpsaExemptionRecord {
  naicsCode: string;
  sbaEmployeeSizeStandard: number;    // SBA employee threshold for the code
  sbaRevenueSizeStandardUsd: number;  // SBA revenue threshold where applicable
  actualEmployeeCount: number;
  actualAnnualRevenueUsd: number;
  qualifiesAsSmallBusiness: boolean;
  determinedAt: string;
  determinedBy: string;
}

export async function recordTdpsaExemptionDetermination(
  env: Env,
  record: Omit<TdpsaExemptionRecord, 'determinedAt'>,
): Promise<string> {
  const id = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO tdpsa_exemption_determination
     (id, naics_code, sba_employee_size_standard, sba_revenue_size_standard_usd,
      actual_employee_count, actual_annual_revenue_usd,
      qualifies_as_small_business, determined_at, determined_by)
     VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)`,
  ).bind(
    id, record.naicsCode, record.sbaEmployeeSizeStandard,
    record.sbaRevenueSizeStandardUsd, record.actualEmployeeCount,
    record.actualAnnualRevenueUsd,
    record.qualifiesAsSmallBusiness ? 1 : 0, record.determinedBy,
  ).run();
  return id;
}
```

---

## 2. Sensitive Data Opt-In Gate

TDPSA § 541.101 defines sensitive categories requiring explicit opt-in consent before collection or processing: racial/ethnic origin, religious beliefs, mental/physical health diagnoses, sex life/sexual orientation, immigration status, genetic data, **biometric data**, children's data, and precise geolocation.

```typescript
// workers/tdpsa-sensitive-consent.ts
const TDPSA_SENSITIVE_CATEGORIES = [
  'racial_ethnic_origin', 'religious_belief', 'mental_health_diagnosis',
  'physical_health_diagnosis', 'sex_life_sexual_orientation',
  'immigration_status', 'genetic_data', 'biometric_data',
  'childrens_data', 'precise_geolocation',
] as const;
type TdpsaSensitiveCategory = typeof TDPSA_SENSITIVE_CATEGORIES[number];

export async function grantTdpsaSensitiveConsent(
  env: Env,
  consumerId: string,
  categories: TdpsaSensitiveCategory[],
  purpose: string,
  consentText: string,
  request: Request,
): Promise<string> {
  const id = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO tdpsa_sensitive_consent
     (id, consumer_id, categories, purpose, consent_text,
      granted_at, revoked_at, ip_address, user_agent)
     VALUES (?, ?, ?, ?, ?, datetime('now'), NULL, ?, ?)`,
  ).bind(
    id, consumerId, JSON.stringify(categories), purpose, consentText,
    request.headers.get('CF-Connecting-IP') ?? 'unknown',
    request.headers.get('User-Agent') ?? 'unknown',
  ).run();
  return id;
}

export async function hasTdpsaSensitiveConsent(
  env: Env,
  consumerId: string,
  category: TdpsaSensitiveCategory,
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM tdpsa_sensitive_consent
     WHERE consumer_id = ? AND revoked_at IS NULL
       AND categories LIKE '%' || ? || '%'
     LIMIT 1`,
  ).bind(consumerId, category).first();
  return row !== null;
}

export async function revokeTdpsaSensitiveConsent(
  env: Env,
  consumerId: string,
  category: TdpsaSensitiveCategory,
): Promise<void> {
  await env.DB.prepare(
    `UPDATE tdpsa_sensitive_consent SET revoked_at = datetime('now')
     WHERE consumer_id = ? AND revoked_at IS NULL
       AND categories LIKE '%' || ? || '%'`,
  ).bind(consumerId, category).run();
}
```

---

## 3. Consumer Rights — 45-Day Clock with Mandatory Appeal Process

```typescript
// workers/tdpsa-dsr.ts
type TdpsaRight =
  | 'access' | 'correction' | 'deletion'
  | 'portability' | 'opt_out_sale'
  | 'opt_out_targeted_advertising' | 'opt_out_profiling';

interface TdpsaDsrTicket {
  id: string;
  consumerId: string;
  right: TdpsaRight;
  receivedAt: string;
  deadlineAt: string;              // 45 days
  extendedDeadlineAt: string | null;  // up to 90 days total
  appealDeadlineAt: string | null;    // must offer appeal after denial
  status: 'open' | 'extended' | 'denied' | 'appeal_pending' | 'completed';
  denialReason: string | null;
}

export async function openTdpsaRequest(
  env: Env,
  consumerId: string,
  right: TdpsaRight,
): Promise<TdpsaDsrTicket> {
  const id = crypto.randomUUID();
  const now = new Date();
  const deadline = new Date(now.getTime() + 45 * 86_400_000);

  await env.DB.prepare(
    `INSERT INTO tdpsa_dsr
     (id, consumer_id, right, received_at, deadline_at, status)
     VALUES (?, ?, ?, ?, ?, 'open')`,
  ).bind(id, consumerId, right, now.toISOString(), deadline.toISOString()).run();

  return {
    id, consumerId, right,
    receivedAt: now.toISOString(),
    deadlineAt: deadline.toISOString(),
    extendedDeadlineAt: null,
    appealDeadlineAt: null,
    status: 'open',
    denialReason: null,
  };
}

export async function extendTdpsaRequest(
  env: Env,
  ticketId: string,
): Promise<void> {
  const newDeadline = new Date(Date.now() + 45 * 86_400_000).toISOString();
  await env.DB.prepare(
    `UPDATE tdpsa_dsr
     SET status = 'extended', extended_deadline_at = ?
     WHERE id = ? AND status = 'open'`,
  ).bind(newDeadline, ticketId).run();
}

export async function denyTdpsaRequest(
  env: Env,
  ticketId: string,
  reason: string,
): Promise<void> {
  // Controller must notify consumer of appeal right
  const appealDeadline = new Date(Date.now() + 45 * 86_400_000).toISOString();
  await env.DB.prepare(
    `UPDATE tdpsa_dsr
     SET status = 'denied', denial_reason = ?, appeal_deadline_at = ?
     WHERE id = ?`,
  ).bind(reason, appealDeadline, ticketId).run();
}

export async function fulfillTdpsaDeletion(
  env: Env,
  ticketId: string,
  consumerId: string,
): Promise<void> {
  await env.DB.prepare(
    `UPDATE users SET email = 'ERASED-' || id, name = 'ERASED',
      phone = NULL, erased_at = datetime('now')
     WHERE id = ?`,
  ).bind(consumerId).run();

  await env.DB.prepare(
    `UPDATE tdpsa_dsr SET status = 'completed', completed_at = datetime('now')
     WHERE id = ?`,
  ).bind(ticketId).run();
}

export async function exportTdpsaPortability(
  env: Env,
  ticketId: string,
  consumerId: string,
): Promise<string> {
  const profile = await env.DB.prepare(
    `SELECT id, email, name, phone, created_at FROM users WHERE id = ?`,
  ).bind(consumerId).first<Record<string, unknown>>();

  const { results: consents } = await env.DB.prepare(
    `SELECT purpose, categories, granted_at, revoked_at
     FROM tdpsa_sensitive_consent WHERE consumer_id = ?`,
  ).bind(consumerId).all();

  const payload = JSON.stringify({ profile, consents });
  const key = `tdpsa-portability/${consumerId}/${ticketId}.json`;
  await env.R2.put(key, payload, { httpMetadata: { contentType: 'application/json' } });

  await env.DB.prepare(
    `UPDATE tdpsa_dsr SET status = 'completed', r2_export_key = ?,
     completed_at = datetime('now') WHERE id = ?`,
  ).bind(key, ticketId).run();

  return key;
}

// Cron: alert on tickets approaching deadline
export async function alertTdpsaDeadlines(env: Env): Promise<void> {
  const horizon = new Date(Date.now() + 5 * 86_400_000).toISOString();
  const { results } = await env.DB.prepare(
    `SELECT id, consumer_id, right,
            COALESCE(extended_deadline_at, deadline_at) AS effective_deadline
     FROM tdpsa_dsr
     WHERE status IN ('open', 'extended')
       AND COALESCE(extended_deadline_at, deadline_at) <= ?`,
  ).bind(horizon).all<{ id: string; consumer_id: string; right: string; effective_deadline: string }>();

  for (const r of results) {
    await env.ALERTS_QUEUE.send({ type: 'tdpsa_deadline_warning', ...r });
  }
}
```

---

## 4. Data Protection Assessment Registry

```typescript
// workers/tdpsa-dpa-registry.ts
type TdpsaDpaActivity =
  | 'targeted_advertising' | 'sale_of_personal_data'
  | 'profiling_significant_effects' | 'sensitive_data_processing'
  | 'other_heightened_risk';

export async function registerTdpsaDpa(
  env: Env,
  activity: TdpsaDpaActivity,
  purpose: string,
  benefitsAssessed: string,
  risksIdentified: string,
  mitigationsApplied: string,
  netBenefitPositive: boolean,
  approvedBy: string,
  nextReviewDate: string,
): Promise<string> {
  const id = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO tdpsa_dpa_registry
     (id, activity, purpose, benefits_assessed, risks_identified,
      mitigations_applied, net_benefit_positive, approved_by,
      completed_at, next_review_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)`,
  ).bind(
    id, activity, purpose, benefitsAssessed, risksIdentified,
    mitigationsApplied, netBenefitPositive ? 1 : 0,
    approvedBy, nextReviewDate,
  ).run();
  return id;
}
```

---

## Anti-patterns

- **Assuming a revenue or consumer-volume threshold applies.** TDPSA uses the SBA small-business test, not a fixed number of consumers — a high-revenue company with few employees can be exempt, and a low-revenue company with many employees may not be; document the determination.
- **Collecting biometric data for internal security without opt-in consent.** TDPSA's biometric sensitive-data category has no internal-security carve-out; explicit opt-in is required before any biometric data is processed.
- **Missing the mandatory internal appeal pathway.** After denying a consumer request, the controller must provide a means for the consumer to appeal the decision inside the organisation before escalating to the AG.
- **Conflating the 30-day cure window with a grace period.** The cure window requires the AG to give notice before suing; it does not excuse the underlying violation, and repeat violations are treated more harshly.
- **Not recording the SBA exemption determination in writing.** If the TDPSA does not apply because you are a small business, document this determination annually — business size changes as the company grows.

---

## Gotchas

- TDPSA covers residents of Texas acting in an individual or household capacity — B2B contact data and employee data are excluded.
- The definition of "sale" under TDPSA includes exchange for monetary **or other valuable consideration** — barter-for-data arrangements are covered.
- Precise geolocation means data identifying a location within a radius of 1,750 feet — cached GPS coordinates in KV or D1 that meet this precision trigger the opt-in requirement.
- Cloudflare's `cf.region` field on the incoming request (`cf.region === 'Texas'`) can be used alongside `CF-IPCountry: US` to route Texas-specific consent logic without dedicated IP geolocation calls.
- Controllers that also operate in states with a global universal opt-out mechanism obligation (Colorado, Connecticut) should build a single UOM-recognition layer and apply TDPSA opt-out from the same signal as a best practice, even though TDPSA does not mandate it.

---

## Verification

```bash
# 1. SBA exemption determination on file
wrangler d1 execute DB --command \
  "SELECT naics_code, qualifies_as_small_business, determined_at
   FROM tdpsa_exemption_determination ORDER BY determined_at DESC LIMIT 5;"

# 2. Open DSR tickets near deadline
wrangler d1 execute DB --command \
  "SELECT id, right, COALESCE(extended_deadline_at, deadline_at) AS due
   FROM tdpsa_dsr WHERE status IN ('open','extended')
   AND due <= datetime('now', '+5 days');"

# 3. Denied requests without appeal response
wrangler d1 execute DB --command \
  "SELECT id, consumer_id, right, appeal_deadline_at
   FROM tdpsa_dsr WHERE status = 'denied'
   AND appeal_deadline_at >= datetime('now');"

# 4. DPA coverage
wrangler d1 execute DB --command \
  "SELECT activity, COUNT(*) AS count, MAX(completed_at) AS latest
   FROM tdpsa_dpa_registry GROUP BY activity;"
```

---

## Related

- `vcdpa-virginia-consumer-data-protection-workers.md`
- `connecticut-ctdpa-data-rights-workers.md`
- `tennessee-ipa-workers-d1.md`
- `us-state-privacy-laws-2026-multi-state-compliance.md`
- `ccpa-cpra-consumer-rights-operations.md`

---

## Sources

- Texas Data Privacy and Security Act, HB 4 (Tex. Bus. & Com. Code Ch. 541): https://capitol.texas.gov/BillLookup/History.aspx?LegSess=88R&Bill=HB4
- Texas AG Consumer Protection: https://www.texasattorneygeneral.gov/consumer-protection
- SBA Size Standards Tool: https://www.sba.gov/document/support--table-size-standards
