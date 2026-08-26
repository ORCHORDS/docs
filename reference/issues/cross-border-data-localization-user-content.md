# Cross-Border Data Localization Requirements for User Content
- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

example project (example.com) serves users globally and stores user-generated content — text posts, media
files, interaction logs, moderation records — in Cloudflare R2 and D1. Both products are
globally distributed by default: R2 objects are stored in the Cloudflare-selected region based
on the first upload location, and D1 databases are replicated read-globally. This is optimal for
latency but creates compliance exposure:

- **EU/EEA GDPR Chapter V**: personal data may only be transferred to third countries if an
  adequacy decision, Standard Contractual Clauses (SCCs), or another Article 46 mechanism is in
  place. If an EU user's session data (even pseudonymous) lands in a non-adequate third country
  (e.g., a US R2 region), GDPR Chapter V applies.
- **Russia Federal Law No. 242-FZ**: Russian-origin personal data of Russian citizens must be
  initially processed and stored on servers physically located in Russia. Cloudflare's standard
  R2 does not offer a Russia-local region; example project cannot legally serve Russian personal data
  if it is stored outside Russia.
- **China PIPL Article 38–40**: Cross-border transfer of Chinese personal data requires either
  a PIPL security assessment by the CAC, a standard contract filing, or a certification — or the
  platform must localize. example project cannot file PIPL contracts and must either block CN users or
  treat their data as subject to localization.
- **Brazil LGPD Article 33**: International transfer requires one of several legal bases; ANPD's
  adequacy list is narrower than GDPR's.

The operator risk: an automatic content-moderation hold or GDPR data-export request from an EU
user whose session data was stored in a US R2 bucket is a potential €20M or 4% global turnover
fine under GDPR Art. 83(5).

---

## Context

example project's architecture:

| Layer             | Technology                | Default region        |
|-------------------|---------------------------|-----------------------|
| Compute           | Cloudflare Workers        | Globally distributed  |
| Media storage     | Cloudflare R2             | Operator-selected hint|
| Structured data   | Cloudflare D1             | Primary + read replicas|
| Session cache     | Cloudflare Workers KV     | Globally replicated   |

Cloudflare R2 supports **jurisdiction constraints** (EU, US-East, APAC-East) that pin objects to
a geographic boundary. Cloudflare D1 (as of 2026) supports **location hints** but not hard
jurisdiction pinning for D1 databases; primary write location can be set, but read replicas may
propagate globally. example project must architect around these limitations.

Session tokens on example project carry no PII by design; however, combination of `cf.country` + subnet
+ behavioral signals may constitute pseudonymous personal data under GDPR's broad definition.
This means data minimisation and jurisdiction routing are obligations, not merely best practices.

---

## Section 1 — Jurisdiction Routing Architecture

The recommended pattern for example project is **geographic shard routing** at the Worker layer:
the origin Worker detects `cf.country` and routes content writes to a jurisdiction-specific
R2 bucket and D1 database. Read requests can be served from the globally-nearest replica, but
writes for EU users must land in an EU-jurisdiction R2 bucket.

```
User (EU) → Cloudflare Edge (Amsterdam) → Worker → EU R2 bucket (EU jurisdiction)
                                                  → EU D1 primary (location_hint=weur)
User (US) → Cloudflare Edge (New York)  → Worker → US R2 bucket (US jurisdiction)
                                                  → US D1 primary (location_hint=enam)
User (CN) → Blocked at geo-enforcement layer (vpn-proxy-detection-geo-restrictions.md)
```

Cloudflare Workers Bindings in `wrangler.toml`:

```toml
[[r2_buckets]]
binding = "MEDIA_EU"
bucket_name = "example project-media-eu"
jurisdiction = "eu"

[[r2_buckets]]
binding = "MEDIA_US"
bucket_name = "example project-media-us"
# No jurisdiction constraint — US default

[[d1_databases]]
binding = "DB_EU"
database_name = "example project-eu"
database_id = "<eu-db-uuid>"
# D1 location_hint set at database creation: wrangler d1 create example project-eu --location weur

[[d1_databases]]
binding = "DB_US"
database_name = "example project-us"
database_id = "<us-db-uuid>"
# D1 location_hint: wrangler d1 create example project-us --location enam
```

---

## Section 2 — D1 Localization Audit Schema

