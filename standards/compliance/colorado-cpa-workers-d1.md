# Colorado Privacy Act (CPA) — Cloudflare Workers D1

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

Your service processes personal data of Colorado residents and meets either threshold under the Colorado Privacy Act (CPA, SB 21-190, Colo. Rev. Stat. §§ 6-1-1301 et seq., effective 1 July 2023): (a) control or process personal data of 100,000+ Colorado consumers during a calendar year, or (b) control or process data of 25,000+ Colorado consumers while deriving revenue or receiving discounts from the sale of personal data. The CPA imposes opt-in consent for sensitive data, mandatory recognition of Universal Opt-Out Mechanisms (UOMs) such as the Global Privacy Control as of 1 July 2024, data protection assessments before high-risk processing, and data subject rights fulfilment within 45 days.

---

## Context

The CPA is enforced by the Colorado AG and district attorneys; fines reach USD 20,000 per violation and USD 500,000 per related series. The CPA's **cure period expired 1 January 2025** — post-2025 violations may be actioned immediately without prior written notice. Key features:

- **Universal Opt-Out Mechanism (UOM)**: controllers must honour any UOM specified by the Colorado AG (currently the Global Privacy Control) as an opt-out of sale and targeted advertising, effective since 1 July 2024.
- **Sensitive data** (§ 6-1-1303(23)): racial/ethnic origin, religious beliefs, mental/physical health condition, sex life/sexual orientation, citizen/immigration status, genetic data, biometric data, children's data under 13, precise geolocation — requires **opt-in consent**.
- **Data protection assessments (DPAs)** required before: targeted advertising, sale, profiling with legal or substantial effects, sensitive data processing, any other processing presenting a heightened risk.
- **Data minimisation** and **purpose limitation** are affirmative obligations, not merely best practices.
- **Response deadline**: 45 days from receipt, extendable once by 45 days with written notice; appeal must be provided and controller must respond within 45 days of appeal.

---

## 1. Universal Opt-Out Mechanism (UOM) / GPC Recognition

Colorado mandates honouring the GPC signal as a UOM opt-out of sale and targeted advertising since 1 July 2024. The Worker intercepts `Sec-GPC: 1` and writes an opt-out record before the request reaches any downstream ad or analytics system.

```typescript
// workers/cpa-uom-middleware.ts
import { Env } from './types';

type CpaOptOutScope = 'sale' | 'targeted_advertising';

export async function cpaUomMiddleware(
  env: Env,
  request: Request,
  consumerId: string | null,
): Promise<{ optedOut: boolean; scopes: CpaOptOutScope[] }> {
  const isGpc = request.headers.get('Sec-GPC') === '1';
  if (!isGpc || !consumerId) return { optedOut: false, scopes: [] };

  const scopes: CpaOptOutScope[] = ['sale', 'targeted_advertising'];
  for (const scope of scopes) {
    await env.DB.prepare(
      `INSERT OR REPLACE INTO cpa_opt_out
       (consumer_id, scope, signal, recorded_at, ip_address)
       VALUES (?, ?, 'gpc', datetime('now'), ?)`,
    ).bind(consumerId, scope, request.headers.get('CF-Connecting-IP') ?? 'unknown').run();
  }

  return { optedOut: true, scopes };
}

export async function isCpaOptedOut(
  env: Env,
  consumerId: string,
  scope: CpaOptOutScope,
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM cpa_opt_out
     WHERE consumer_id = ? AND scope = ?
     LIMIT 1`,
  ).bind(consumerId, scope).first();
  return row !== null;
}

export async function rescindCpaOptOut(
  env: Env,
  consumerId: string,
  scope: CpaOptOutScope,
): Promise<void> {
  // Consumer may manually re-opt-in; deletion of the opt-out record re-enables processing
  await env.DB.prepare(
    `DELETE FROM cpa_opt_out WHERE consumer_id = ? AND scope = ?`,
  ).bind(consumerId, scope).run();
}
```

---

## 2. Sensitive Data Opt-In Gate

```typescript
// workers/cpa-sensitive-consent.ts
const CPA_SENSITIVE_CATEGORIES = [
  'racial_ethnic_origin', 'religious_belief', 'mental_health_condition',
  'physical_health_condition', 'sex_life_sexual_orientation',
  'citizen_immigration_status', 'genetic_data', 'biometric_data',
  'childrens_data', 'precise_geolocation',
] as const;
type CpaSensitiveCategory = typeof CPA_SENSITIVE_CATEGORIES[number];

