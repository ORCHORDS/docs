# Montana MCDPA Consumer Rights — Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Your service processes personal data of Montana residents and meets at least one MCDPA threshold: (a) during a calendar year, control or process personal data of 50,000+ Montana consumers (excluding data processed solely for payment transactions), or (b) control or process personal data of 25,000+ consumers while deriving 25 %+ of gross revenue from the sale of personal data. The Montana Consumer Data Privacy Act (MCDPA, SB 384, codified at Mont. Code Ann. §§ 30-14-3401 through 30-14-3412, effective 1 October 2024) closely follows the Colorado CPA model with opt-in consent for sensitive data, GPC recognition, and data protection assessments — with AG enforcement and civil penalties up to USD 7,500 per violation.

---

## Context

MCDPA is notable for its lower applicability threshold (50,000 consumers rather than the 100,000 of most peer laws), making it applicable to smaller regional services that process Montana resident data:

- **Consumer rights** (§ 30-14-3404): access, correction, deletion, portability, opt-out of sale/targeted advertising/profiling with significant effects.
- **Sensitive data** (§ 30-14-3401): racial/ethnic origin, religious beliefs, mental/physical health condition, sex life/sexual orientation, citizenship/immigration status, genetic/biometric data, children's data, precise geolocation — requires **opt-in consent** before processing.
- **GPC recognition** (§ 30-14-3404(5)): controllers must process the Global Privacy Control browser signal as a valid opt-out of sale and targeted advertising.
- **Data protection assessments (DPAs)** (§ 30-14-3407): required before targeted advertising, sale, high-risk profiling, sensitive data processing, or other activities presenting heightened risk.
- **Response deadline**: 45 calendar days from receipt of a verifiable request; extendable by 45 days with notice.
- **Appeal right**: consumers may appeal within a reasonable time after denial; controller must respond within 60 days.
- **No private right of action**: enforcement exclusively by the Montana AG.

---

## 1. Sensitive Data Opt-In Consent Gate

MCDPA requires affirmative opt-in consent before any sensitive data processing — stronger than Utah's opt-out model.

```typescript
// workers/mcdpa-sensitive-consent.ts
import { Env } from './types';

const MCDPA_SENSITIVE = [
  'racial_ethnic_origin', 'religious_belief', 'mental_health_condition',
  'physical_health_condition', 'sex_life_sexual_orientation',
  'citizenship_immigration', 'genetic_data', 'biometric_data',
  'childrens_data', 'precise_geolocation',
] as const;
type McdpaSensitiveCategory = typeof MCDPA_SENSITIVE[number];

export async function grantMcdpaSensitiveConsent(
  env: Env,
  consumerId: string,
  categories: McdpaSensitiveCategory[],
  purpose: string,
  consentText: string,
  request: Request,
): Promise<string> {
  const id = crypto.randomUUID();

  await env.DB.prepare(
    `INSERT INTO mcdpa_sensitive_consent
     (id, consumer_id, categories, purpose, consent_text,
      granted_at, revoked_at, ip_address)
     VALUES (?, ?, ?, ?, ?, datetime('now'), NULL, ?)`,
  ).bind(
    id, consumerId, JSON.stringify(categories),
    purpose, consentText,
    request.headers.get('CF-Connecting-IP') ?? 'unknown',
  ).run();

  return id;
}

export async function revokeMcdpaSensitiveConsent(
  env: Env,
  consumerId: string,
  category: McdpaSensitiveCategory,
): Promise<void> {
  await env.DB.prepare(
    `UPDATE mcdpa_sensitive_consent
     SET revoked_at = datetime('now')
     WHERE consumer_id = ? AND revoked_at IS NULL
       AND categories LIKE '%' || ? || '%'`,
  ).bind(consumerId, category).run();
}

export async function hasMcdpaSensitiveConsent(
  env: Env,
  consumerId: string,
  category: McdpaSensitiveCategory,
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM mcdpa_sensitive_consent
     WHERE consumer_id = ? AND revoked_at IS NULL
       AND categories LIKE '%' || ? || '%'
     LIMIT 1`,
  ).bind(consumerId, category).first();
  return row !== null;
}
```

---

## 2. GPC Opt-Out Signal Recognition

MCDPA requires recognising the Global Privacy Control signal at the edge as an opt-out of sale and targeted advertising.

```typescript
// workers/mcdpa-gpc-middleware.ts
export async function mcdpaGpcMiddleware(
  env: Env,
  request: Request,
  consumerId: string | null,
): Promise<{ applied: boolean }> {
  if (!consumerId || request.headers.get('Sec-GPC') !== '1') {
    return { applied: false };
  }

  // GPC applies to sale and targeted advertising under MCDPA
  await env.DB.prepare(
    `INSERT OR REPLACE INTO mcdpa_opt_out
     (consumer_id, scope, signal, recorded_at, ip_address)
     VALUES (?, 'sale_and_targeted_advertising', 'gpc', datetime('now'), ?)`,
  ).bind(
    consumerId,
    request.headers.get('CF-Connecting-IP') ?? 'unknown',
  ).run();

  return { applied: true };
}

