# Utah UCPA Privacy Compliance — Cloudflare Workers D1

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Your service controls or processes personal data of Utah residents and meets both UCPA thresholds simultaneously: (a) annual revenue of USD 25 million or more, AND (b) either process personal data of 100,000+ Utah consumers per year, or process personal data of 25,000+ consumers while deriving 50 %+ of gross revenue from the sale of personal data. The Utah Consumer Privacy Act (UCPA, Utah Code §§ 13-61-101 through 13-61-404, effective 31 December 2023) is among the most business-friendly US state privacy laws — it requires opt-out rights for sale and targeted advertising but has no correction right and no opt-in requirement for sensitive data — with AG enforcement and fines up to USD 7,500 per violation.

---

## Context

The UCPA differs meaningfully from the Virginia/Connecticut/Colorado cluster:

- **Consumer rights** (§ 13-61-201): access, deletion, portability, opt-out of sale and targeted advertising. Notably **no correction right** and **no opt-out of profiling**.
- **Sensitive data** (§ 13-61-102): racial/ethnic origin, religious belief, sexual orientation, citizenship/immigration, genetic/biometric data, specific health conditions, precise geolocation, children's data — controller must provide **clear notice and opt-out opportunity** (not opt-in consent; opt-out model applies).
- **No GPC mandate**: UCPA does not require recognition of opt-out preference signals such as GPC (as of the current statute text).
- **Dual threshold**: both the revenue floor ($25 M) and the data-volume test must be satisfied — a data-heavy nonprofit or small business below $25 M is exempt.
- **Response deadline**: 45 calendar days, extendable by 45 days with prior notice.
- **No private right of action**: enforcement is exclusively by the AG with a 30-day cure period.

---

## 1. Opt-Out of Sale and Targeted Advertising

UCPA requires a clear and conspicuous opt-out mechanism for data sales and targeted advertising — but only those two activities.

```typescript
// workers/ucpa-opt-out.ts
import { Env } from './types';

type UcpaOptOutScope = 'sale' | 'targeted_advertising' | 'all';

interface UcpaOptOutRecord {
  id: string;
  consumerId: string;
  scope: UcpaOptOutScope;
  signal: 'web_form' | 'api' | 'preference_center';
  recordedAt: string;
  ipAddress: string;
}

export async function recordUcpaOptOut(
  env: Env,
  consumerId: string,
  scope: UcpaOptOutScope,
  signal: UcpaOptOutRecord['signal'],
  request: Request,
): Promise<string> {
  const id = crypto.randomUUID();

  await env.DB.prepare(
    `INSERT OR REPLACE INTO ucpa_opt_out
     (id, consumer_id, scope, signal, recorded_at, ip_address)
     VALUES (?, ?, ?, ?, datetime('now'), ?)`,
  ).bind(
    id, consumerId, scope, signal,
    request.headers.get('CF-Connecting-IP') ?? 'unknown',
  ).run();

  return id;
}

export async function isUcpaOptedOut(
  env: Env,
  consumerId: string,
  scope: 'sale' | 'targeted_advertising',
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM ucpa_opt_out
     WHERE consumer_id = ? AND (scope = ? OR scope = 'all')
     LIMIT 1`,
  ).bind(consumerId, scope).first();
  return row !== null;
}

export async function revokeUcpaOptOut(
  env: Env,
  consumerId: string,
  scope: UcpaOptOutScope,
): Promise<void> {
  await env.DB.prepare(
    `DELETE FROM ucpa_opt_out WHERE consumer_id = ? AND scope = ?`,
  ).bind(consumerId, scope).run();
}
```

---

## 2. Sensitive Data Notice and Opt-Out

Unlike CTDPA/VCDPA, UCPA does not require opt-in consent for sensitive data — it requires a clear notice that sensitive data is being processed and an opportunity to opt out before processing begins.

```typescript
// workers/ucpa-sensitive-notice.ts
const UCPA_SENSITIVE = [
  'racial_ethnic_origin', 'religious_belief', 'sexual_orientation',
  'citizenship_immigration', 'genetic_data', 'biometric_data',
  'health_condition', 'precise_geolocation', 'childrens_data',
] as const;
type UcpaSensitiveCategory = typeof UCPA_SENSITIVE[number];

