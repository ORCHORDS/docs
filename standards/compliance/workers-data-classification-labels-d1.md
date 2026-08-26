# Data Classification Labeling System with Cloudflare Workers + D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Organisations handling mixed-sensitivity data — customer PII, internal memos, public marketing copy — need a programmatic way to label every piece of data with a classification level and enforce access control based on that label. Without this, a junior engineer can accidentally expose a "Restricted" record through a public API because the code had no concept of data sensitivity.

This article builds a classification labeling system inside Cloudflare Workers + D1 that: assigns labels at ingest, propagates labels to derived data, enforces read/write access by classification, and logs every access decision.

## Context

Applies when:
- Your organisation follows an information classification policy (ISO 27001 Annex A.8.2, NIST SP 800-60)
- You process personal data under GDPR/CCPA and must track which records are "Restricted" (containing special-category data)
- You need to generate data inventories for privacy audits
- Multiple teams share a D1 database and you need row-level classification enforcement at the API layer

## Solution

### Classification levels (lowest to highest sensitivity)

| Level | Value | Examples |
|---|---|---|
| Public | 0 | Marketing pages, press releases |
| Internal | 1 | Internal docs, non-sensitive employee data |
| Confidential | 2 | Customer PII, financial records |
| Restricted | 3 | Health data, payment card data, credentials |

### D1 Schema

```sql
CREATE TABLE IF NOT EXISTS classification_label (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  resource_type   TEXT    NOT NULL,   -- e.g. "Document", "Record", "Field"
  resource_id     TEXT    NOT NULL,
  level           INTEGER NOT NULL CHECK(level IN (0,1,2,3)),
  level_name      TEXT    NOT NULL,   -- PUBLIC|INTERNAL|CONFIDENTIAL|RESTRICTED
  rationale       TEXT,               -- why this classification was assigned
  auto_detected   INTEGER NOT NULL DEFAULT 0,  -- 1 if set by scanner
  assigned_by     TEXT    NOT NULL,
  inherited_from  TEXT,               -- parent resource_id if inherited
  created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX idx_label_resource ON classification_label(resource_type, resource_id);
CREATE INDEX idx_label_level ON classification_label(level);

CREATE TABLE IF NOT EXISTS classification_audit (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  resource_type TEXT NOT NULL,
  resource_id   TEXT NOT NULL,
  action        TEXT NOT NULL,  -- READ|WRITE|LABEL_CHANGE|ACCESS_DENIED
  actor_id      TEXT NOT NULL,
  actor_level   INTEGER,        -- actor's clearance level
  resource_level INTEGER,
  outcome       TEXT NOT NULL,  -- ALLOWED|DENIED
  reason        TEXT,
  ts            TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_caud_resource ON classification_audit(resource_type, resource_id);
CREATE INDEX idx_caud_actor    ON classification_audit(actor_id);
CREATE INDEX idx_caud_outcome  ON classification_audit(outcome);
```

### Worker: data-classification.ts

```typescript
import type { D1Database } from '@cloudflare/workers-types';

export interface Env {
  DB: D1Database;
}

export type ClassificationLevel = 0 | 1 | 2 | 3;
export const LEVEL_NAMES: Record<ClassificationLevel, string> = {
  0: 'PUBLIC',
  1: 'INTERNAL',
  2: 'CONFIDENTIAL',
  3: 'RESTRICTED',
};

interface ActorContext {
  actorId: string;
  clearanceLevel: ClassificationLevel; // from JWT claim or directory lookup
}

// ----- Automatic content scanner -----

const RESTRICTED_PATTERNS: RegExp[] = [
  /\b\d{3}-\d{2}-\d{4}\b/,                          // SSN
  /\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14})\b/, // Visa/Mastercard PAN
  /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i,     // Email (treated as PII)
];

const CONFIDENTIAL_PATTERNS: RegExp[] = [
  /\b(?:salary|compensation|revenue|profit)\b/i,
  /\bcustomer(?:\s+id|_id|Id)\b/i,
];

export function scanContent(text: string): ClassificationLevel {
  if (RESTRICTED_PATTERNS.some((re) => re.test(text))) return 3;
  if (CONFIDENTIAL_PATTERNS.some((re) => re.test(text))) return 2;
  // Default to Internal for any user-generated content
  return 1;
}

// ----- Label management -----

export async function setLabel(
  db: D1Database,
  resourceType: string,
  resourceId: string,
  level: ClassificationLevel,
  assignedBy: string,
  options: { rationale?: string; autoDetected?: boolean; inheritedFrom?: string } = {}
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO classification_label
         (resource_type, resource_id, level, level_name, rationale,
          auto_detected, assigned_by, inherited_from)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(resource_type, resource_id) DO UPDATE SET
         level = excluded.level,
         level_name = excluded.level_name,
         rationale = excluded.rationale,
         auto_detected = excluded.auto_detected,
         assigned_by = excluded.assigned_by,
         inherited_from = excluded.inherited_from,
         updated_at = datetime('now')`
    )
    .bind(
      resourceType,
      resourceId,
      level,
      LEVEL_NAMES[level],
      options.rationale ?? null,
      options.autoDetected ? 1 : 0,
      assignedBy,
      options.inheritedFrom ?? null
    )
    .run();
}

