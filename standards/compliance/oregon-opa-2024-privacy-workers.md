# Oregon OPA 2024 Privacy — Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Your service controls or processes personal data of Oregon residents and meets at least one OPA threshold: (a) during a calendar year, control or process personal data of 100,000+ Oregon consumers (excluding data processed solely for payment transactions), or (b) control or process personal data of 25,000+ consumers while deriving 25 %+ of gross revenue from selling personal data. The Oregon Consumer Privacy Act (Oregon OPA, HB 2051, codified at ORS §§ 646A.570 – 646A.590, effective 1 July 2024; nonprofit exemption extended to 1 July 2025) is one of the broader US state privacy laws, introducing a unique requirement to disclose the **list of third parties** to whom personal data was disclosed — with AG enforcement and civil penalties up to USD 7,500 per violation.

---

## Context

The Oregon OPA closely tracks the Virginia/Colorado/Connecticut cluster but adds notable requirements:

- **Consumer rights** (ORS § 646A.576): access, correction, deletion, portability, opt-out of sale/targeted advertising/profiling with significant effects, and a **right to know the categories of third parties** to whom data was disclosed.
- **Sensitive data** (ORS § 646A.570): racial/ethnic origin, religious beliefs, mental/physical health condition, sex life/sexual orientation, citizenship/immigration, genetic/biometric data, children's data, precise geolocation, union membership, status as a victim of crime — requires **opt-in consent** before processing.
- **GPC recognition** (ORS § 646A.576(1)(d)): controllers must process Global Privacy Control signals as valid opt-outs; the AG may specify additional signals by rule by 1 January 2026.
- **Data protection assessments (DPAs)** (ORS § 646A.581): required before targeted advertising, sale, high-risk profiling, sensitive data processing, or other activities presenting a heightened risk of harm.
- **Response deadline**: 45 calendar days from receipt; extendable by 45 days with notice. Appeal must be completed within 45 days of denial.
- **No private right of action**: AG enforcement only.
- **Third-party disclosure list**: when a consumer exercises access rights, the controller must provide a list of the categories of third parties to whom personal data has been disclosed, along with the categories of personal data disclosed.

---

## 1. Sensitive Data Opt-In Consent Gate (Including Union Membership and Crime Victimhood)

Oregon OPA expands the sensitive category list beyond most peer laws to include union membership and crime-victim status.

```typescript
// workers/opa-sensitive-consent.ts
import { Env } from './types';

const OPA_SENSITIVE = [
  'racial_ethnic_origin', 'religious_belief', 'mental_health_condition',
  'physical_health_condition', 'sex_life_sexual_orientation',
  'citizenship_immigration', 'genetic_data', 'biometric_data',
  'childrens_data', 'precise_geolocation',
  'union_membership',        // Oregon-specific
  'crime_victim_status',     // Oregon-specific
] as const;
type OpaSensitiveCategory = typeof OPA_SENSITIVE[number];

export async function grantOpaSensitiveConsent(
  env: Env,
  consumerId: string,
  categories: OpaSensitiveCategory[],
  purpose: string,
  consentText: string,
  request: Request,
): Promise<string> {
  const id = crypto.randomUUID();

  await env.DB.prepare(
    `INSERT INTO opa_sensitive_consent
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

export async function hasOpaSensitiveConsent(
  env: Env,
  consumerId: string,
  category: OpaSensitiveCategory,
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM opa_sensitive_consent
     WHERE consumer_id = ? AND revoked_at IS NULL
       AND categories LIKE '%' || ? || '%'
     LIMIT 1`,
  ).bind(consumerId, category).first();
  return row !== null;
}
```

---

## 2. Third-Party Disclosure Ledger

Oregon OPA uniquely requires controllers to disclose the **list of third-party categories** and the **categories of data** shared with them when a consumer makes an access request.

```typescript
// workers/opa-third-party-ledger.ts
interface OpaThirdPartyDisclosure {
  id: string;
  consumerId: string;
  thirdPartyCategory: string;   // e.g. 'advertising_network', 'analytics_provider'
  thirdPartyName: string;
  dataCategories: string[];     // categories of data disclosed
  disclosurePurpose: string;
  disclosedAt: string;
  retentionPeriod: string;      // ISO-8601 duration, e.g. 'P1Y'
}

export async function recordOpaThirdPartyDisclosure(
  env: Env,
  disclosure: Omit<OpaThirdPartyDisclosure, 'id'>,
): Promise<string> {
  const id = crypto.randomUUID();

  await env.DB.prepare(
    `INSERT INTO opa_third_party_disclosures
     (id, consumer_id, third_party_category, third_party_name,
      data_categories, disclosure_purpose, disclosed_at, retention_period)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
  ).bind(
    id, disclosure.consumerId, disclosure.thirdPartyCategory,
    disclosure.thirdPartyName, JSON.stringify(disclosure.dataCategories),
    disclosure.disclosurePurpose, disclosure.disclosedAt,
    disclosure.retentionPeriod,
  ).run();

  return id;
}