export async function grantCpaSensitiveConsent(
  env: Env,
  consumerId: string,
  categories: CpaSensitiveCategory[],
  purpose: string,
  consentText: string,
  request: Request,
): Promise<string> {
  const id = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO cpa_sensitive_consent
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

export async function revokeCpaSensitiveConsent(
  env: Env,
  consumerId: string,
  category: CpaSensitiveCategory,
): Promise<void> {
  await env.DB.prepare(
    `UPDATE cpa_sensitive_consent SET revoked_at = datetime('now')
     WHERE consumer_id = ? AND revoked_at IS NULL
       AND categories LIKE '%' || ? || '%'`,
  ).bind(consumerId, category).run();
}

export async function hasCpaSensitiveConsent(
  env: Env,
  consumerId: string,
  category: CpaSensitiveCategory,
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM cpa_sensitive_consent
     WHERE consumer_id = ? AND revoked_at IS NULL
       AND categories LIKE '%' || ? || '%'
     LIMIT 1`,
  ).bind(consumerId, category).first();
  return row !== null;
}
```

---

## 3. Consumer Rights — 45-Day Clock with Appeal

```typescript
// workers/cpa-dsr.ts
type CpaRight =
  | 'access' | 'correction' | 'deletion'
  | 'portability' | 'opt_out_sale'
  | 'opt_out_targeted_advertising' | 'opt_out_profiling';

interface CpaDsrTicket {
  id: string;
  consumerId: string;
  right: CpaRight;
  receivedAt: string;
  deadlineAt: string;             // 45 days
  extendedDeadlineAt: string | null;   // up to 90 days total
  appealDeadlineAt: string | null;     // controller has 45 days to respond to appeal
  status: 'open' | 'extended' | 'denied' | 'appeal_pending' | 'completed';
  denialReason: string | null;
}

export async function openCpaRequest(
  env: Env,
  consumerId: string,
  right: CpaRight,
): Promise<CpaDsrTicket> {
  const id = crypto.randomUUID();
  const now = new Date();
  const deadline = new Date(now.getTime() + 45 * 86_400_000);

  await env.DB.prepare(
    `INSERT INTO cpa_dsr
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

export async function extendCpaRequest(
  env: Env,
  ticketId: string,
  noticeText: string,
): Promise<void> {
  const newDeadline = new Date(Date.now() + 45 * 86_400_000).toISOString();
  await env.DB.prepare(
    `UPDATE cpa_dsr
     SET status = 'extended', extended_deadline_at = ?, extension_notice = ?
     WHERE id = ? AND status = 'open'`,
  ).bind(newDeadline, noticeText, ticketId).run();
}

export async function denyCpaRequest(
  env: Env,
  ticketId: string,
  reason: string,
): Promise<void> {
  // CPA requires offering an internal appeal; controller has 45 days to respond
  const appealDeadline = new Date(Date.now() + 45 * 86_400_000).toISOString();
  await env.DB.prepare(
    `UPDATE cpa_dsr
     SET status = 'denied', denial_reason = ?, appeal_deadline_at = ?
     WHERE id = ?`,
  ).bind(reason, appealDeadline, ticketId).run();
}

export async function fulfillCpaDeletion(
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
    `UPDATE cpa_dsr SET status = 'completed', completed_at = datetime('now')
     WHERE id = ?`,
  ).bind(ticketId).run();
}

// Cron: alert on tickets approaching deadline
export async function alertCpaDeadlines(env: Env): Promise<void> {
  const horizon = new Date(Date.now() + 5 * 86_400_000).toISOString();
  const { results } = await env.DB.prepare(
    `SELECT id, consumer_id, right,
            COALESCE(extended_deadline_at, deadline_at) AS effective_deadline
     FROM cpa_dsr
     WHERE status IN ('open', 'extended')
       AND COALESCE(extended_deadline_at, deadline_at) <= ?`,
  ).bind(horizon).all<{ id: string; consumer_id: string; right: string; effective_deadline: string }>();

  for (const r of results) {
    await env.ALERTS_QUEUE.send({ type: 'cpa_deadline_warning', ...r });
  }
}
```

---

## 4. Data Protection Assessment Registry

CPA § 6-1-1309 mandates DPAs before high-risk activities. The AG may request them during enforcement; they must be retained for the duration of the processing activity and for three years thereafter.

```typescript
// workers/cpa-dpa-registry.ts
type CpaDpaActivity =
  | 'targeted_advertising' | 'sale_of_personal_data'
  | 'profiling_legal_substantial_effects' | 'sensitive_data_processing'
  | 'other_heightened_risk';

export async function registerCpaDpa(
  env: Env,
  activity: CpaDpaActivity,
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
    `INSERT INTO cpa_dpa_registry
     (id, activity, purpose, benefits_assessed, risks_identified,
      mitigations_applied, net_benefit_positive, approved_by,
      completed_at, next_review_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)`,
  ).bind(
    id, activity, purpose, benefitsAssessed, risksIdentified,
    mitigationsApplied, netBenefitPositive ? 1 : 0, approvedBy, nextReviewDate,
  ).run();
  return id;
}

