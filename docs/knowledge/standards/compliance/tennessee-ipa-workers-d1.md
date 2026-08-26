# Tennessee IPA Consumer Rights — Cloudflare Workers D1

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

Your service processes personal data of Tennessee residents and meets the Tennessee Information Protection Act (TIPA / HB 1181, Tenn. Code Ann. §§ 47-18-3201 et seq., effective 1 July 2025) thresholds: control or process personal data of 175,000+ Tennessee consumers per year, or control or process data of 25,000+ Tennessee consumers while deriving more than 25% of gross revenue from the sale of personal data. TIPA grants consumers the rights of access, correction, deletion, portability, and opt-out of sale, targeted advertising, and profiling with significant effects; the Tennessee AG can seek civil penalties up to USD 7,500 per violation after a 60-day cure period.

---

## Context

TIPA closely resembles the Virginia VCDPA and Connecticut CTDPA in structure but has two notable divergences:

- **No Global Privacy Control (GPC) obligation.** TIPA does not require controllers to recognise the GPC or any universal opt-out mechanism signal as a matter of statute.
- **60-day cure period** (no sunset): the AG must give written notice and 60 days to cure before commencing an action — this does not expire.
- **Sensitive data** (§ 47-18-3203) requires **opt-in consent** before processing: racial/ethnic origin, religious beliefs, mental/physical health condition, sex life/sexual orientation, immigration status, genetic data, biometric data, children's data, and precise geolocation.
- **Data protection assessments (DPAs)** required before targeted advertising, sale, profiling with significant effects, and sensitive data processing.
- **Response deadline**: 45 calendar days, extendable once by 45 days with written notice to the consumer; appeal response within 60 days of receiving the appeal.

On Cloudflare Workers, the consent gate, opt-out registry, DSR ticket queue, and DPA log all live in D1; portability exports go to an R2 bucket.

---

## 1. Sensitive Data Opt-In Gate

All processing of TIPA-sensitive categories is prohibited unless a valid opt-in consent record exists for the consumer.

```typescript
// workers/tipa-sensitive-consent.ts
import { Env } from './types';

const TIPA_SENSITIVE_CATEGORIES = [
  'racial_ethnic_origin', 'religious_belief', 'mental_health_condition',
  'physical_health_condition', 'sex_life_sexual_orientation',
  'immigration_status', 'genetic_data', 'biometric_data',
  'childrens_data', 'precise_geolocation',
] as const;
type TipaSensitiveCategory = typeof TIPA_SENSITIVE_CATEGORIES[number];

export async function grantTipaSensitiveConsent(
  env: Env,
  consumerId: string,
  categories: TipaSensitiveCategory[],
  purpose: string,
  consentText: string,
  request: Request,
): Promise<string> {
  const id = crypto.randomUUID();
  await env.DB.prepare(
    `INSERT INTO tipa_sensitive_consent
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

export async function revokeTipaSensitiveConsent(
  env: Env,
  consumerId: string,
  category: TipaSensitiveCategory,
): Promise<void> {
  await env.DB.prepare(
    `UPDATE tipa_sensitive_consent SET revoked_at = datetime('now')
     WHERE consumer_id = ? AND revoked_at IS NULL
       AND categories LIKE '%' || ? || '%'`,
  ).bind(consumerId, category).run();
}

export async function hasTipaSensitiveConsent(
  env: Env,
  consumerId: string,
  category: TipaSensitiveCategory,
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM tipa_sensitive_consent
     WHERE consumer_id = ? AND revoked_at IS NULL
       AND categories LIKE '%' || ? || '%'
     LIMIT 1`,
  ).bind(consumerId, category).first();
  return row !== null;
}
```

---

## 2. Opt-Out Registry — Sale, Targeted Advertising, Profiling

TIPA § 47-18-3207 requires controllers to offer opt-out mechanisms for sale, targeted advertising, and profiling that produces significant decisions. The opt-out must be made effective within 15 days of receipt.

```typescript
// workers/tipa-opt-out.ts
type TipaOptOutScope =
  | 'sale' | 'targeted_advertising' | 'profiling_significant_decisions';

export async function recordTipaOptOut(
  env: Env,
  consumerId: string,
  scopes: TipaOptOutScope[],
  request: Request,
): Promise<void> {
  for (const scope of scopes) {
    await env.DB.prepare(
      `INSERT OR REPLACE INTO tipa_opt_out
       (consumer_id, scope, recorded_at, effective_by, ip_address)
       VALUES (?, ?, datetime('now'),
               datetime('now', '+15 days'), ?)`,
    ).bind(consumerId, scope, request.headers.get('CF-Connecting-IP') ?? 'unknown').run();
  }
}

export async function isTipaOptedOut(
  env: Env,
  consumerId: string,
  scope: TipaOptOutScope,
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM tipa_opt_out
     WHERE consumer_id = ? AND scope = ?
       AND effective_by <= datetime('now')
     LIMIT 1`,
  ).bind(consumerId, scope).first();
  return row !== null;
}

