# Maryland Online Data Privacy Act (MODPA) — Workers & D1 Compliance

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your example project app processes personal data of Maryland residents. MODPA (MD Code, Commercial Law § 14-4601 et seq.) took effect 1 October 2025 and contains stricter data-minimisation rules than any other US state law, plus a broader sensitive-data definition. A regulator audit or a privacy assessment raises the question: does your Cloudflare Workers / D1 stack satisfy MODPA obligations?

## Context

MODPA applies to any controller that, during a calendar year, processes personal data of ≥ 35,000 Maryland consumers OR processes data of ≥ 10,000 consumers AND derives > 20 % of gross revenue from selling personal data. Key differentiators vs. other state laws:

- **Data minimisation is codified** — collection limited to what is "reasonably necessary and proportionate" to the disclosed purpose; no catch-all "legitimate business purposes" escape.
- **Sensitive data opt-in** — biometric, health, financial, geolocation (< 1,750 m radius), racial/ethnic, religious, sexual orientation, immigration status, or data of minors under 18 all require affirmative consent.
- **No broad B2B exemption** — employee data and B2B contacts are only narrowly carved out.
- **Universal Opt-Out Mechanism (UOOM)** — controllers must honour opt-out signals from browser/OS settings by 1 January 2026.
- **Data protection assessments (DPAs)** required before processing activities that present "heightened risk" (targeted advertising, sale, profiling, sensitive data).

Enforcement: Maryland Attorney General; no private right of action; 60-day cure period (sunsets 1 October 2027).

## 1. Consent Gate for Sensitive Data

Store consent decisions in D1 and enforce them in the Worker before any sensitive-data write path.

```typescript
// workers/modpa-consent.ts
export interface Env {
  DB: D1Database;
}

export async function checkMarylandSensitiveConsent(
  env: Env,
  userId: string,
  dataCategory: string
): Promise<boolean> {
  const SENSITIVE = new Set([
    'biometric', 'health', 'financial', 'precise_geolocation',
    'race_ethnicity', 'religion', 'sexual_orientation',
    'immigration_status', 'minor_data'
  ]);
  if (!SENSITIVE.has(dataCategory)) return true; // not sensitive

  const row = await env.DB.prepare(
    `SELECT opted_in, captured_at FROM modpa_consent
     WHERE user_id = ? AND data_category = ? AND jurisdiction = 'MD'`
  ).bind(userId, dataCategory).first<{ opted_in: number; captured_at: string }>();

  return row?.opted_in === 1;
}

export async function recordMarylandConsent(
  env: Env,
  userId: string,
  dataCategory: string,
  optedIn: boolean,
  ipAddress: string
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO modpa_consent
       (user_id, data_category, jurisdiction, opted_in, ip_address, captured_at)
     VALUES (?, ?, 'MD', ?, ?, CURRENT_TIMESTAMP)
     ON CONFLICT(user_id, data_category, jurisdiction)
     DO UPDATE SET opted_in = excluded.opted_in,
                   ip_address = excluded.ip_address,
                   captured_at = excluded.captured_at`
  ).bind(userId, dataCategory, optedIn ? 1 : 0, ipAddress).run();
}
```

D1 schema:
```sql
CREATE TABLE IF NOT EXISTS modpa_consent (
  user_id       TEXT NOT NULL,
  data_category TEXT NOT NULL,
  jurisdiction  TEXT NOT NULL DEFAULT 'MD',
  opted_in      INTEGER NOT NULL DEFAULT 0,
  ip_address    TEXT,
  captured_at   TEXT NOT NULL,
  PRIMARY KEY (user_id, data_category, jurisdiction)
);
```

## 2. Data Minimisation Enforcement at Ingest

MODPA § 14-4604(a) bars collection of fields not "reasonably necessary" for the stated purpose. Enforce at the Worker edge with a purpose-to-fields allowlist.

```typescript
// workers/modpa-minimise.ts
type Purpose = 'account_creation' | 'order_fulfillment' | 'marketing_analytics';

const ALLOWED_FIELDS: Record<Purpose, Set<string>> = {
  account_creation:   new Set(['email', 'display_name', 'password_hash', 'country']),
  order_fulfillment:  new Set(['email', 'shipping_address', 'payment_token', 'order_items']),
  marketing_analytics: new Set(['anonymous_id', 'page_path', 'referrer', 'utm_source']),
};

export function stripExcessFields(
  payload: Record<string, unknown>,
  purpose: Purpose
): Record<string, unknown> {
  const allowed = ALLOWED_FIELDS[purpose];
  return Object.fromEntries(
    Object.entries(payload).filter(([key]) => allowed.has(key))
  );
}

// Usage in a Worker handler:
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const body = await request.json<Record<string, unknown>>();
    const purpose = (request.headers.get('X-Processing-Purpose') ?? 'account_creation') as Purpose;
    const clean = stripExcessFields(body, purpose);
    // proceed with `clean` only
    return new Response(JSON.stringify({ ok: true }));
  },
};
```

## 3. Universal Opt-Out Mechanism (UOOM) Signal Handling

From 1 January 2026 controllers must honour browser/OS opt-out signals (GPC header, Sec-GPC).

```typescript
// workers/modpa-uoom.ts
export function isGlobalPrivacyControlSet(request: Request): boolean {
  return request.headers.get('Sec-GPC') === '1';
}

