# Connecticut CTDPA Data Rights — Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Your service processes personal data of Connecticut residents and meets one of the CTDPA thresholds: (a) during a calendar year, control or process personal data of 100,000+ consumers, or (b) control or process personal data of 25,000+ consumers while deriving 25 %+ of gross revenue from the sale of personal data. The Connecticut Data Privacy Act (CTDPA, Public Act 22-15, codified at Conn. Gen. Stat. §§ 42-515 through 42-525, effective 1 July 2023) mandates consumer rights fulfilment, opt-in consent for sensitive data, Global Privacy Control recognition (effective 1 October 2024), and data protection assessments — with enforcement by the Connecticut AG and fines up to USD 5,000 per violation.

---

## Context

The CTDPA closely mirrors the VCDPA and Colorado CPA but contains several notable distinctions:

- **Consumer rights** (§ 42-519): access, correction, deletion, portability, opt-out of sale/targeted advertising/profiling with significant effects.
- **Sensitive data** (§ 42-515): racial/ethnic origin, religious beliefs, mental/physical health condition, sex life/sexual orientation, immigration status, genetic/biometric data, children's data, precise geolocation — requires **opt-in consent** before processing.
- **GPC recognition** (§ 42-519(b)): controllers must honour the Global Privacy Control browser signal as an opt-out of sale and targeted advertising as of 1 October 2024.
- **Data protection assessments (DPAs)** (§ 42-521): required prior to commencing targeted advertising, sale, profiling with significant effects, sensitive data processing, or any processing presenting heightened risk.
- **Response deadline**: 45 calendar days, extendable by 45 days with written notice; appeals must be provided within 60 days.
- **Cure period**: the AG must provide 60 days' notice before commencing an action (expires 31 December 2024 for future acts).

---

## 1. Sensitive Data Opt-In Consent Gate

Sensitive data processing requires an affirmative opt-in before any collection or processing begins.

```typescript
// workers/ctdpa-sensitive-consent.ts
import { Env } from './types';

const CTDPA_SENSITIVE = [
  'racial_ethnic_origin', 'religious_belief', 'mental_health_condition',
  'physical_health_condition', 'sex_life_sexual_orientation',
  'immigration_status', 'genetic_data', 'biometric_data',
  'childrens_data', 'precise_geolocation',
] as const;
type CtdpaSensitiveCategory = typeof CTDPA_SENSITIVE[number];

export async function grantCtdpaSensitiveConsent(
  env: Env,
  consumerId: string,
  categories: CtdpaSensitiveCategory[],
  purpose: string,
  consentText: string,
  request: Request,
): Promise<string> {
  const id = crypto.randomUUID();

  await env.DB.prepare(
    `INSERT INTO ctdpa_sensitive_consent
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

export async function hasCtdpaSensitiveConsent(
  env: Env,
  consumerId: string,
  category: CtdpaSensitiveCategory,
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM ctdpa_sensitive_consent
     WHERE consumer_id = ? AND revoked_at IS NULL
       AND categories LIKE '%' || ? || '%'
     LIMIT 1`,
  ).bind(consumerId, category).first();
  return row !== null;
}
```

---

## 2. GPC / Opt-Out Signal Recognition

§ 42-519(b) requires recognition of the Global Privacy Control signal as an opt-out of sale and targeted advertising. Workers intercept the `Sec-GPC: 1` header before the request reaches any downstream processor.

```typescript
// workers/ctdpa-gpc-middleware.ts
export async function ctdpaGpcMiddleware(
  env: Env,
  request: Request,
  consumerId: string | null,
): Promise<{ optedOut: boolean }> {
  const isGpc = request.headers.get('Sec-GPC') === '1';
  if (!isGpc || !consumerId) return { optedOut: false };

  await env.DB.prepare(
    `INSERT OR REPLACE INTO ctdpa_opt_out
     (consumer_id, signal, scope, recorded_at, ip_address)
     VALUES (?, 'gpc', 'sale_and_targeted_advertising', datetime('now'), ?)`,
  ).bind(consumerId, request.headers.get('CF-Connecting-IP') ?? 'unknown').run();

  return { optedOut: true };
}

export async function isCtdpaOptedOut(
  env: Env,
  consumerId: string,
  scope: 'sale' | 'targeted_advertising' | 'profiling',
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM ctdpa_opt_out
     WHERE consumer_id = ?
       AND (scope = ? OR scope = 'all' OR scope = 'sale_and_targeted_advertising')
     LIMIT 1`,
  ).bind(consumerId, scope).first();
  return row !== null;
}
```

---

## 3. Consumer Rights — 45-Day Clock with Appeal

```typescript
// workers/ctdpa-dsr.ts
type CtdpaRight =
  | 'access' | 'correction' | 'deletion'
  | 'portability' | 'opt_out_sale'
  | 'opt_out_targeted_advertising' | 'opt_out_profiling';