The jurisdiction routing decision and any cross-border data flow must be logged for GDPR
Article 30 Records of Processing Activities (RoPA) compliance.

```sql
-- data_jurisdiction_log: records where each content object was stored
CREATE TABLE IF NOT EXISTS data_jurisdiction_log (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  content_id      TEXT    NOT NULL,  -- post_id or r2_key
  content_type    TEXT    NOT NULL,  -- post | media | moderation_record | session_log
  user_cf_country TEXT    NOT NULL,  -- inferred user jurisdiction at write time
  storage_jurisdiction TEXT NOT NULL, -- eu | us | apac | global
  r2_bucket       TEXT,
  d1_database     TEXT,
  legal_basis     TEXT    NOT NULL,  -- adequacy | scc | legitimate_interest | blocked
  created_at      INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS djl_content_id  ON data_jurisdiction_log (content_id);
CREATE INDEX IF NOT EXISTS djl_country     ON data_jurisdiction_log (user_cf_country, created_at);

-- ropa_processing_activities: GDPR Art. 30 record (static reference table, managed by ops)
CREATE TABLE IF NOT EXISTS ropa_processing_activities (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  activity_name   TEXT    NOT NULL UNIQUE,
  purpose         TEXT    NOT NULL,
  legal_basis     TEXT    NOT NULL,  -- consent | contract | legitimate_interest | legal_obligation
  data_categories TEXT    NOT NULL,  -- JSON array
  recipients      TEXT    NOT NULL,  -- JSON array of data recipients / processors
  third_country   TEXT,              -- NULL if EU-only transfer
  transfer_mechanism TEXT,          -- adequacy | scc | bcr | exemption
  retention_days  INTEGER,
  updated_at      INTEGER NOT NULL DEFAULT (unixepoch())
);
```

---

## Section 3 — Worker: Jurisdiction Router

```typescript
// jurisdiction-router.ts

interface Env {
  // EU-jurisdiction bindings
  MEDIA_EU: R2Bucket;
  DB_EU: D1Database;
  // US-jurisdiction bindings
  MEDIA_US: R2Bucket;
  DB_US: D1Database;
  // Audit log (always written to US primary for ops access; only pseudonymous data here)
  DB_AUDIT: D1Database;
}

type Jurisdiction = 'eu' | 'us' | 'apac' | 'blocked';

// GDPR adequacy decisions current as of 2026-08
const EU_ADEQUATE_COUNTRIES = new Set([
  'AD', 'AR', 'CA', 'FO', 'GB', 'GG', 'IL', 'IM', 'JP', 'JE', 'NZ',
  'CH', 'UY', 'US', // US: adequacy decision (Data Privacy Framework, Jul 2023)
  // EEA members
  'AT','BE','BG','HR','CY','CZ','DK','EE','FI','FR','DE','GR','HU',
  'IS','IE','IT','LV','LI','LT','LU','MT','NL','NO','PL','PT','RO',
  'SK','SI','ES','SE',
]);

// Countries requiring data localization (platform must block or localize)
const LOCALIZATION_REQUIRED = new Set(['RU', 'CN', 'BY', 'KZ']);

export function resolveJurisdiction(cfCountry: string): {
  jurisdiction: Jurisdiction;
  legalBasis: string;
} {
  if (LOCALIZATION_REQUIRED.has(cfCountry)) {
    return { jurisdiction: 'blocked', legalBasis: 'blocked' };
  }
  const euCountries = new Set([
    'AT','BE','BG','HR','CY','CZ','DK','EE','FI','FR','DE','GR','HU',
    'IE','IT','LV','LT','LU','MT','NL','PL','PT','RO','SK','SI','ES',
    'SE','IS','LI','NO', // EEA
    'AD','FO','GG','IM','JE','GB','CH', // adequacy-equivalent for routing
  ]);
  if (euCountries.has(cfCountry)) {
    return { jurisdiction: 'eu', legalBasis: 'adequacy' };
  }
  if (EU_ADEQUATE_COUNTRIES.has(cfCountry)) {
    return { jurisdiction: 'us', legalBasis: 'adequacy' };
  }
  // No adequacy decision: use SCC — only for non-personal / pseudonymous data
  // For example project's anonymous sessions, pseudonymous data may transfer under legitimate interest
  // with appropriate SCCs in place with Cloudflare (DPA on file)
  return { jurisdiction: 'us', legalBasis: 'scc' };
}

export function getBindings(jurisdiction: Jurisdiction, env: Env): {
  media: R2Bucket;
  db: D1Database;
} {
  if (jurisdiction === 'eu') {
    return { media: env.MEDIA_EU, db: env.DB_EU };
  }
  return { media: env.MEDIA_US, db: env.DB_US };
}

export async function writeWithJurisdiction(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
  contentId: string,
  contentType: string,
  writeCallback: (media: R2Bucket, db: D1Database) => Promise<void>
): Promise<{ jurisdiction: Jurisdiction; legalBasis: string }> {
  const cf = request.cf as Record<string, unknown>;
  const cfCountry = (cf.country as string) ?? 'XX';

  const { jurisdiction, legalBasis } = resolveJurisdiction(cfCountry);

  if (jurisdiction === 'blocked') {
    throw new Error(`Data localization required for country ${cfCountry}; serving blocked`);
  }

  const { media, db } = getBindings(jurisdiction, env);
  await writeCallback(media, db);

  // Audit log (fire-and-forget, pseudonymous only)
  ctx.waitUntil(
    env.DB_AUDIT.prepare(`
      INSERT INTO data_jurisdiction_log
        (content_id, content_type, user_cf_country, storage_jurisdiction, legal_basis)
      VALUES (?, ?, ?, ?, ?)
    `).bind(contentId, contentType, cfCountry, jurisdiction, legalBasis).run()
  );

  return { jurisdiction, legalBasis };
}
```