export async function applyUOOMForMaryland(
  env: Env,
  request: Request,
  userId: string | null
): Promise<void> {
  if (!isGlobalPrivacyControlSet(request)) return;

  // Best-effort: record opt-out for identified users
  if (userId) {
    await env.DB.prepare(
      `INSERT INTO sale_optout (user_id, jurisdiction, source, opted_out_at)
       VALUES (?, 'MD', 'GPC', CURRENT_TIMESTAMP)
       ON CONFLICT(user_id, jurisdiction) DO UPDATE
       SET source = 'GPC', opted_out_at = CURRENT_TIMESTAMP`
    ).bind(userId).run();
  }
  // For anonymous visitors: set a KV flag keyed by fingerprint / session
}
```

## 4. Data Protection Assessment (DPA) Registry

Log assessments in D1 with purpose, risk level, and approval date; reference them during audit.

```typescript
// workers/modpa-dpa-registry.ts
interface DPAEntry {
  assessment_id: string;
  processing_activity: string;
  risk_category: 'targeted_advertising' | 'sale' | 'profiling' | 'sensitive_data';
  risk_level: 'high' | 'medium';
  benefits_outweigh_risks: boolean;
  approved_by: string;
  approved_at: string;
  next_review_date: string;
}

export async function registerDPA(env: Env, entry: DPAEntry): Promise<void> {
  await env.DB.prepare(
    `INSERT OR REPLACE INTO modpa_dpa_registry
       (assessment_id, processing_activity, risk_category, risk_level,
        benefits_outweigh_risks, approved_by, approved_at, next_review_date)
     VALUES (?,?,?,?,?,?,?,?)`
  ).bind(
    entry.assessment_id, entry.processing_activity, entry.risk_category,
    entry.risk_level, entry.benefits_outweigh_risks ? 1 : 0,
    entry.approved_by, entry.approved_at, entry.next_review_date
  ).run();
}
```

## 5. Consumer Rights Endpoint (Access / Deletion / Correction / Portability)

```typescript
// workers/modpa-dsr.ts
export async function handleMODPARequest(
  env: Env,
  type: 'access' | 'delete' | 'correct' | 'portability',
  userId: string,
  correction?: Record<string, unknown>
): Promise<Record<string, unknown>> {
  switch (type) {
    case 'access':
    case 'portability': {
      const rows = await env.DB.prepare(
        'SELECT * FROM user_data WHERE user_id = ?'
      ).bind(userId).all();
      return { data: rows.results };
    }
    case 'delete': {
      await env.DB.prepare('DELETE FROM user_data WHERE user_id = ?').bind(userId).run();
      await env.DB.prepare('DELETE FROM modpa_consent WHERE user_id = ?').bind(userId).run();
      return { deleted: true };
    }
    case 'correct': {
      const sets = Object.keys(correction ?? {}).map(k => `${k} = ?`).join(', ');
      const vals = Object.values(correction ?? {});
      await env.DB.prepare(
        `UPDATE user_data SET ${sets} WHERE user_id = ?`
      ).bind(...vals, userId).run();
      return { corrected: true };
    }
  }
}
```

## Anti-patterns

- **Collecting device fingerprints for analytics** and calling it "necessary" — data minimisation bars this; use anonymous session IDs instead.
- **Relying on a generic "legitimate business purpose" basis** — MODPA does not recognise this; every collection must map to the disclosed purpose.
- **Ignoring GPC on unauthenticated requests** — UOOM applies even when the user is not logged in; honour it at the edge via KV.
- **Skipping DPAs for lookalike-audience uploads** — this is a sale/targeted-advertising activity and requires an assessment.
- **Re-using CCPA consent records** — MODPA's sensitive-data definition (e.g., precise geolocation radius 1,750 m) differs from CCPA/CPRA; obtain separate signals.

## Gotchas

- MODPA's **minor threshold is under 18**, not 13 (COPPA) or 16 (some states) — age verification must be stricter.
- The **cure period sunsets 1 October 2027**; after that the AG may sue without notice.
- **No revenue-based small-business exemption** — the thresholds are consumer-count based only.
- Cloudflare's **`CF-IPCountry` header identifies country, not US state** — use a geo-IP database for state-level routing or collect state during sign-up.

## Verification

```bash
# 1. Confirm consent table exists and has MD entries
wrangler d1 execute PROD_DB --command \
  "SELECT data_category, COUNT(*) FROM modpa_consent WHERE jurisdiction='MD' GROUP BY 1"

# 2. Verify GPC handling in staging
curl -s -H "Sec-GPC: 1" https://staging.example.com/api/profile | jq .

# 3. List DPA registry
wrangler d1 execute PROD_DB --command \
  "SELECT processing_activity, risk_category, approved_at FROM modpa_dpa_registry"
```

## Related

- `ccpa-opt-out.md`
- `connecticut-ctdpa-data-rights-workers.md`
- `data-minimization-workers-d1-pii-redaction.md`
- `gdpr-data-subject-rights-api.md`
- `data-retention-automated-deletion-workers.md`

## Sources

- Maryland Online Data Privacy Act, MD Code, Commercial Law §§ 14-4601 – 14-4627 (2024)
- Maryland Attorney General Guidance on MODPA, January 2025
- Global Privacy Control specification — https://globalprivacycontrol.org
- IAPP State Privacy Law Tracker — https://iapp.org/resources/article/us-state-privacy-legislation-tracker/