// Cron: alert on DPAs due for review
export async function alertCpaDpaReviews(env: Env): Promise<void> {
  const horizon = new Date(Date.now() + 30 * 86_400_000).toISOString();
  const { results } = await env.DB.prepare(
    `SELECT id, activity, next_review_at FROM cpa_dpa_registry
     WHERE next_review_at <= ? ORDER BY next_review_at`,
  ).bind(horizon).all<{ id: string; activity: string; next_review_at: string }>();

  for (const r of results) {
    await env.ALERTS_QUEUE.send({ type: 'cpa_dpa_review_due', ...r });
  }
}
```

---

## Anti-patterns

- **Assuming the cure period still applies after 1 January 2025.** Colorado's 60-day cure period expired at the start of 2025; the AG can now file an action without prior notice.
- **Honouring GPC only for sale but not targeted advertising.** Colorado's UOM mandate covers both — scoping the opt-out only to "sale" is a violation.
- **Conflating Colorado's citizen/immigration status category with other states.** Colorado explicitly lists citizenship/immigration status as a sensitive category requiring opt-in; some other state laws do not.
- **Not retaining DPAs for the required period.** DPAs must be kept for the life of the processing plus three years; deleting them during routine data minimisation sweeps is incorrect.
- **Treating the UOM opt-out as consumer-specific only.** The UOM recognition must apply to any authenticated or identifiable session from a Colorado consumer — it cannot require login before honouring the signal.

---

## Gotchas

- The Colorado AG publishes an authoritative list of recognised UOM mechanisms; organisations must monitor updates to this list and implement new signals within the prescribed timeline after they are added.
- The appeal response deadline under CPA is **45 days** (not 60 as in Connecticut); this is the period within which the controller must respond after the consumer files an appeal.
- Colorado's definition of "profiling" with legal or similarly substantial effects is broader than simple automated decision-making — credit decisions, employment, housing, insurance, and educational opportunities are explicitly named.
- Cloudflare Workers receive `cf.region`; when `CF-IPCountry` is `US` and `cf.region` is `CO`, route the request through the CPA middleware pipeline.
- Revenue derived from data sale (not consumer count) triggers the 25,000-consumer secondary threshold — even a small ad-tech integration may push you above it.

---

## Verification

```bash
# 1. GPC opt-out records in last 7 days
wrangler d1 execute DB --command \
  "SELECT consumer_id, scope, signal, recorded_at FROM cpa_opt_out
   WHERE recorded_at >= datetime('now', '-7 days') ORDER BY recorded_at DESC LIMIT 20;"

# 2. Open DSR tickets near deadline
wrangler d1 execute DB --command \
  "SELECT id, right, COALESCE(extended_deadline_at, deadline_at) AS due
   FROM cpa_dsr WHERE status IN ('open','extended')
   AND due <= datetime('now', '+5 days');"

# 3. Denied requests in appeal window
wrangler d1 execute DB --command \
  "SELECT id, consumer_id, right, appeal_deadline_at FROM cpa_dsr
   WHERE status = 'denied' AND appeal_deadline_at >= datetime('now');"

# 4. DPAs due for review in next 30 days
wrangler d1 execute DB --command \
  "SELECT activity, next_review_at FROM cpa_dpa_registry
   WHERE next_review_at <= datetime('now', '+30 days');"
```

---

## Related

- `connecticut-ctdpa-data-rights-workers.md`
- `vcdpa-virginia-consumer-data-protection-workers.md`
- `us-state-privacy-laws-2026-multi-state-compliance.md`
- `eprivacy-directive-workers.md`
- `cookie-consent-management-platform.md`

---

## Sources

- Colorado Privacy Act (Colo. Rev. Stat. §§ 6-1-1301 et seq.): https://leg.colorado.gov/sites/default/files/2021a_190_signed.pdf
- Colorado AG Privacy Rules and UOM List: https://coag.gov/resources/data-privacy/
- IAPP Colorado Privacy Act Overview: https://iapp.org/resources/article/colorado-privacy-act/