// Return the disclosure list for an access request response
export async function getOpaThirdPartyList(
  env: Env,
  consumerId: string,
): Promise<Array<{ thirdPartyCategory: string; dataCategories: string[] }>> {
  const { results } = await env.DB.prepare(
    `SELECT DISTINCT third_party_category, data_categories
     FROM opa_third_party_disclosures
     WHERE consumer_id = ?
     ORDER BY third_party_category`,
  ).bind(consumerId).all<{ third_party_category: string; data_categories: string }>();

  return results.map((r) => ({
    thirdPartyCategory: r.third_party_category,
    dataCategories: JSON.parse(r.data_categories) as string[],
  }));
}
```

---

## 3. GPC Opt-Out Recognition

Oregon OPA mandates GPC processing; the AG is empowered to designate additional opt-out signals by rule from 1 January 2026.

```typescript
// workers/opa-gpc-middleware.ts
export async function opaGpcMiddleware(
  env: Env,
  request: Request,
  consumerId: string | null,
): Promise<{ applied: boolean }> {
  if (!consumerId || request.headers.get('Sec-GPC') !== '1') {
    return { applied: false };
  }

  await env.DB.prepare(
    `INSERT OR REPLACE INTO opa_opt_out
     (consumer_id, signal, scope, recorded_at, ip_address)
     VALUES (?, 'gpc', 'sale_and_targeted_advertising', datetime('now'), ?)`,
  ).bind(
    consumerId,
    request.headers.get('CF-Connecting-IP') ?? 'unknown',
  ).run();

  return { applied: true };
}

export async function isOpaOptedOut(
  env: Env,
  consumerId: string,
  scope: 'sale' | 'targeted_advertising' | 'profiling',
): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM opa_opt_out
     WHERE consumer_id = ?
       AND (scope = ? OR scope = 'all'
            OR scope = 'sale_and_targeted_advertising')
     LIMIT 1`,
  ).bind(consumerId, scope).first();
  return row !== null;
}
```

---

## 4. Consumer Rights — 45-Day Workflow with Third-Party List

The access response must include the third-party disclosure list — which means the DSR handler must query the third-party ledger before responding.

```typescript
// workers/opa-dsr.ts
type OpaRight =
  | 'access' | 'correction' | 'deletion' | 'portability'
  | 'opt_out_sale' | 'opt_out_targeted_advertising'
  | 'opt_out_profiling' | 'third_party_list';

interface OpaDsrTicket {
  id: string;
  consumerId: string;
  right: OpaRight;
  receivedAt: string;
  deadlineAt: string;
  extendedDeadlineAt: string | null;
  appealDeadlineAt: string | null; // 45 days from denial
  status: 'open' | 'extended' | 'completed' | 'denied' | 'appeal_pending';
  denialReason: string | null;
}

export async function openOpaRequest(
  env: Env,
  consumerId: string,
  right: OpaRight,
): Promise<OpaDsrTicket> {
  const id = crypto.randomUUID();
  const now = new Date();
  const deadline = new Date(now.getTime() + 45 * 86_400_000);

  await env.DB.prepare(
    `INSERT INTO opa_dsr
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

export async function fulfillOpaAccessRequest(
  env: Env,
  ticketId: string,
  consumerId: string,
): Promise<{ personalDataSummary: unknown; thirdParties: unknown[] }> {
  // Fetch the personal data summary (implementation-specific)
  const personalDataSummary = await env.DB.prepare(
    `SELECT * FROM user_profiles WHERE consumer_id = ?`,
  ).bind(consumerId).first();

  // Oregon-specific: include the third-party disclosure list
  const thirdParties = await getOpaThirdPartyList(env, consumerId);

  await env.DB.prepare(
    `UPDATE opa_dsr SET status = 'completed' WHERE id = ?`,
  ).bind(ticketId).run();

  return { personalDataSummary, thirdParties };
}

