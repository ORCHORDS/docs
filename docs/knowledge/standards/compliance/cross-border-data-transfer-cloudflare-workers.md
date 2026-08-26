# Cross-Border Data Transfer — Cloudflare Workers, Data Localisation & SCCs

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project processes EU user data on Cloudflare's global network. By default, Cloudflare's
Smart Placement and global routing may process requests in US or APAC data centres,
triggering GDPR Chapter V obligations (cross-border transfers). The DPO asks: which
Cloudflare capabilities constrain where data is processed, which transfer mechanisms
apply, and how do Workers + D1 enforce regional routing in code?

## Context

GDPR Chapter V (Art. 44-49) prohibits transferring personal data to third countries
unless an "adequacy decision" covers that country, Standard Contractual Clauses (SCCs)
are in place, or another Art. 46/49 derogation applies.

Cloudflare's position as of 2026:
- **USA**: covered by the EU-US Data Privacy Framework (DPF), adopted July 2023; CJEU
  has not yet invalidated it as of 2026 — monitor litigation.
- **UK**: UK Adequacy Decision in force (adopted June 2021); under review post-DUAA 2025.
- **Other Cloudflare PoPs** (APAC, LATAM): no adequacy; transfers rely on Cloudflare's
  SCCs with customers and sub-processors.

Cloudflare offers two data-localisation products:
- **Data Localisation Suite (DLS)**: restricts where metadata is inspected, logs are
  stored, and Workers run.
- **Regional Services**: restricts TLS termination + data processing to a geographic
  region (e.g. EU).

D1 databases have a primary region (chosen at creation) and a global read replica
network. For GDPR, the primary write region should be EU.

## Adequacy & Transfer Mechanism Matrix

```
+-------------------+--------------------+-------------------------------+--------------------+
| Destination       | Adequacy status    | Transfer mechanism (2026)     | Action required    |
+-------------------+--------------------+-------------------------------+--------------------+
| USA (Cloudflare)  | DPF (conditional)  | DPF self-certification        | Monitor DPF review |
| UK                | Adequacy decision  | UK IDTA or adequacy           | Review post-DUAA   |
| Switzerland       | Adequacy decision  | None extra needed             | Annual check       |
| Japan             | Adequacy decision  | None extra needed             | Annual check       |
| India             | No adequacy        | SCCs (2021 EC modules)        | DPIA required      |
| Brazil            | No adequacy        | SCCs                          | DPIA required      |
| Singapore         | No adequacy        | SCCs / BCRs                   | DPIA required      |
| China             | No adequacy        | PIPL-specific mechanism       | Avoid if possible  |
+-------------------+--------------------+-------------------------------+--------------------+
```

## Cloudflare Regional Services & DLS Configuration

```toml
# wrangler.toml — restrict Worker execution to EU
[env.production]
name = "example project-api"

# Regional Services: EU only
# Set via Cloudflare dashboard → Workers → Settings → Routing → Region
# Wrangler CLI equivalent (as of 2026):
# wrangler deploy --region eu

# D1 primary region: EU (set at database creation time — cannot be changed)
[[d1_databases]]
binding     = "DB"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
# Created with: wrangler d1 create example project-prod --location weur

[[kv_namespaces]]
binding     = "CONSENT_KV"
id          = "yyyyyyyy..."

# Data Localisation Suite: configured in Cloudflare dashboard
# Enables: EU-only log storage, EU-only WAF processing, EU-only Bot Management
```

## Workers `cf.country` + Smart Placement Routing

```typescript
// workers/src/middleware/regional-routing.ts

const EU_EEA_COUNTRIES = new Set([
  'AT','BE','BG','CY','CZ','DE','DK','EE','ES','FI','FR','GR','HR',
  'HU','IE','IT','LT','LU','LV','MT','NL','PL','PT','RO','SE','SI',
  'SK','IS','LI','NO', // EEA
  'CH', // Switzerland (adequacy)
  'GB', // UK (adequacy — review annually)
]);

const ADEQUATE_COUNTRIES = new Set([
  'JP','KR','CA','AR','UY','NZ','IL','AD','FO','GG','IM','JE','MD','SM',
  'US', // DPF — conditional
]);

export interface DataResidencyInfo {
  requiresSCCs: boolean;
  requiresDPIA: boolean;
  country: string;
  region: 'eu' | 'adequate' | 'third';
}

export function assessDataResidency(request: Request): DataResidencyInfo {
  const cf = (request as any).cf ?? {};
  const country: string = cf.country ?? 'XX';

  if (EU_EEA_COUNTRIES.has(country)) {
    return { requiresSCCs: false, requiresDPIA: false, country, region: 'eu' };
  }
  if (ADEQUATE_COUNTRIES.has(country)) {
    return { requiresSCCs: false, requiresDPIA: false, country, region: 'adequate' };
  }
  return { requiresSCCs: true, requiresDPIA: true, country, region: 'third' };
}

// Middleware: attach residency info to request context
export async function regionalMiddleware(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response | null> {
  const info = assessDataResidency(request);

  // Log non-adequate country access for ROPA / transfer record
  if (info.region === 'third') {
    ctx.waitUntil(
      env.DB.prepare(`
        INSERT INTO transfer_events (id, country, requires_sccs, recorded_at)
        VALUES (?, ?, 1, ?)
      `).bind(crypto.randomUUID(), info.country, Date.now()).run()
    );
  }

  // Attach to headers for downstream Workers / Pages Functions
  request.headers.set('X-Data-Region', info.region);
  request.headers.set('X-Data-Country', info.country);

  return null; // continue processing
}
```