export async function getLabel(
  db: D1Database,
  resourceType: string,
  resourceId: string
): Promise<{ level: ClassificationLevel; levelName: string } | null> {
  const row = await db
    .prepare(
      'SELECT level, level_name FROM classification_label WHERE resource_type = ? AND resource_id = ?'
    )
    .bind(resourceType, resourceId)
    .first<{ level: number; level_name: string }>();

  if (!row) return null;
  return { level: row.level as ClassificationLevel, levelName: row.level_name };
}

// ----- Access control enforcement -----

export async function checkAccess(
  db: D1Database,
  actor: ActorContext,
  resourceType: string,
  resourceId: string,
  action: 'READ' | 'WRITE'
): Promise<{ allowed: boolean; reason: string }> {
  const label = await getLabel(db, resourceType, resourceId);

  // Unlabelled resources default to INTERNAL (level 1)
  const resourceLevel: ClassificationLevel = (label?.level ?? 1) as ClassificationLevel;
  const allowed = actor.clearanceLevel >= resourceLevel;
  const reason = allowed
    ? `Actor clearance ${actor.clearanceLevel} >= resource level ${resourceLevel}`
    : `Actor clearance ${actor.clearanceLevel} < resource level ${resourceLevel} (${LEVEL_NAMES[resourceLevel]})`;

  // Always log the access decision
  await db
    .prepare(
      `INSERT INTO classification_audit
         (resource_type, resource_id, action, actor_id, actor_level,
          resource_level, outcome, reason)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .bind(
      resourceType,
      resourceId,
      allowed ? action : 'ACCESS_DENIED',
      actor.actorId,
      actor.clearanceLevel,
      resourceLevel,
      allowed ? 'ALLOWED' : 'DENIED',
      reason
    )
    .run();

  return { allowed, reason };
}

// ----- Label inheritance for child resources -----

/**
 * Propagate a parent's classification to all children.
 * E.g., classifying a Folder also classifies all Documents inside it.
 */
export async function propagateLabel(
  db: D1Database,
  parentType: string,
  parentId: string,
  childType: string,
  childIds: string[],
  assignedBy: string
): Promise<void> {
  const parentLabel = await getLabel(db, parentType, parentId);
  if (!parentLabel) return;

  for (const childId of childIds) {
    const existing = await getLabel(db, childType, childId);
    // Only upgrade (never downgrade) via inheritance
    if (!existing || existing.level < parentLabel.level) {
      await setLabel(db, childType, childId, parentLabel.level, assignedBy, {
        rationale: `Inherited from ${parentType}/${parentId}`,
        inheritedFrom: parentId,
      });
    }
  }
}

// ----- HTTP handler -----

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // POST /classify/scan — auto-scan content and return suggested level
    if (request.method === 'POST' && url.pathname === '/classify/scan') {
      const { content } = await request.json<{ content: string }>();
      const level = scanContent(content);
      return Response.json({ level, levelName: LEVEL_NAMES[level] });
    }

    // PUT /classify/:type/:id — assign a label
    const labelMatch = url.pathname.match(/^\/classify\/([^\/]+)\/([^\/]+)$/);
    if (request.method === 'PUT' && labelMatch) {
      const [, resourceType, resourceId] = labelMatch;
      const body = await request.json<{
        level: ClassificationLevel;
        actorId: string;
        rationale?: string;
      }>();
      await setLabel(env.DB, resourceType, resourceId, body.level, body.actorId, {
        rationale: body.rationale,
      });
      return Response.json({ ok: true });
    }

    // GET /classify/:type/:id — get a label
    if (request.method === 'GET' && labelMatch) {
      const [, resourceType, resourceId] = labelMatch;
      const label = await getLabel(env.DB, resourceType, resourceId);
      if (!label) return new Response('Not found', { status: 404 });
      return Response.json(label);
    }

    // POST /access-check — enforce access
    if (request.method === 'POST' && url.pathname === '/access-check') {
      const body = await request.json<{
        actorId: string;
        clearanceLevel: ClassificationLevel;
        resourceType: string;
        resourceId: string;
        action: 'READ' | 'WRITE';
      }>();
      const result = await checkAccess(
        env.DB,
        { actorId: body.actorId, clearanceLevel: body.clearanceLevel },
        body.resourceType,
        body.resourceId,
        body.action
      );
      return Response.json(result, { status: result.allowed ? 200 : 403 });
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

## Implementation Details

### Integrating automatic scanning at ingest

```typescript
// Middleware wrapper for any data ingestion endpoint
export async function ingestWithClassification(
  db: D1Database,
  resourceType: string,
  resourceId: string,
  content: string,
  actorId: string
): Promise<ClassificationLevel> {
  const autoLevel = scanContent(content);
  await setLabel(db, resourceType, resourceId, autoLevel, 'system:scanner', {
    autoDetected: true,
    rationale: `Auto-classified by content scanner`,
  });
  return autoLevel;
}
```

### Bulk classification inventory report

```typescript
export async function getInventoryByLevel(
  db: D1Database
): Promise<Record<string, number>> {
  const rows = await db
    .prepare(
      `SELECT level_name, COUNT(*) as cnt
       FROM classification_label
       GROUP BY level_name`
    )
    .all<{ level_name: string; cnt: number }>();

  return Object.fromEntries(rows.results.map((r) => [r.level_name, r.cnt]));
}
```

## Anti-patterns

- **Never default unknown resources to PUBLIC** — always default to INTERNAL (level 1) or require explicit labeling before serving the resource.
- **Do not conflate authentication with authorisation** — a valid JWT proves identity but not clearance level. Clearance must be looked up from a separate, access-controlled store.
- **Do not allow self-classification** — users should not be able to downgrade the classification of their own resources. Require a minimum clearance level of 2 to change labels.
- **Avoid regex-only scanners for production** — the patterns above are illustrative. Supplement with a dedicated DLP (Data Loss Prevention) service for high-volume production traffic.

## Gotchas

- **`ON CONFLICT` upsert requires the UNIQUE index** — without `idx_label_resource`, the upsert silently inserts a duplicate row instead of updating.
- **Inherited labels must be re-propagated when the parent changes** — build a hook into `setLabel` to fan-out propagation to known children.
- **Level integers vs. names** — store both in D1 to avoid joins in query results. Keep them in sync on every write.
- **Audit log can grow large** — partition `classification_audit` by month using a `yyyymm` prefix in a `period` column, or archive rows older than 90 days to R2.

## Verification

```bash
# Auto-scan content
curl -X POST https://classify.example.workers.dev/classify/scan \
  -H 'Content-Type: application/json' \
  -d '{"content": "Customer email: alice@example.com, SSN: 123-45-6789"}'
# Expected: {"level":3,"levelName":"RESTRICTED"}

# Assign label manually
curl -X PUT https://classify.example.workers.dev/classify/Document/doc_001 \
  -H 'Content-Type: application/json' \
  -d '{"level":2,"actorId":"admin","rationale":"Contains customer PII"}'

# Check access — actor with clearance 1 (INTERNAL) trying to read CONFIDENTIAL resource
curl -X POST https://classify.example.workers.dev/access-check \
  -H 'Content-Type: application/json' \
  -d '{"actorId":"bob","clearanceLevel":1,"resourceType":"Document","resourceId":"doc_001","action":"READ"}'
# Expected: {"allowed":false, ...} with HTTP 403
```

## Related

- `workers-sox-financial-audit-trail-d1.md` — use classification levels to tag financial audit entries
- `workers-privacy-impact-assessment-d1.md` — feed classification inventory into DPIA data flow maps
- `workers-cookie-consent-management-kv.md` — ensure consent data is classified RESTRICTED

## Sources

- https://developers.cloudflare.com/d1/
- https://csrc.nist.gov/publications/detail/sp/800-60/vol-1/final
- https://www.iso.org/standard/54534.html (ISO 27001 Annex A.8.2)
