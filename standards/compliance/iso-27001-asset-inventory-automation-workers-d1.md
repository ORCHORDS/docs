# ISO 27001 Asset Inventory Automation with Cloudflare Workers and D1

Date: 2026-08-23 / Author: example.com / Status: production

---

**Symptom / Use-case**

ISO 27001:2022 Annex A 5.9 (Inventory of information and other associated assets) requires organisations to maintain an inventory of assets and identify owners. Manual spreadsheets drift quickly—new Workers get deployed, D1 databases get created, R2 buckets appear—and the register falls out of sync before an internal audit. This article shows how to automate asset discovery, classification, and ownership assignment using Cloudflare Workers (Cron Triggers), D1, and the Cloudflare API so the ISMS register stays current without human effort.

**Context**

Annex A 5.9 pairs with 5.10 (Acceptable use), 5.11 (Return of assets), 5.12 (Classification), and 8.8 (Vulnerability management). A compliant asset register must capture: unique identifier, asset name, asset type, owner, classification label (Public / Internal / Confidential / Restricted), location/environment, processing purpose, and status. D1 serves as the authoritative register; a scheduled Worker pulls from the Cloudflare REST API nightly; a second Worker exposes a read API for auditors; KV caches classification lookups.

---

## D1 Schema for the Asset Register

```sql
-- migrations/0001_asset_register.sql
CREATE TABLE IF NOT EXISTS assets (
  id            TEXT PRIMARY KEY,          -- cf-{resource_type}-{resource_id}
  name          TEXT NOT NULL,
  asset_type    TEXT NOT NULL,             -- worker | d1 | r2 | kv | queue | durable_object
  owner_email   TEXT,
  classification TEXT NOT NULL DEFAULT 'Internal', -- Public|Internal|Confidential|Restricted
  environment   TEXT NOT NULL,             -- production | staging | development
  account_id    TEXT NOT NULL,
  purpose       TEXT,
  status        TEXT NOT NULL DEFAULT 'active',
  first_seen_at TEXT NOT NULL,
  last_seen_at  TEXT NOT NULL,
  metadata      TEXT                       -- JSON blob for type-specific details
);

CREATE INDEX IF NOT EXISTS idx_assets_type        ON assets(asset_type);
CREATE INDEX IF NOT EXISTS idx_assets_owner       ON assets(owner_email);
CREATE INDEX IF NOT EXISTS idx_assets_status      ON assets(status);
CREATE INDEX IF NOT EXISTS idx_assets_last_seen   ON assets(last_seen_at);
```

## Scheduled Discovery Worker