---

## Section 4 — GDPR Chapter V Transfer Impact Assessment (TIA) Checklist

For each data flow between example project and Cloudflare (as data processor), the operator must
maintain a Transfer Impact Assessment per EDPB guidelines. This D1 table serves as the
machine-readable record:

```sql
INSERT INTO ropa_processing_activities
  (activity_name, purpose, legal_basis, data_categories, recipients, third_country,
   transfer_mechanism, retention_days)
VALUES
  ('anonymous_session_logs',
   'Platform integrity and abuse prevention',
   'legitimate_interest',
   '["pseudonymous_session_token","ip_subnet","cf_asn","interaction_type"]',
   '["Cloudflare Inc. (data processor, DPA signed)"]',
   'US',
   'adequacy',  -- EU-US Data Privacy Framework adequacy decision (Jul 2023)
   30),
  ('eu_user_media_uploads',
   'User-generated content hosting',
   'contract',
   '["media_file","upload_timestamp","session_token"]',
   '["Cloudflare Inc. (data processor, DPA signed)"]',
   NULL,  -- stored in EU jurisdiction R2 bucket; no third-country transfer
   NULL,
   90),
  ('moderation_records',
   'Content moderation and legal compliance',
   'legal_obligation',
   '["post_id","violation_code","session_token","evidence_hash"]',
   '["Cloudflare Inc. (data processor)","NCMEC (CSAM reports only)"]',
   'US',
   'adequacy',
   365);
```

---

## Anti-patterns

- **Using a single global R2 bucket for all user data**: R2's jurisdiction constraint must be set
  at bucket creation time; it cannot be changed retroactively. A global bucket cannot be
  retroactively made EU-jurisdiction. Plan the bucket topology before launch.
- **Assuming `cf.country` determines data subject nationality for GDPR purposes**: GDPR applies to
  the processing of data of *EU residents*, not EU citizens. A French user on holiday in Thailand
  is still an EU data subject; their session data processed in Thailand is a Chapter V transfer.
  When in doubt, apply EU protections to any session where `cf.isEUCountry` was true at any
  point in the session lifetime.
- **Relying on D1 location hint as a binding jurisdiction constraint**: D1 location hints guide
  primary placement but Cloudflare may replicate reads globally. D1 is not equivalent to R2's
  hard `jurisdiction` constraint. For strict EU localization, consider Cloudflare Hyperdrive
  pointing to a PostgreSQL instance in an EU data center you control.
- **Storing the full `cf.country` in audit logs as the sole TIA record**: The DPA audit examiner
  will ask for the legal basis of each transfer individually. The `data_jurisdiction_log` table
  above captures `legal_basis` per row; ensure this is populated accurately.