interface CtdpaDsrTicket {
  id: string;
  consumerId: string;
  right: CtdpaRight;
  receivedAt: string;
  deadlineAt: string;           // 45 days
  extendedDeadlineAt: string | null; // up to 90 days total
  appealDeadlineAt: string | null;   // 60 days from denial to appeal
  status: 'open' | 'extended' | 'denied' | 'appeal_pending' | 'completed';
}

export async function openCtdpaRequest(
  env: Env,
  consumerId: string,
  right: CtdpaRight,
): Promise<CtdpaDsrTicket> {
  const id = crypto.randomUUID();
  const now = new Date();
  const deadline = new Date(now.getTime() + 45 * 86_400_000);

  await env.DB.prepare(
    `INSERT INTO ctdpa_dsr
     (id, consumer_id, right, received_at, deadline_at, status)
     VALUES (?, ?, ?, ?, ?, 'open')`,
  ).bind(id, consumerId, right, now.toISOString(), deadline.toISOString()).run();

  return { id, consumerId, right, receivedAt: now.toISOString(),
    deadlineAt: deadline.toISOString(), extendedDeadlineAt: null,
    appealDeadlineAt: null, status: 'open' };
}

export async function denyCtdpaRequest(
  env: Env,
  ticketId: string,
  reason: string,
): Promise<void> {
  // Consumer must be notified; they have 60 days to appeal
  const appealDeadline = new Date(Date.now() + 60 * 86_400_000).toISOString();
  await env.DB.prepare(
    `UPDATE ctdpa_dsr
     SET status = 'denied', denial_reason = ?, appeal_deadline_at = ?
     WHERE id = ?`,
  ).bind(reason, appealDeadline, ticketId).run();
}

// Cron: surface tickets approaching their deadline
export async function alertCtdpaDeadlines(env: Env): Promise<void> {
  const horizon = new Date(Date.now() + 5 * 86_400_000).toISOString();
  const { results } = await env.DB.prepare(
    `SELECT id, consumer_id, right,
            COALESCE(extended_deadline_at, deadline_at) AS effective_deadline
     FROM ctdpa_dsr
     WHERE status IN ('open', 'extended')
       AND COALESCE(extended_deadline_at, deadline_at) <= ?`,
  ).bind(horizon).all<{ id: string; consumer_id: string; right: string; effective_deadline: string }>();

  for (const r of results) {
    await env.ALERTS_QUEUE.send({ type: 'ctdpa_deadline_warning', ...r });
  }
}
```

---

## 4. Data Protection Assessment Registry

§ 42-521 requires a completed DPA before beginning high-risk processing. The AG may subpoena DPAs during an investigation.

```typescript
// workers/ctdpa-dpa-registry.ts
type CtdpaDpaActivity =
  | 'targeted_advertising' | 'sale_of_personal_data'
  | 'profiling_significant_effects' | 'sensitive_data_processing'
  | 'other_heightened_risk';

interface CtdpaDpa {
  id: string;
  activity: CtdpaDpaActivity;
  purpose: string;
  benefitsAssessed: string;
  risksIdentified: string;
  mitigationsApplied: string;
  netBenefitPositive: boolean;
  approvedBy: string;
  completedAt: string;
  nextReviewAt: string;
}