export async function recordSensitiveDataNoticeAck(
  env: Env,
  consumerId: string,
  categories: UcpaSensitiveCategory[],
  noticeVersion: string,
  request: Request,
): Promise<string> {
  const id = crypto.randomUUID();

  await env.DB.prepare(
    `INSERT INTO ucpa_sensitive_notice
     (id, consumer_id, categories, notice_version, acknowledged_at,
      opted_out, ip_address)
     VALUES (?, ?, ?, ?, datetime('now'), 0, ?)`,
  ).bind(
    id, consumerId, JSON.stringify(categories), noticeVersion,
    request.headers.get('CF-Connecting-IP') ?? 'unknown',
  ).run();

  return id;
}

export async function recordSensitiveDataOptOut(
  env: Env,
  consumerId: string,
  categories: UcpaSensitiveCategory[],
  request: Request,
): Promise<void> {
  await env.DB.prepare(
    `INSERT OR REPLACE INTO ucpa_sensitive_opt_out
     (consumer_id, categories, opted_out_at, ip_address)
     VALUES (?, ?, datetime('now'), ?)`,
  ).bind(
    consumerId, JSON.stringify(categories),
    request.headers.get('CF-Connecting-IP') ?? 'unknown',
  ).run();
}

export async function isSensitiveDataOptedOut(
  env: Env,
  consumerId: string,
  category: UcpaSensitiveCategory,
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM ucpa_sensitive_opt_out
     WHERE consumer_id = ? AND categories LIKE '%' || ? || '%'`,
  ).bind(consumerId, category).first();
  return row !== null;
}
```

---

## 3. Consumer Rights — Access, Deletion, Portability

UCPA provides no correction right; the controller must respond to access, deletion, and portability within 45 days.

```typescript
// workers/ucpa-dsr.ts
type UcpaRight = 'access' | 'deletion' | 'portability';

interface UcpaDsrTicket {
  id: string;
  consumerId: string;
  right: UcpaRight;
  receivedAt: string;
  deadlineAt: string;           // 45 calendar days
  extendedDeadlineAt: string | null; // up to 90 days with notice
  status: 'open' | 'extended' | 'completed' | 'denied';
  denialReason: string | null;
}

export async function openUcpaRequest(
  env: Env,
  consumerId: string,
  right: UcpaRight,
): Promise<UcpaDsrTicket> {
  const id = crypto.randomUUID();
  const now = new Date();
  const deadline = new Date(now.getTime() + 45 * 86_400_000);

  await env.DB.prepare(
    `INSERT INTO ucpa_dsr
     (id, consumer_id, right, received_at, deadline_at, status)
     VALUES (?, ?, ?, ?, ?, 'open')`,
  ).bind(id, consumerId, right, now.toISOString(), deadline.toISOString()).run();

  return { id, consumerId, right, receivedAt: now.toISOString(),
    deadlineAt: deadline.toISOString(), extendedDeadlineAt: null,
    status: 'open', denialReason: null };
}

export async function extendUcpaRequest(
  env: Env,
  ticketId: string,
): Promise<void> {
  const row = await env.DB.prepare(
    `SELECT received_at FROM ucpa_dsr WHERE id = ?`,
  ).bind(ticketId).first<{ received_at: string }>();
  if (!row) throw new Error('DSR ticket not found');

  const extended = new Date(new Date(row.received_at).getTime() + 90 * 86_400_000);

  await env.DB.prepare(
    `UPDATE ucpa_dsr
     SET status = 'extended', extended_deadline_at = ?
     WHERE id = ?`,
  ).bind(extended.toISOString(), ticketId).run();
}

// Cron job: send alerts 5 days before effective deadline
export async function alertUcpaDeadlines(env: Env): Promise<void> {
  const horizon = new Date(Date.now() + 5 * 86_400_000).toISOString();
  const { results } = await env.DB.prepare(
    `SELECT id, consumer_id, right,
            COALESCE(extended_deadline_at, deadline_at) AS due
     FROM ucpa_dsr
     WHERE status IN ('open','extended') AND due <= ?`,
  ).bind(horizon).all<{ id: string; consumer_id: string; right: string; due: string }>();

  for (const r of results) {
    await env.ALERTS_QUEUE.send({ type: 'ucpa_deadline_warning', ...r });
  }
}
```

---

## 4. Dual-Threshold Applicability Check

UCPA only applies when the entity meets **both** the $25 M revenue floor and a data-volume test. A Worker can gate UCPA logic behind a runtime feature flag tied to applicability status.

```typescript
// workers/ucpa-applicability.ts
interface UcpaApplicabilityStatus {
  meetsRevenueThreshold: boolean;  // >= $25M annual revenue
  meetsDataVolumeTest: boolean;    // >= 100k consumers OR (25k+ with 50%+ revenue from sale)
  applicable: boolean;
  lastAssessedAt: string;
}

export async function getUcpaApplicability(
  env: Env,
): Promise<UcpaApplicabilityStatus> {
  const row = await env.DB.prepare(
    `SELECT meets_revenue_threshold, meets_data_volume_test,
            applicable, last_assessed_at
     FROM ucpa_applicability ORDER BY last_assessed_at DESC LIMIT 1`,
  ).first<{
    meets_revenue_threshold: number;
    meets_data_volume_test: number;
    applicable: number;
    last_assessed_at: string;
  }>();

  if (!row) {
    return { meetsRevenueThreshold: false, meetsDataVolumeTest: false,
      applicable: false, lastAssessedAt: new Date(0).toISOString() };
  }

  return {
    meetsRevenueThreshold: row.meets_revenue_threshold === 1,
    meetsDataVolumeTest: row.meets_data_volume_test === 1,
    applicable: row.applicable === 1,
    lastAssessedAt: row.last_assessed_at,
  };
}

// Gate: skip UCPA processing when not applicable
export async function requiresUcpa(env: Env, request: Request): Promise<boolean> {
  const country = request.headers.get('CF-IPCountry');
  if (country !== 'US') return false;
  const { applicable } = await getUcpaApplicability(env);
  return applicable;
}
```

---

## Anti-patterns

- **Treating UCPA like CTDPA/VCDPA for sensitive data.** UCPA uses an opt-out model for sensitive data — implementing opt-in consent is overly restrictive and may conflict with UX flows, but implementing no notice at all is a violation.
- **Omitting the $25 M revenue floor check.** A data-heavy entity below $25 M annual revenue is exempt; incorrectly applying UCPA burdens that entity without legal basis.
- **Adding a correction right workflow.** UCPA does not include a correction right; building one in the UCPA path can confuse consumers and creates obligations UCPA does not impose.
- **Assuming GPC is required.** Unlike Connecticut and Colorado, UCPA does not require recognition of opt-out browser signals — implement separately if serving multi-state.

---

## Gotchas

- The 30-day cure period is statutory and applies to all violations; the AG cannot commence an action without providing it.
- "Sale" under UCPA means exchange for **monetary consideration only** — a narrower definition than Virginia/Connecticut/Colorado, which include other valuable consideration.
- Precise geolocation under UCPA is defined as a radius of less than 1,750 feet — same as VCDPA; ensure mapping or check-in features assess location precision before deciding sensitive-data rules apply.
- No data protection assessments are required under UCPA — unlike VCDPA, CTDPA, and Colorado CPA.
- Profiling opt-out is not included; only sale and targeted advertising opt-out are required.

---

## Verification

```bash
# 1. Active opt-outs by scope
wrangler d1 execute DB --command \
  "SELECT scope, COUNT(*) AS total FROM ucpa_opt_out GROUP BY scope;"

# 2. Sensitive data opt-outs
wrangler d1 execute DB --command \
  "SELECT consumer_id, categories, opted_out_at FROM ucpa_sensitive_opt_out
   ORDER BY opted_out_at DESC LIMIT 20;"

# 3. Open DSR tickets approaching deadline
wrangler d1 execute DB --command \
  "SELECT id, right, COALESCE(extended_deadline_at, deadline_at) AS due
   FROM ucpa_dsr WHERE status IN ('open','extended')
   AND due <= datetime('now', '+5 days');"

# 4. Applicability status
wrangler d1 execute DB --command \
  "SELECT * FROM ucpa_applicability ORDER BY last_assessed_at DESC LIMIT 1;"
```

---

## Related

- `vcdpa-virginia-consumer-data-protection-workers.md`
- `connecticut-ctdpa-data-rights-workers.md`
- `us-state-privacy-laws-2026-multi-state-compliance.md`
- `ccpa-cpra-consumer-rights-operations.md`
- `cookie-consent-management-platform.md`

---

## Sources

- Utah Consumer Privacy Act (Utah Code §§ 13-61-101 – 13-61-404): https://le.utah.gov/xcode/Title13/Chapter61/13-61.html
- Utah AG Privacy Page: https://attorneygeneral.utah.gov/privacy/
- IAPP UCPA Overview: https://iapp.org/resources/article/utah-consumer-privacy-act/
- Cloudflare Workers D1 docs: https://developers.cloudflare.com/d1/
- OneTrust UCPA Analysis: https://www.onetrust.com/blog/utah-consumer-privacy-act/
