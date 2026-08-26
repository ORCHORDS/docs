# New Jersey Data Privacy Act (NJDPA) — Workers & D1 Compliance

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your example project platform serves New Jersey residents. The New Jersey Data Privacy Act (P.L. 2023, c. 266) took effect 15 January 2025. A New Jersey Division of Consumer Affairs inquiry or a privacy audit asks whether the Workers / D1 stack honours opt-out rights, sensitive-data consent, and data-processing agreements (DPAs) required by the Act.

## Context

The NJDPA applies to controllers that, during a calendar year, process personal data of ≥ 100,000 New Jersey consumers OR process data of ≥ 25,000 consumers and derive revenue from selling personal data. Core obligations:

- **Consumer rights** — access, correction, deletion, portability, opt-out of sale / targeted advertising / certain profiling.
- **Sensitive-data opt-in** — race, ethnicity, religion, mental/physical health, sexual orientation, citizenship/immigration status, biometric data, precise geolocation (< 1,750 ft / ~533 m), financial account numbers, union membership, or data of children under 13.
- **Data protection assessments** — required for targeted advertising, sale, certain profiling, sensitive data, and other high-risk activities.
- **Processor DPAs** — contracts must cover processing instructions, confidentiality, sub-processor rules, deletion/return, audits.
- **Universal Opt-Out Mechanism (UOOM)** — must honour technical opt-out signals (GPC) by 15 January 2026.
- Enforcement: NJ Division of Consumer Affairs; 30-day cure period; civil penalties up to $10,000 per violation (treble for wilful).

## 1. D1 Schema for NJDPA Consumer Rights

```sql
-- migrations/0010_njdpa.sql
CREATE TABLE IF NOT EXISTS njdpa_consent (
  user_id       TEXT NOT NULL,
  right_type    TEXT NOT NULL, -- 'sale_optout' | 'targeted_ads_optout' | 'profiling_optout' | 'sensitive_optin'
  data_category TEXT,          -- for sensitive_optin rows
  granted       INTEGER NOT NULL DEFAULT 0,
  source        TEXT,          -- 'explicit_ui' | 'GPC'
  captured_at   TEXT NOT NULL,
  PRIMARY KEY (user_id, right_type, data_category)
);

CREATE TABLE IF NOT EXISTS njdpa_dsr_log (
  request_id   TEXT PRIMARY KEY,
  user_id      TEXT NOT NULL,
  request_type TEXT NOT NULL,
  received_at  TEXT NOT NULL,
  completed_at TEXT,
  status       TEXT NOT NULL DEFAULT 'pending'
);
```

## 2. Opt-Out Signal Middleware

Apply at the edge for every request so sale/targeted-ad pipelines downstream are blocked before any data flows.

```typescript
// workers/njdpa-middleware.ts
export interface Env {
  DB: D1Database;
  KV: KVNamespace;
}

export async function njdpaOptOutMiddleware(
  request: Request,
  env: Env,
  userId: string | null
): Promise<{ saleBlocked: boolean; targetedAdsBlocked: boolean }> {
  // 1. Check GPC header (UOOM)
  const gpcSet = request.headers.get('Sec-GPC') === '1';

  if (!userId) {
    return { saleBlocked: gpcSet, targetedAdsBlocked: gpcSet };
  }

  // 2. Check stored preferences
  const rows = await env.DB.prepare(
    `SELECT right_type, granted FROM njdpa_consent
     WHERE user_id = ? AND right_type IN ('sale_optout','targeted_ads_optout')`
  ).bind(userId).all<{ right_type: string; granted: number }>();

  const prefs = Object.fromEntries(rows.results.map(r => [r.right_type, r.granted === 1]));

  const saleBlocked = gpcSet || (prefs['sale_optout'] ?? false);
  const targetedAdsBlocked = gpcSet || (prefs['targeted_ads_optout'] ?? false);

  // 3. Persist GPC-sourced opt-out for future requests
  if (gpcSet && !prefs['sale_optout']) {
    await recordNJOptOut(env, userId, 'sale_optout', 'GPC');
    await recordNJOptOut(env, userId, 'targeted_ads_optout', 'GPC');
  }

  return { saleBlocked, targetedAdsBlocked };
}

async function recordNJOptOut(
  env: Env,
  userId: string,
  rightType: string,
  source: string
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO njdpa_consent (user_id, right_type, data_category, granted, source, captured_at)
     VALUES (?, ?, NULL, 1, ?, CURRENT_TIMESTAMP)
     ON CONFLICT(user_id, right_type, data_category)
     DO UPDATE SET granted = 1, source = excluded.source, captured_at = excluded.captured_at`
  ).bind(userId, rightType, source).run();
}
```

## 3. Sensitive-Data Opt-In Gate

```typescript
// workers/njdpa-sensitive.ts
const NJ_SENSITIVE_CATEGORIES = new Set([
  'race_ethnicity', 'religion', 'mental_health', 'physical_health',
  'sexual_orientation', 'citizenship_immigration', 'biometric',
  'precise_geolocation', 'financial_account', 'union_membership', 'minor_data'
]);

export async function assertNJSensitiveConsent(
  env: Env,
  userId: string,
  category: string
): Promise<void> {
  if (!NJ_SENSITIVE_CATEGORIES.has(category)) return;

  const row = await env.DB.prepare(
    `SELECT granted FROM njdpa_consent
     WHERE user_id = ? AND right_type = 'sensitive_optin' AND data_category = ?`
  ).bind(userId, category).first<{ granted: number }>();

  if (!row || row.granted !== 1) {
    throw new Error(`NJ NJDPA: opt-in consent required for sensitive category '${category}'`);
  }
}