async function getOpaThirdPartyList(env: Env, consumerId: string) {
  const { results } = await env.DB.prepare(
    `SELECT DISTINCT third_party_category, data_categories
     FROM opa_third_party_disclosures WHERE consumer_id = ?`,
  ).bind(consumerId).all<{ third_party_category: string; data_categories: string }>();

  return results.map((r) => ({
    category: r.third_party_category,
    dataCategories: JSON.parse(r.data_categories),
  }));
}

export async function denyOpaRequest(
  env: Env,
  ticketId: string,
  reason: string,
): Promise<void> {
  const appealDeadline = new Date(Date.now() + 45 * 86_400_000).toISOString();
  await env.DB.prepare(
    `UPDATE opa_dsr
     SET status = 'denied', denial_reason = ?, appeal_deadline_at = ?
     WHERE id = ?`,
  ).bind(reason, appealDeadline, ticketId).run();
}
```

---

## Anti-patterns

- **Omitting union membership and crime-victim status from sensitive data lists.** Oregon expands the sensitive category definition beyond most peer laws; controllers who port Virginia/Connecticut configuration without adding these two categories are non-compliant.
- **Responding to access requests without the third-party disclosure list.** This is the most Oregon-specific obligation — failing to include it in access responses is a structural violation.
- **Setting the appeal deadline to 60 days.** Oregon OPA's appeal response deadline is 45 days (not 60 like Connecticut); verify per-state appeal deadlines in multi-state tooling.
- **Treating nonprofits as permanently exempt.** The nonprofit exemption expired 1 July 2025 — nonprofits meeting the data-volume threshold are now subject.

---

## Gotchas

- Oregon OPA's definition of "sale" includes exchange for **any valuable consideration** (monetary or otherwise) — broader than Utah.
- The AG may by rule designate additional opt-out signals beyond GPC effective 1 January 2026; monitor Oregon AG rulemaking.
- Status as a crime victim is Oregon-specific; most multi-state compliance toolkits do not include it — verify your sensitive data taxonomy.
- Payment transaction data processed solely for completing a payment is excluded from the 100,000-consumer threshold count.
- Precise geolocation is defined as less than 1,750 feet radius, consistent with peer state laws.

---

## Verification

```bash
# 1. Sensitive consent coverage including Oregon-specific categories
wrangler d1 execute DB --command \
  "SELECT consumer_id, categories, granted_at FROM opa_sensitive_consent
   WHERE revoked_at IS NULL
     AND (categories LIKE '%union_membership%'
       OR categories LIKE '%crime_victim_status%')
   ORDER BY granted_at DESC LIMIT 20;"

# 2. Third-party disclosure ledger coverage
wrangler d1 execute DB --command \
  "SELECT third_party_category, COUNT(*) AS disclosures
   FROM opa_third_party_disclosures GROUP BY third_party_category;"

# 3. Open DSR tickets near deadline
wrangler d1 execute DB --command \
  "SELECT id, right, COALESCE(extended_deadline_at, deadline_at) AS due
   FROM opa_dsr WHERE status IN ('open','extended')
   AND due <= datetime('now', '+5 days');"

# 4. GPC opt-out count
wrangler d1 execute DB --command \
  "SELECT COUNT(*) AS gpc_total FROM opa_opt_out WHERE signal = 'gpc';"
```

---

## Related

- `connecticut-ctdpa-data-rights-workers.md`
- `montana-mcdpa-consumer-rights-workers.md`
- `vcdpa-virginia-consumer-data-protection-workers.md`
- `us-state-privacy-laws-2026-multi-state-compliance.md`
- `gdpr-data-subject-rights-api.md`

---

## Sources

- Oregon Consumer Privacy Act (HB 2051, ORS §§ 646A.570 – 646A.590): https://olis.oregonlegislature.gov/liz/2023R1/Downloads/MeasureDocument/HB2051/Enrolled
- Oregon AG Privacy Resources: https://www.doj.state.or.us/consumer-protection/privacy/
- IAPP Oregon OPA Overview: https://iapp.org/resources/article/oregon-consumer-privacy-act/
- W3C Global Privacy Control spec: https://globalprivacycontrol.github.io/gpc-spec/
- Cloudflare Workers D1 docs: https://developers.cloudflare.com/d1/