export async function rescindTipaOptOut(
  env: Env,
  consumerId: string,
  scope: TipaOptOutScope,
): Promise<void> {
  await env.DB.prepare(
    `DELETE FROM tipa_opt_out WHERE consumer_id = ? AND scope = ?`,
  ).bind(consumerId, scope).run();
}
```

---

## 3. Consumer Rights — 45-Day Clock with Appeal

```typescript
// workers/tipa-dsr.ts
type TipaRight =
  | 'access' | 'correction' | 'deletion'
  | 'portability' | 'opt_out_sale'
  | 'opt_out_targeted_advertising' | 'opt_out_profiling';

interface TipaDsrTicket {
  id: string;
  consumerId: string;
  right: TipaRight;
  receivedAt: string;
  deadlineAt: string;          // 45 days
  extendedDeadlineAt: string | null;  // up to 90 days total
  appealDeadlineAt: string | null;    // 60 days from denial
  status: 'open' | 'extended' | 'denied' | 'appeal_pending' | 'completed';
  denialReason: string | null;
}

export async function openTipaRequest(
  env: Env,
  consumerId: string,
  right: TipaRight,
): Promise<TipaDsrTicket> {
  const id = crypto.randomUUID();
  const now = new Date();
  const deadline = new Date(now.getTime() + 45 * 86_400_000);

  await env.DB.prepare(
    `INSERT INTO tipa_dsr
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

export async function extendTipaRequest(
  env: Env,
  ticketId: string,
  noticeToConsumer: string,
): Promise<void> {
  const newDeadline = new Date(Date.now() + 45 * 86_400_000).toISOString();
  await env.DB.prepare(
    `UPDATE tipa_dsr
     SET status = 'extended', extended_deadline_at = ?, extension_notice = ?
     WHERE id = ? AND status = 'open'`,
  ).bind(newDeadline, noticeToConsumer, ticketId).run();
}

export async function denyTipaRequest(
  env: Env,
  ticketId: string,
  reason: string,
): Promise<void> {
  const appealDeadline = new Date(Date.now() + 60 * 86_400_000).toISOString();
  await env.DB.prepare(
    `UPDATE tipa_dsr
     SET status = 'denied', denial_reason = ?, appeal_deadline_at = ?
     WHERE id = ?`,
  ).bind(reason, appealDeadline, ticketId).run();
}

export async function exportTipaPortabilityPackage(
  env: Env,
  ticketId: string,
  consumerId: string,
): Promise<string> {
  // Gather the consumer's stored data from the main tables
  const profileRow = await env.DB.prepare(
    `SELECT id, email, name, phone, created_at FROM users WHERE id = ?`,
  ).bind(consumerId).first<Record<string, unknown>>();

  const { results: consentRows } = await env.DB.prepare(
    `SELECT purpose, categories, granted_at, revoked_at
     FROM tipa_sensitive_consent WHERE consumer_id = ?`,
  ).bind(consumerId).all();

  const payload = { profile: profileRow, consentRecords: consentRows };
  const key = `tipa-portability/${consumerId}/${ticketId}.json`;

  await env.R2.put(key, JSON.stringify(payload), {
    httpMetadata: { contentType: 'application/json' },
  });

  await env.DB.prepare(
    `UPDATE tipa_dsr SET status = 'completed', completed_at = datetime('now'),
     r2_export_key = ? WHERE id = ?`,
  ).bind(key, ticketId).run();

  return key;
}

// Cron: alert on tickets approaching deadline
export async function alertTipaDeadlines(env: Env): Promise<void> {
  const horizon = new Date(Date.now() + 5 * 86_400_000).toISOString();
  const { results } = await env.DB.prepare(
    `SELECT id, consumer_id, right,
            COALESCE(extended_deadline_at, deadline_at) AS effective_deadline
     FROM tipa_dsr
     WHERE status IN ('open', 'extended')
       AND COALESCE(extended_deadline_at, deadline_at) <= ?`,
  ).bind(horizon).all<{ id: string; consumer_id: string; right: string; effective_deadline: string }>();

  for (const r of results) {
    await env.ALERTS_QUEUE.send({ type: 'tipa_deadline_warning', ...r });
  }
}
```

---

## 4. Data Protection Assessment Registry

TIPA § 47-18-3209 requires a completed DPA before beginning targeted advertising, sale, profiling with significant decisions, sensitive data processing, or any other processing presenting a heightened risk. The AG may request DPAs during enforcement.

```typescript
// workers/tipa-dpa-registry.ts
type TipaDpaActivity =
  | 'targeted_advertising' | 'sale_of_personal_data'
  | 'profiling_significant_decisions' | 'sensitive_data_processing'
  | 'other_heightened_risk';

export async function registerTipaDpa(
  env: Env,
  activity: TipaDpaActivity,
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
    `INSERT INTO tipa_dpa_registry
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

- **Importing CTDPA/VCDPA GPC middleware and assuming it applies.** TIPA does not require recognition of the Global Privacy Control; honour GPC only if you have separately adopted it as a best practice, but do not conflate it with a legal obligation under TIPA.
- **Starting the 45-day response clock on verification completion.** TIPA starts the clock at receipt; verification effort counts inside the 45-day window.
- **Skipping the internal appeal mechanism.** Denying a consumer request without offering an internal appeal process is a separate non-compliance issue even if the denial itself was lawful.
- **Treating the 60-day cure period as permanent immunity.** The cure period under TIPA has no statutory sunset, but a second violation of the same type after a cure notice is unlikely to receive another cure opportunity.
- **Failing to document DPAs before beginning processing.** A DPA completed after targeted advertising or sensitive data processing has already begun provides no protection — timing is material.

---

## Gotchas

- TIPA's thresholds are based on Tennessee **consumers** — residents of Tennessee acting in an individual or household capacity — not all data subjects processed by the controller.
- Employee data and business-to-business contact data are excluded from TIPA's scope.
- The right to correction (rectification) is explicit in TIPA; systems that cannot support in-place corrections must route to a manual workflow within the 45-day window.
- Cloudflare Workers receive the `CF-IPCountry` and `cf.region` (state) fields from the incoming request; use these to identify Tennessee residents dynamically when explicit state data is not available in the session.
- Biometric data requires opt-in consent even for internal authentication and anti-fraud uses — there is no carve-out equivalent to Illinois BIPA's security-purpose exemption.

---

## Verification

```bash
# 1. Open tickets approaching 45-day deadline
wrangler d1 execute DB --command \
  "SELECT id, right, COALESCE(extended_deadline_at, deadline_at) AS due
   FROM tipa_dsr WHERE status IN ('open','extended')
   AND due <= datetime('now', '+5 days') ORDER BY due;"

# 2. Denied requests pending appeal response
wrangler d1 execute DB --command \
  "SELECT id, consumer_id, right, appeal_deadline_at
   FROM tipa_dsr WHERE status = 'denied'
   AND appeal_deadline_at IS NOT NULL
   AND appeal_deadline_at >= datetime('now');"

# 3. Sensitive consent grants still active
wrangler d1 execute DB --command \
  "SELECT consumer_id, categories, purpose, granted_at
   FROM tipa_sensitive_consent WHERE revoked_at IS NULL
   ORDER BY granted_at DESC LIMIT 20;"

# 4. DPA coverage by activity
wrangler d1 execute DB --command \
  "SELECT activity, COUNT(*) AS total, MAX(completed_at) AS latest
   FROM tipa_dpa_registry GROUP BY activity;"
```

---

## Related

- `connecticut-ctdpa-data-rights-workers.md`
- `vcdpa-virginia-consumer-data-protection-workers.md`
- `us-state-privacy-laws-2026-multi-state-compliance.md`
- `gdpr-data-subject-rights-api.md`
- `cookie-consent-management-platform.md`

---

## Sources

- Tennessee Information Protection Act, HB 1181 (Tenn. Code Ann. §§ 47-18-3201 et seq.): https://wapp.capitol.tn.gov/apps/Billinfo/default.aspx?BillNumber=HB1181&ga=113
- Tennessee AG Consumer Protection Division: https://www.tn.gov/attorneygeneral/section/consumer-protection.html
- IAPP US State Privacy Legislation Tracker: https://iapp.org/resources/article/us-state-privacy-legislation-tracker/