export async function registerCtdpaDpa(
  env: Env,
  dpa: Omit<CtdpaDpa, 'id' | 'completedAt'>,
): Promise<string> {
  const id = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO ctdpa_dpa_registry
     (id, activity, purpose, benefits_assessed, risks_identified,
      mitigations_applied, net_benefit_positive, approved_by,
      completed_at, next_review_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)`,
  ).bind(
    id, dpa.activity, dpa.purpose, dpa.benefitsAssessed,
    dpa.risksIdentified, dpa.mitigationsApplied,
    dpa.netBenefitPositive ? 1 : 0, dpa.approvedBy, dpa.nextReviewAt,
  ).run();
  return id;
}
```

---

## Anti-patterns

- **Reusing CCPA infrastructure without GPC expansion.** Connecticut GPC covers both sale AND targeted advertising; CCPA (pre-CPRA) covered only sale — scoping the opt-out too narrowly is a violation.
- **Starting the 45-day clock on verification completion instead of receipt.** CTDPA starts the clock at receipt of a verifiable consumer request; verification is part of the 45-day window.
- **Omitting the 60-day appeal deadline.** When denying a request, the controller must offer an internal appeal and respond within 60 days — skipping this is a separate violation.
- **Treating precise geolocation as non-sensitive.** Any coordinate that identifies a location to less than ~1,750 feet triggers opt-in consent, including cached or derived coordinates.

---

## Gotchas

- CTDPA's cure period (60 days) expires 31 December 2024 for violations occurring after that date — post-2024 violators may be sued without notice.
- The threshold test for "sale" includes exchange for **any valuable consideration**, not just cash — barter arrangements count.
- CTDPA explicitly includes a right to **correct** inaccurate personal data, unlike Utah's UCPA which does not.
- Small businesses below the 100,000 / 25,000 threshold are exempt, but there is no revenue-size floor — only the data-volume tests apply.
- Cloudflare Workers run globally; apply CTDPA controls when `CF-IPCountry: US` and state is `CT`, or when the consumer is otherwise known to be a Connecticut resident.

---

## Verification

```bash
# 1. Check GPC opt-out records for last 7 days
wrangler d1 execute DB --command \
  "SELECT consumer_id, scope, recorded_at FROM ctdpa_opt_out
   WHERE signal = 'gpc' AND recorded_at >= datetime('now', '-7 days')
   ORDER BY recorded_at DESC LIMIT 20;"

# 2. Open DSR tickets near deadline
wrangler d1 execute DB --command \
  "SELECT id, right, COALESCE(extended_deadline_at, deadline_at) AS due
   FROM ctdpa_dsr WHERE status IN ('open','extended')
   AND due <= datetime('now', '+5 days');"

# 3. DPA coverage by activity type
wrangler d1 execute DB --command \
  "SELECT activity, COUNT(*) AS count, MAX(completed_at) AS latest
   FROM ctdpa_dpa_registry GROUP BY activity;"

# 4. Sensitive consent grants missing revocation
wrangler d1 execute DB --command \
  "SELECT consumer_id, categories, granted_at FROM ctdpa_sensitive_consent
   WHERE revoked_at IS NULL ORDER BY granted_at DESC LIMIT 20;"
```

---

## Related

- `vcdpa-virginia-consumer-data-protection-workers.md`
- `us-state-privacy-laws-2026-multi-state-compliance.md`
- `gdpr-consent-management-cloudflare-workers.md`
- `cookie-consent-management-platform.md`
- `gdpr-data-subject-rights-api.md`

---

## Sources

- Connecticut Data Privacy Act (Conn. Gen. Stat. §§ 42-515 – 42-525): https://www.cga.ct.gov/2022/ACT/PA/PDF/2022PA-00015-R00SB-00006-PA.PDF
- Connecticut AG Privacy Guidance: https://portal.ct.gov/AG/Sections/Privacy/The-Privacy-Act
- IAPP CTDPA Overview: https://iapp.org/resources/article/connecticut-data-privacy-act/
- W3C Global Privacy Control spec: https://globalprivacycontrol.github.io/gpc-spec/
- Cloudflare Workers D1 docs: https://developers.cloudflare.com/d1/