```typescript
// workers/asset-discovery/index.ts
export interface Env {
  ASSET_DB: D1Database;
  CF_API_TOKEN: string;
  CF_ACCOUNT_ID: string;
  OWNER_CACHE: KVNamespace;
}

interface CfResource { id: string; name: string; [key: string]: unknown }

async function fetchCfResources(
  env: Env,
  path: string
): Promise<CfResource[]> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/${path}`,
    { headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` } }
  );
  const json = await res.json() as { result: CfResource[] };
  return json.result ?? [];
}

async function upsertAsset(
  db: D1Database,
  asset: {
    id: string; name: string; asset_type: string;
    account_id: string; metadata: Record<string, unknown>;
  }
): Promise<void> {
  const now = new Date().toISOString();
  await db.prepare(`
    INSERT INTO assets (id, name, asset_type, account_id, first_seen_at, last_seen_at, metadata)
    VALUES (?1, ?2, ?3, ?4, ?5, ?5, ?6)
    ON CONFLICT(id) DO UPDATE SET
      name         = excluded.name,
      last_seen_at = excluded.last_seen_at,
      metadata     = excluded.metadata
  `).bind(
    asset.id, asset.name, asset.asset_type,
    asset.account_id, now, JSON.stringify(asset.metadata)
  ).run();
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const accountId = env.CF_ACCOUNT_ID;

    // Discover Workers
    const workers = await fetchCfResources(env, 'workers/scripts');
    for (const w of workers) {
      await upsertAsset(env.ASSET_DB, {
        id: `cf-worker-${w.id}`, name: w.name as string,
        asset_type: 'worker', account_id: accountId,
        metadata: { modified_on: w.modified_on, usage_model: w.usage_model }
      });
    }

    // Discover D1 databases
    const databases = await fetchCfResources(env, 'd1/database');
    for (const db of databases) {
      await upsertAsset(env.ASSET_DB, {
        id: `cf-d1-${db.uuid}`, name: db.name as string,
        asset_type: 'd1', account_id: accountId,
        metadata: { uuid: db.uuid, version: db.version, num_tables: db.num_tables }
      });
    }

    // Discover R2 buckets
    const buckets = await fetchCfResources(env, 'r2/buckets');
    for (const b of buckets) {
      await upsertAsset(env.ASSET_DB, {
        id: `cf-r2-${b.name}`, name: b.name as string,
        asset_type: 'r2', account_id: accountId,
        metadata: { creation_date: b.creation_date, location: b.location }
      });
    }

    // Mark assets not seen in 48 h as retired
    await env.ASSET_DB.prepare(`
      UPDATE assets SET status = 'retired'
      WHERE last_seen_at < datetime('now', '-48 hours') AND status = 'active'
    `).run();
  }
};
```

## Owner Assignment API

```typescript
// workers/asset-ownership/index.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== 'PATCH') return new Response('Method Not Allowed', { status: 405 });

    const { assetId, ownerEmail, classification, purpose } =
      await req.json() as {
        assetId: string; ownerEmail: string;
        classification: string; purpose: string;
      };

    const validClasses = ['Public', 'Internal', 'Confidential', 'Restricted'];
    if (!validClasses.includes(classification)) {
      return Response.json({ error: 'Invalid classification' }, { status: 400 });
    }

    const result = await env.ASSET_DB.prepare(`
      UPDATE assets
      SET owner_email = ?1, classification = ?2, purpose = ?3
      WHERE id = ?4
    `).bind(ownerEmail, classification, purpose, assetId).run();

    if (result.meta.changes === 0) {
      return Response.json({ error: 'Asset not found' }, { status: 404 });
    }

    return Response.json({ updated: assetId });
  }
} satisfies ExportedHandler<Env>;
```

## Audit Export Worker

```typescript
// workers/asset-export/index.ts — generates ISO 27001 Annex A 5.9 evidence CSV
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { results } = await env.ASSET_DB.prepare(`
      SELECT id, name, asset_type, owner_email, classification,
             environment, purpose, status, first_seen_at, last_seen_at
      FROM assets ORDER BY asset_type, name
    `).all();

    const header = 'Asset ID,Name,Type,Owner,Classification,Environment,Purpose,Status,First Seen,Last Seen\n';
    const rows = (results as Record<string, string>[]).map(r =>
      [r.id, r.name, r.asset_type, r.owner_email ?? '',
       r.classification, r.environment, r.purpose ?? '',
       r.status, r.first_seen_at, r.last_seen_at]
        .map(v => `"${v.replace(/"/g, '""')}"`)
        .join(',')
    ).join('\n');

    return new Response(header + rows, {
      headers: {
        'Content-Type': 'text/csv',
        'Content-Disposition': `attachment; filename="asset-register-${new Date().toISOString().slice(0,10)}.csv"`
      }
    });
  }
} satisfies ExportedHandler<Env>;
```

## Orphan Detection (No Owner After 7 Days)

```typescript
// Part of the scheduled worker — alert on unowned assets
async function alertOrphans(env: Env): Promise<void> {
  const { results } = await env.ASSET_DB.prepare(`
    SELECT id, name, asset_type, first_seen_at
    FROM assets
    WHERE owner_email IS NULL
      AND status = 'active'
      AND first_seen_at < datetime('now', '-7 days')
  `).all();

  if (results.length === 0) return;

  // Post to Slack / PagerDuty / email as required by your ISMS
  await fetch(env.ALERT_WEBHOOK, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: `ISO 27001 A.5.9: ${results.length} assets have no owner after 7 days`,
      assets: results
    })
  });
}
```

**Anti-patterns**

- Storing asset data only in KV — KV has no query capability; D1 SQL is required for owner/type/classification filtering during audit.
- Running discovery on every request — use Cron Triggers (`0 2 * * *`) to avoid rate-limiting the Cloudflare API.
- Treating `last_seen_at` as `updated_at` — an asset can go unchanged for months yet remain active; the retired logic requires the 48-hour window, not an absence of updates.
- Skipping the `purpose` field — ISO 27001 A.5.9 requires the processing purpose, not just technical metadata.

**Gotchas**

- The Cloudflare Workers list API returns a maximum of 1000 scripts per page; add cursor-based pagination for large accounts.
- R2 bucket names are globally unique but account-scoped in the API; prefix IDs with account ID to avoid collisions in multi-account setups.
- D1 `ON CONFLICT DO UPDATE` resets `first_seen_at` if the INSERT branch wins — ensure `first_seen_at` is excluded from the UPDATE clause.
- KV namespace listing (`kv/namespaces`) returns preview namespaces used by Wrangler; filter by `title` prefix to exclude dev namespaces from the production register.

**Verification**

```bash
# Check asset count by type
wrangler d1 execute ASSET_DB --command \
  "SELECT asset_type, COUNT(*) AS n FROM assets GROUP BY asset_type;"

# Find unowned assets
wrangler d1 execute ASSET_DB --command \
  "SELECT id, name, first_seen_at FROM assets WHERE owner_email IS NULL AND status='active';"

# Confirm retired assets are flagged
wrangler d1 execute ASSET_DB --command \
  "SELECT COUNT(*) FROM assets WHERE status='retired';"
```

**Related**

- `iso-27001-continuous-monitoring-automation-workers-d1.md`
- `iso-27001-isms-scope-definition.md`
- `iso-27001-risk-assessment-methodology.md`
- `data-classification-policy.md`
- `iso-27002-2022-new-controls.md`

**Sources**

- ISO/IEC 27001:2022 Annex A, Control 5.9 — Inventory of information and other associated assets
- ISO/IEC 27002:2022 §5.9 — Implementation guidance
- Cloudflare API Documentation — Workers, D1, R2, KV resource listing endpoints
- ENISA Good Practices for Asset Management (2022)