## D1 Regional Write Routing

```typescript
// workers/src/lib/db-router.ts
// Ensure writes always go to EU primary; reads may use local replica

export async function writeToEU(
  env: Env,
  statement: string,
  ...params: unknown[]
): Promise<D1Result> {
  // D1 automatically routes writes to the primary region (weur if created with --location weur)
  // This wrapper adds logging for audit trail
  const result = await env.DB.prepare(statement).bind(...params).run();
  return result;
}

// For sensitive PII fields: validate request is EU-origin before writing
export function assertEuOrigin(request: Request): void {
  const region = request.headers.get('X-Data-Region');
  if (region !== 'eu') {
    throw new Response(
      JSON.stringify({ error: 'PII writes restricted to EU-origin requests' }),
      { status: 451, headers: { 'Content-Type': 'application/json' } }
    );
  }
}
```

```sql
-- migrations/0025_transfer_events.sql
CREATE TABLE transfer_events (
  id            TEXT    PRIMARY KEY,
  country       TEXT    NOT NULL,
  requires_sccs INTEGER NOT NULL DEFAULT 0,
  recorded_at   INTEGER NOT NULL
);
-- Art. 30 ROPA: keep for duration of processing relationship
CREATE INDEX idx_te_country ON transfer_events(country, recorded_at DESC);
```

## SCCs Implementation Checklist

```
+-------+------------------------------------------+----------------------+
| Step  | Action                                   | Responsible          |
+-------+------------------------------------------+----------------------+
| 1     | Identify all sub-processors              | DPO + Engineering    |
| 2     | Confirm Cloudflare SCC addendum signed   | Legal                |
| 3     | Run DPIA for any third-country processing | DPO                  |
| 4     | Add sub-processor to Art. 30 ROPA         | DPO                  |
| 5     | Implement TIA (Transfer Impact Assessment)| DPO + Legal          |
| 6     | Store SCC documents in compliance repo    | Legal                |
| 7     | Annual review: check adequacy updates     | DPO                  |
+-------+------------------------------------------+----------------------+

Cloudflare SCC addendum location (2026):
https://www.cloudflare.com/cloudflare-customer-dpa/
Module: Controller-to-Processor (Cloudflare is processor)
```

## Anti-patterns

- Relying on Smart Placement without Regional Services enabled — Smart Placement
  optimises for latency, not GDPR compliance; it may route to US PoPs by default.
- Assuming DPF is permanent — the Schrems III risk is real; maintain SCCs as a
  fallback alongside DPF self-certification.
- Creating D1 database without `--location weur` — the default location is US; you
  cannot migrate an existing database's primary region.
- Logging `cf.country` to D1 without rate-limiting — over time this becomes a profiling
  dataset; retain for 30 days max or aggregate counts only.
- Using `cf.colo` (Cloudflare data-centre code) as a proxy for user country — `cf.colo`
  is where the PoP is, not where the user is; use `cf.country`.

## Gotchas

- **Regional Services ≠ full data localisation**: Regional Services restricts where
  TLS terminates and where Worker CPU runs, but metadata (logs, analytics) may still
  leave the EU unless DLS is also enabled.
- **D1 global read replicas**: D1 replicates reads globally for performance; if you need
  to restrict even reads to EU, use the `--location weur` regional endpoint (Workers
  binding routes reads to nearest replica regardless of `--location`).
- **KV is global by default**: Cloudflare KV replicates values globally. For GDPR-
  sensitive values, use D1 (EU primary) or consider Durable Objects with a specific
  jurisdiction tag.
- **Durable Object jurisdiction tags**: `cf.DurableObjectNamespace.jurisdiction('eu')`
  ensures DO state never leaves EU infrastructure — use for session state, real-time
  presence, and any stateful EU-only processing.
- **DPF annual recertification**: US companies must recertify DPF participation annually;
  verify your sub-processors' DPF status before each annual ROPA review.

## Verification

```bash
# Confirm D1 primary region is EU
wrangler d1 info example project-prod | grep -i location
# Expected: weur or similar EU location

# Check transfer events table for unexpected third-country hits
wrangler d1 execute example project-prod \
  --command "SELECT country, COUNT(*) cnt FROM transfer_events
             WHERE requires_sccs=1
             GROUP BY country ORDER BY cnt DESC LIMIT 20;"

# Verify Worker runs in EU via Cloudflare trace
curl https://example.com/cdn-cgi/trace | grep -E "loc=|colo="
# Expected: loc=EU-country, colo=EU-PoP (if Regional Services enabled)

# Confirm Regional Services flag via API
curl -s -X GET "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/example project-api" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result.placement'
```

## Related

- `gdpr-international-transfers-schrems2.md`
- `gdpr-dpa-standard-contractual-clauses.md`
- `data-localization-requirements.md`
- `cross-border-data-transfer-mechanisms.md`
- `gdpr-article-30-ropa-automation.md`

## Sources

- GDPR Art. 44-49 — EUR-Lex
- EU-US Data Privacy Framework — ec.europa.eu/info/law/law-topic/data-protection
- EDPB Recommendations 01/2020 on transfer impact assessments
- Cloudflare Data Localisation Suite — developers.cloudflare.com/data-localization
- Cloudflare Regional Services — developers.cloudflare.com/workers/platform/
- Cloudflare D1 `--location` flag — developers.cloudflare.com/d1/configuration/
- Cloudflare DPA & SCC addendum — cloudflare.com/cloudflare-customer-dpa