export async function isMcdpaOptedOut(
  env: Env,
  consumerId: string,
  scope: 'sale' | 'targeted_advertising' | 'profiling',
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM mcdpa_opt_out
     WHERE consumer_id = ?
       AND (scope = ? OR scope = 'all'
            OR scope = 'sale_and_targeted_advertising')
     LIMIT 1`,
  ).bind(consumerId, scope).first();
  return row !== null;
}
```

---

## 3. Consumer Rights Request Handling

MCDPA's 45-day clock starts on receipt of a verifiable request. The appeal workflow must be implemented — unlike UCPA, MCDPA requires it.

```typescript
// workers/mcdpa-dsr.ts
type McdpaRight =
  | 'access' | 'correction' | 'deletion'
  | 'portability' | 'opt_out_sale'
  | 'opt_out_targeted_advertising' | 'opt_out_profiling';

interface McdpaDsrTicket {
  id: string;
  consumerId: string;
  right: McdpaRight;
  receivedAt: string;
  deadlineAt: string;
  extendedDeadlineAt: string | null;
  appealDeadlineAt: string | null;  // 60 days from denial to appeal
  status: 'open' | 'extended' | 'completed' | 'denied' | 'appeal_pending';
  denialReason: string | null;
}

export async function openMcdpaRequest(
  env: Env,
  consumerId: string,
  right: McdpaRight,
): Promise<McdpaDsrTicket> {
  const id = crypto.randomUUID();
  const now = new Date();
  const deadline = new Date(now.getTime() + 45 * 86_400_000);

  await env.DB.prepare(
    `INSERT INTO mcdpa_dsr
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

export async function denyMcdpaRequest(
  env: Env,
  ticketId: string,
  reason: string,
): Promise<void> {
  const appealDeadline = new Date(Date.now() + 60 * 86_400_000).toISOString();
  await env.DB.prepare(
    `UPDATE mcdpa_dsr
     SET status = 'denied', denial_reason = ?, appeal_deadline_at = ?
     WHERE id = ?`,
  ).bind(reason, appealDeadline, ticketId).run();
}

export async function alertMcdpaDeadlines(env: Env): Promise<void> {
  const horizon = new Date(Date.now() + 5 * 86_400_000).toISOString();
  const { results } = await env.DB.prepare(
    `SELECT id, consumer_id, right,
            COALESCE(extended_deadline_at, deadline_at) AS due
     FROM mcdpa_dsr WHERE status IN ('open','extended') AND due <= ?`,
  ).bind(horizon).all<{ id: string; consumer_id: string; right: string; due: string }>();

  for (const r of results) {
    await env.ALERTS_QUEUE.send({ type: 'mcdpa_deadline_warning', ...r });
  }
}
```

---

## 4. Data Protection Assessment Registry

Montana DPAs must be completed before any high-risk processing activity begins; the AG may request DPAs during investigation.

```typescript
// workers/mcdpa-dpa-registry.ts
type McdpaDpaActivity =
  | 'targeted_advertising' | 'sale_of_personal_data'
  | 'profiling_significant_effects' | 'sensitive_data_processing'
  | 'other_heightened_risk';

export async function registerMcdpaDpa(
  env: Env,
  activity: McdpaDpaActivity,
  purpose: string,
  risks: string,
  mitigations: string,
  netBenefitPositive: boolean,
  approvedBy: string,
  nextReviewAt: string,
): Promise<string> {
  const id = crypto.randomUUID();

  await env.DB.prepare(
    `INSERT INTO mcdpa_dpa_registry
     (id, activity, purpose, risks_identified, mitigations_applied,
      net_benefit_positive, approved_by, completed_at, next_review_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)`,
  ).bind(
    id, activity, purpose, risks, mitigations,
    netBenefitPositive ? 1 : 0, approvedBy, nextReviewAt,
  ).run();

  return id;
}

export async function listMissingMcdpaDpas(env: Env): Promise<McdpaDpaActivity[]> {
  const required: McdpaDpaActivity[] = [
    'targeted_advertising', 'sale_of_personal_data',
    'profiling_significant_effects',
  ];
  const missing: McdpaDpaActivity[] = [];

  for (const activity of required) {
    const row = await env.DB.prepare(
      `SELECT 1 FROM mcdpa_dpa_registry WHERE activity = ? LIMIT 1`,
    ).bind(activity).first();
    if (!row) missing.push(activity);
  }

  return missing;
}
```

---

## Anti-patterns

- **Using 100,000 as the applicability threshold.** MCDPA triggers at 50,000 consumers — half the threshold of most peer state laws. Services that previously applied only Virginia/Connecticut rules may be newly subject to Montana.
- **Skipping the appeal mechanism.** MCDPA requires controllers to provide an appeal process after denial; no appeal path means a structural violation on every denial.
- **Ignoring GPC.** Montana follows the Colorado CPA model in requiring GPC recognition; unlike Utah, there is no GPC exemption.
- **Processing sensitive data with only notice, not consent.** Montana requires affirmative opt-in consent for sensitive categories — notice-and-opt-out (Utah model) is insufficient.

---

## Gotchas

- Payment transaction data is explicitly excluded from the 50,000-consumer count — e-commerce platforms should strip payment-only records when computing applicability.
- "Sale" includes exchange for **other valuable consideration** (not just monetary) — barter arrangements and data-for-access exchanges count.
- Precise geolocation triggers sensitive-data rules at less than approximately 1,750 feet radius.
- MCDPA does not specify a revenue floor, unlike Utah's $25 M requirement — any entity meeting the data-volume test is subject.
- Employees and B2B contacts are excluded from consumer rights, but only when data is processed solely in an employment/commercial context.

---

## Verification

```bash
# 1. Sensitive consent records active by category
wrangler d1 execute DB --command \
  "SELECT consumer_id, categories, granted_at FROM mcdpa_sensitive_consent
   WHERE revoked_at IS NULL ORDER BY granted_at DESC LIMIT 20;"

# 2. GPC opt-outs in last 30 days
wrangler d1 execute DB --command \
  "SELECT COUNT(*) AS gpc_count FROM mcdpa_opt_out
   WHERE signal = 'gpc' AND recorded_at >= datetime('now', '-30 days');"

# 3. Open DSR tickets near deadline
wrangler d1 execute DB --command \
  "SELECT id, right, COALESCE(extended_deadline_at, deadline_at) AS due
   FROM mcdpa_dsr WHERE status IN ('open','extended')
   AND due <= datetime('now', '+5 days');"

# 4. DPA coverage gaps
wrangler d1 execute DB --command \
  "SELECT activity, COUNT(*) AS count FROM mcdpa_dpa_registry GROUP BY activity;"
```

---

## Related

- `connecticut-ctdpa-data-rights-workers.md`
- `vcdpa-virginia-consumer-data-protection-workers.md`
- `us-state-privacy-laws-2026-multi-state-compliance.md`
- `gdpr-consent-management-cloudflare-workers.md`
- `cookie-consent-management-platform.md`

---

## Sources

- Montana Consumer Data Privacy Act (SB 384, Mont. Code Ann. §§ 30-14-3401 – 30-14-3412): https://leg.mt.gov/bills/2023/billpdf/SB0384.pdf
- Montana AG Privacy Resources: https://dojmt.gov/consumer/
- IAPP MCDPA Overview: https://iapp.org/resources/article/montana-consumer-data-privacy-act/
- W3C Global Privacy Control spec: https://globalprivacycontrol.github.io/gpc-spec/
- Cloudflare Workers D1 docs: https://developers.cloudflare.com/d1/