// In your Worker handler:
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { userId, category } = await request.json<{ userId: string; category: string }>();
    try {
      await assertNJSensitiveConsent(env, userId, category);
    } catch (err) {
      return new Response(JSON.stringify({ error: (err as Error).message }), {
        status: 403,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    // continue processing
    return new Response(JSON.stringify({ ok: true }));
  },
};
```

## 4. Consumer Rights Handler (45-Day Response Deadline)

NJDPA requires responses within 45 days (extendable by 45 days with notice).

```typescript
// workers/njdpa-dsr.ts
type DSRType = 'access' | 'correct' | 'delete' | 'portability' | 'opt_out_confirm';

export async function handleNJDPARequest(
  env: Env,
  requestId: string,
  userId: string,
  type: DSRType,
  payload?: Record<string, unknown>
): Promise<Record<string, unknown>> {
  // Log intake
  await env.DB.prepare(
    `INSERT OR IGNORE INTO njdpa_dsr_log
       (request_id, user_id, request_type, received_at, status)
     VALUES (?, ?, ?, CURRENT_TIMESTAMP, 'processing')`
  ).bind(requestId, userId, type).run();

  let result: Record<string, unknown>;

  switch (type) {
    case 'access':
    case 'portability': {
      const rows = await env.DB.prepare(
        'SELECT * FROM user_data WHERE user_id = ?'
      ).bind(userId).all();
      result = { user_id: userId, records: rows.results };
      break;
    }
    case 'delete': {
      await env.DB.batch([
        env.DB.prepare('DELETE FROM user_data WHERE user_id = ?').bind(userId),
        env.DB.prepare('DELETE FROM njdpa_consent WHERE user_id = ?').bind(userId),
      ]);
      result = { deleted: true };
      break;
    }
    case 'correct': {
      const fields = payload ?? {};
      const sets = Object.keys(fields).map(k => `${k} = ?`).join(', ');
      if (sets) {
        await env.DB.prepare(
          `UPDATE user_data SET ${sets} WHERE user_id = ?`
        ).bind(...Object.values(fields), userId).run();
      }
      result = { corrected: true };
      break;
    }
    default:
      result = { acknowledged: true };
  }

  // Mark complete
  await env.DB.prepare(
    `UPDATE njdpa_dsr_log SET status = 'completed', completed_at = CURRENT_TIMESTAMP
     WHERE request_id = ?`
  ).bind(requestId).run();

  return result;
}
```

## 5. Processor DPA Checklist Stored in D1

Track each sub-processor DPA signed status for audit evidence.

```sql
CREATE TABLE IF NOT EXISTS processor_dpa_register (
  processor_name    TEXT PRIMARY KEY,
  service_type      TEXT NOT NULL,
  dpa_signed_date   TEXT NOT NULL,
  expiry_date       TEXT,
  sub_processors_listed INTEGER DEFAULT 0,
  audit_right_clause    INTEGER DEFAULT 0,
  deletion_clause       INTEGER DEFAULT 0,
  jurisdiction      TEXT NOT NULL DEFAULT 'NJ'
);
```

## Anti-patterns

- **Treating NJ like CCPA** — NJDPA has a 30-day cure period (not 45 as in CCPA); missing it exposes you to immediate civil penalties.
- **Aggregating geolocation data to "area level"** — the NJDPA precise geolocation threshold is ~533 m; aggregating to postal code does not automatically move outside the sensitive category.
- **Relying on consent captured before 15 January 2025** — pre-Act consent records must be re-evaluated against the new opt-in requirements.
- **Using a single opt-out flag for all purposes** — sale, targeted advertising, and profiling are separate rights under NJDPA; store them separately.

## Gotchas

- **Children under 13**: NJDPA adds restrictions layered on top of COPPA; the NJDPA does not independently set a 13-year age threshold but inherits from COPPA.
- **Authenticity verification**: controllers must have a "reasonably accessible and reliable" means to verify identity for DSRs; a magic-link email flow suffices.
- **No revenue safe-harbour for small businesses** — unlike Texas TDPSA, NJDPA uses pure consumer-count thresholds.
- **Cloudflare geo headers** give country, not US state — supplement with IP-to-state lookup or rely on user-declared state at registration.

## Verification

```bash
# Confirm opt-out records for NJ users
wrangler d1 execute PROD_DB --command \
  "SELECT right_type, source, COUNT(*) FROM njdpa_consent
   WHERE right_type LIKE '%_optout' GROUP BY 1,2"

# DSR response-time audit (flag overdue items > 45 days)
wrangler d1 execute PROD_DB --command \
  "SELECT request_id, user_id, request_type, received_at
   FROM njdpa_dsr_log
   WHERE status = 'processing'
     AND julianday('now') - julianday(received_at) > 45"

# Processor DPA coverage
wrangler d1 execute PROD_DB --command \
  "SELECT processor_name, dpa_signed_date, audit_right_clause
   FROM processor_dpa_register WHERE jurisdiction = 'NJ'"
```

## Related

- `ccpa-opt-out.md`
- `connecticut-ctdpa-data-rights-workers.md`
- `vcdpa-virginia-consumer-data-protection-workers.md`
- `data-minimization-workers-d1-pii-redaction.md`
- `gdpr-data-subject-rights-api.md`

## Sources

- New Jersey Data Privacy Act, P.L. 2023, c. 266, effective 15 January 2025
- NJ Division of Consumer Affairs Guidance, December 2024
- IAPP NJDPA Summary — https://iapp.org
- Global Privacy Control spec — https://globalprivacycontrol.org