- **Treating the EU-US Data Privacy Framework (DPF) as permanent**: The DPF has been challenged
  twice (Schrems I and II) and may be invalidated again. Maintain SCC fallback documentation
  with Cloudflare such that a DPF invalidation does not trigger an immediate GDPR violation.

---

## Gotchas

- R2 `jurisdiction = "eu"` restricts object storage to European Economic Area data centers but
  **does not restrict who can access the bucket via the S3-compatible API**. Access control
  (preventing US-located Cloudflare staff from reading EU objects under US legal process) requires
  a separate Cloudflare Data Localization Suite (DLS) engagement.
- Cloudflare D1 is not listed on Cloudflare's Data Processing Addendum (DPA) as of early 2025 in
  all enterprise tiers. Verify with Cloudflare account management that D1 is covered before
  treating D1 as a GDPR-compliant processor arrangement.
- `wrangler d1 create --location weur` sets the location hint but does not guarantee the database
  is exclusively in western Europe — it sets the *primary* write location. Query the D1 API or
  Cloudflare dashboard to confirm the actual primary region after creation.
- Cloudflare Workers KV is globally replicated with no jurisdiction constraints. Do not store any
  data that constitutes personal data in KV; use it only for ephemeral session validity flags
  that do not identify natural persons.
- Cross-shard queries (e.g., moderation audit spanning both `DB_EU` and `DB_US`) require two
  separate D1 queries and a merge in the Worker. D1 does not support cross-database JOINs.

---

## Verification

```bash
# 1. Verify EU R2 bucket jurisdiction constraint
wrangler r2 bucket info example project-media-eu
# Expected: jurisdiction: eu

# 2. Verify that EU user upload lands in EU bucket
curl -X POST https://example.com/api/upload \
  -H "CF-IPCountry: DE" \
  -H "X-Session-Token: test123" \
  -H "Content-Type: image/jpeg" \
  --data-binary "@test.jpg"
# Check DB_AUDIT: SELECT storage_jurisdiction FROM data_jurisdiction_log WHERE user_cf_country = 'DE';

# 3. Verify CN user is blocked
curl -X POST https://example.com/api/upload \
  -H "CF-IPCountry: CN" \
  -H "X-Session-Token: test456" \
  --data-binary "@test.jpg"
# Expected: 403 (localization_required)

# 4. Verify RoPA entries are current
wrangler d1 execute example project-prod-us --command \
  "SELECT activity_name, legal_basis, transfer_mechanism FROM ropa_processing_activities;"

# 5. Audit jurisdiction distribution for the last 30 days
wrangler d1 execute example project-prod-us --command \
  "SELECT storage_jurisdiction, legal_basis, COUNT(*) as records
   FROM data_jurisdiction_log
   WHERE created_at > unixepoch() - 2592000
   GROUP BY storage_jurisdiction, legal_basis;"
```

---

## Related

- `vpn-proxy-detection-geo-restrictions.md`
- `gdpr-data-export-worker-r2-signed-url.md`
- `user-privacy-law-enforcement-requests.md`
- `digital-services-act-platform-compliance.md`
- `data-act-portability.md`
- `age-verification-cloudflare-workers-kyc.md`
- `cryptocurrency-regulatory-risk-platform.md`
- `r2-etag-conditional-request.md`

---

## Sources

- GDPR Chapter V (Articles 44–49) — international data transfers — https://gdpr-info.eu/chapter-5/
- EU-US Data Privacy Framework (EC adequacy decision, Jul 2023) — https://commission.europa.eu/document/fa09cbad-dd7d-4684-ae60-be03fcb0fddf_en
- Cloudflare R2 jurisdiction constraints — https://developers.cloudflare.com/r2/reference/data-location/
- Cloudflare Data Localization Suite — https://developers.cloudflare.com/data-localization/
- Russia Federal Law No. 242-FZ (data localization) — https://pd.rkn.gov.ru/
- China PIPL Articles 38–40 (cross-border transfer) — https://www.moj.gov.cn/pub/sfbgw/news/202108/t20210820_432986.html
- EDPB Transfer Impact Assessment guidelines — https://edpb.europa.eu/our-work-tools/documents/public-consultations/2021/recommendations-012020-measures-supplement_en
- Brazil LGPD Article 33 (international transfer) — https://www.lgpdbrasil.com.br/
- Cloudflare D1 — location hints — https://developers.cloudflare.com/d1/configuration/data-location/
