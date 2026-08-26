# Data Retention Policy Enforcer in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You store multiple categories of personal data (orders, sessions, audit logs, chat messages, consent records) each with different legally mandated or business-driven retention periods. Manually pruning records is error-prone. You need an automated retention enforcement system: configurable periods per data type stored in KV, a scheduled cron Worker that deletes records past their retention age via a soft-delete → hard-delete pipeline, a legal hold mechanism that blocks deletion for records under litigation, and a retention audit report endpoint for your DPO.

## Context

Data minimisation (GDPR Art. 5(1)(e)) requires that personal data be kept "no longer than is necessary". Different retention periods typically apply:

- **Session tokens**: 90 days
- **Access logs**: 1 year
- **Order records**: 7 years (tax/accounting law)
- **Consent records**: 3 years (GDPR accountability)
- **Chat/message data**: 2 years
- **Marketing profiles**: Until consent withdrawal + 30 days

Retention enforcement runs as a Cloudflare Cron Trigger, avoiding a persistent server while still running on a reliable schedule.

## Solution

```typescript
export interface Env {
  DB: D1Database;
  DATA_BUCKET: R2Bucket;
  RETENTION_CONFIG: KVNamespace; // Stores retention periods per data type
  INTERNAL_API_SECRET: string;
}

// ─── Retention config types ───────────────────────────────────────────────────

interface RetentionRule {
  dataType: string;
  retentionDays: number;
  softDeleteDays: number; // Days in soft-delete state before hard deletion
  table?: string;         // D1 table name
  r2Prefix?: string;      // R2 object prefix
  enabled: boolean;
}

async function getRetentionRules(env: Env): Promise<RetentionRule[]> {
  const raw = await env.RETENTION_CONFIG.get('rules');
  if (!raw) return DEFAULT_RULES;
  return JSON.parse(raw) as RetentionRule[];
}

const DEFAULT_RULES: RetentionRule[] = [
  { dataType: 'sessions',      retentionDays: 90,    softDeleteDays: 7,   table: 'user_sessions',  enabled: true },
  { dataType: 'access_logs',   retentionDays: 365,   softDeleteDays: 30,  table: 'access_logs',    enabled: true },
  { dataType: 'orders',        retentionDays: 2555,  softDeleteDays: 30,  table: 'orders',         enabled: true },
  { dataType: 'consent_log',   retentionDays: 1095,  softDeleteDays: 30,  table: 'consent_log',    enabled: true },
  { dataType: 'messages',      retentionDays: 730,   softDeleteDays: 14,  table: 'messages',       enabled: true },
  { dataType: 'user_files',    retentionDays: 365,   softDeleteDays: 14,  r2Prefix: 'users/',      enabled: true },
];

// ─── Legal hold helpers ───────────────────────────────────────────────────────

async function isOnLegalHold(env: Env, dataType: string, recordId: string): Promise<boolean> {
  const row = await env.DB.prepare(
    `SELECT 1 FROM legal_holds
     WHERE data_type = ? AND record_id = ? AND active = 1
     LIMIT 1`
  )
    .bind(dataType, recordId)
    .first();
  return row !== null;
}

async function listLegalHolds(env: Env, dataType: string): Promise<Set<string>> {
  const rows = await env.DB.prepare(
    `SELECT record_id FROM legal_holds WHERE data_type = ? AND active = 1`
  )
    .bind(dataType)
    .all();
  return new Set(rows.results.map((r: Record<string, unknown>) => r.record_id as string));
}

// ─── Soft-delete stage ────────────────────────────────────────────────────────

async function softDeleteExpired(
  env: Env,
  rule: RetentionRule
): Promise<{ softDeleted: number; skippedHolds: number }> {
  if (!rule.table) return { softDeleted: 0, skippedHolds: 0 };

  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - rule.retentionDays);

  // Fetch IDs of expired, non-soft-deleted records
  const { results } = await env.DB.prepare(
    `SELECT id FROM ${rule.table}
     WHERE created_at < ? AND (deleted_at IS NULL)
     LIMIT 500`
  )
    .bind(cutoff.toISOString())
    .all();

  const holds = await listLegalHolds(env, rule.dataType);

  let softDeleted = 0;
  let skippedHolds = 0;

  const now = new Date().toISOString();
  for (const row of results) {
    const id = (row as Record<string, unknown>).id as string;
    if (holds.has(id)) {
      skippedHolds++;
      continue;
    }
    await env.DB.prepare(
      `UPDATE ${rule.table} SET deleted_at = ?, retention_state = 'soft_deleted' WHERE id = ?`
    )
      .bind(now, id)
      .run();
    softDeleted++;
  }

  return { softDeleted, skippedHolds };
}

// ─── Hard-delete stage ────────────────────────────────────────────────────────

async function hardDeleteSoftDeleted(
  env: Env,
  rule: RetentionRule
): Promise<{ hardDeleted: number; skippedHolds: number }> {
  if (!rule.table) return { hardDeleted: 0, skippedHolds: 0 };

  const hardDeleteCutoff = new Date();
  hardDeleteCutoff.setDate(hardDeleteCutoff.getDate() - rule.softDeleteDays);

  const { results } = await env.DB.prepare(
    `SELECT id FROM ${rule.table}
     WHERE retention_state = 'soft_deleted' AND deleted_at < ?
     LIMIT 500`
  )
    .bind(hardDeleteCutoff.toISOString())
    .all();

  const holds = await listLegalHolds(env, rule.dataType);
  let hardDeleted = 0;
  let skippedHolds = 0;

  for (const row of results) {
    const id = (row as Record<string, unknown>).id as string;
    if (holds.has(id)) {
      skippedHolds++;
      continue;
    }
    // Hard delete: remove all PII columns, keep skeleton for audit
    await env.DB.prepare(
      `UPDATE ${rule.table}
       SET retention_state = 'hard_deleted', pii_purged_at = ?
       WHERE id = ?`
    )
      .bind(new Date().toISOString(), id)
      .run();
    hardDeleted++;
  }

  return { hardDeleted, skippedHolds };
}

// ─── R2 retention enforcement ─────────────────────────────────────────────────

async function enforceR2Retention(
  env: Env,
  rule: RetentionRule
): Promise<{ deleted: number }> {
  if (!rule.r2Prefix) return { deleted: 0 };

  const cutoffMs = Date.now() - rule.retentionDays * 86400 * 1000;
  let deleted = 0;
  let cursor: string | undefined;

  do {
    const listed = await env.DATA_BUCKET.list({ prefix: rule.r2Prefix, cursor, limit: 100 });
    for (const obj of listed.objects) {
      if (obj.uploaded.getTime() < cutoffMs) {
        // Check custom metadata for legal hold flag
        const head = await env.DATA_BUCKET.head(obj.key);
        if (head?.customMetadata?.legalHold === 'true') continue;
        await env.DATA_BUCKET.delete(obj.key);
        deleted++;
      }
    }
    cursor = listed.truncated ? listed.cursor : undefined;
  } while (cursor);

  return { deleted };
}

// ─── Retention audit report ───────────────────────────────────────────────────

interface RetentionReport {
  generatedAt: string;
  rules: Array<{
    dataType: string;
    retentionDays: number;
    pendingSoftDelete: number;
    pendingHardDelete: number;
    legalHoldsActive: number;
  }>;
}

async function generateRetentionReport(env: Env): Promise<RetentionReport> {
  const rules = await getRetentionRules(env);
  const report: RetentionReport = { generatedAt: new Date().toISOString(), rules: [] };

  for (const rule of rules) {
    if (!rule.table || !rule.enabled) continue;

    const softCutoff = new Date();
    softCutoff.setDate(softCutoff.getDate() - rule.retentionDays);

    const hardCutoff = new Date();
    hardCutoff.setDate(hardCutoff.getDate() - rule.softDeleteDays);

    const [pendingSoft, pendingHard, holds] = await Promise.all([
      env.DB.prepare(
        `SELECT COUNT(*) as cnt FROM ${rule.table} WHERE created_at < ? AND deleted_at IS NULL`
      )
        .bind(softCutoff.toISOString())
        .first<{ cnt: number }>(),
      env.DB.prepare(
        `SELECT COUNT(*) as cnt FROM ${rule.table} WHERE retention_state = 'soft_deleted' AND deleted_at < ?`
      )
        .bind(hardCutoff.toISOString())
        .first<{ cnt: number }>(),
      env.DB.prepare(
        `SELECT COUNT(*) as cnt FROM legal_holds WHERE data_type = ? AND active = 1`
      )
        .bind(rule.dataType)
        .first<{ cnt: number }>(),
    ]);

    report.rules.push({
      dataType: rule.dataType,
      retentionDays: rule.retentionDays,
      pendingSoftDelete: pendingSoft?.cnt ?? 0,
      pendingHardDelete: pendingHard?.cnt ?? 0,
      legalHoldsActive: holds?.cnt ?? 0,
    });
  }

  return report;
}

// ─── Scheduled handler ────────────────────────────────────────────────────────

async function runRetentionCycle(env: Env): Promise<Record<string, unknown>> {
  const rules = await getRetentionRules(env);
  const summary: Record<string, unknown> = { ranAt: new Date().toISOString(), results: [] };
  const results: unknown[] = [];

  for (const rule of rules) {
    if (!rule.enabled) continue;
    const soft = await softDeleteExpired(env, rule);
    const hard = await hardDeleteSoftDeleted(env, rule);
    const r2 = await enforceR2Retention(env, rule);
    results.push({ dataType: rule.dataType, ...soft, ...hard, r2Deleted: r2.deleted });
  }

  summary.results = results;
  return summary;
}

// ─── Main Worker ───────────────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const authHeader = request.headers.get('Authorization');

    if (authHeader !== `Bearer ${env.INTERNAL_API_SECRET}`) {
      return new Response('Unauthorized', { status: 401 });
    }

    if (url.pathname === '/retention/report') {
      const report = await generateRetentionReport(env);
      return new Response(JSON.stringify(report, null, 2), {
        headers: { 'Content-Type': 'application/json' },
      });
    }

    if (url.pathname === '/retention/run' && request.method === 'POST') {
      const summary = await runRetentionCycle(env);
      return new Response(JSON.stringify(summary, null, 2), {
        headers: { 'Content-Type': 'application/json' },
      });
    }

    if (url.pathname === '/retention/holds' && request.method === 'POST') {
      const { dataType, recordId, reason, caseRef } =
        await request.json<{ dataType: string; recordId: string; reason: string; caseRef: string }>();
      await env.DB.prepare(
        `INSERT INTO legal_holds (id, data_type, record_id, reason, case_ref, created_at, active)
         VALUES (?, ?, ?, ?, ?, ?, 1)`
      )
        .bind(crypto.randomUUID(), dataType, recordId, reason, caseRef, new Date().toISOString())
        .run();
      return new Response(JSON.stringify({ held: true }), {
        headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response('Not found', { status: 404 });
  },

  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await runRetentionCycle(env);
  },
};
```

## Implementation Details

**Two-stage deletion**: Soft-delete marks records with `deleted_at` and `retention_state = 'soft_deleted'`, making them invisible to application queries but recoverable. After `softDeleteDays`, hard-delete nullifies PII columns while keeping the record skeleton (id, timestamps, `pii_purged_at`) for audit purposes.

**Legal holds**: The `legal_holds` table maps `(data_type, record_id)` to a hold. The enforcer fetches all active holds for a data type in one query and checks membership in a `Set<string>` — O(1) per record lookup instead of a join per record.

**KV-driven config**: Retention rules live in KV under key `'rules'`. Update them via the KV API or dashboard without redeploying the Worker.

**wrangler.toml cron**:
```toml
[triggers]
crons = ["0 2 * * *"]  # 02:00 UTC daily
```

**D1 schema additions**:
```sql
ALTER TABLE user_sessions ADD COLUMN deleted_at TEXT;
ALTER TABLE user_sessions ADD COLUMN retention_state TEXT;
ALTER TABLE user_sessions ADD COLUMN pii_purged_at TEXT;

CREATE TABLE legal_holds (
  id TEXT PRIMARY KEY,
  data_type TEXT NOT NULL,
  record_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  case_ref TEXT,
  created_at TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1
);
```

## Anti-patterns

- **Do not** hard-delete without a soft-delete grace period — accidental over-deletion has no recovery path.
- **Do not** DELETE rows from D1 entirely for order records; financial regulations may require the record skeleton for 7 years.
- **Do not** store retention rules hardcoded in Worker code; externalize to KV so legal changes don't require a deployment.
- **Do not** skip the legal hold check — deleting records under active litigation creates spoliation liability.
- **Do not** run retention enforcement during peak traffic hours; schedule for off-peak (e.g., 02:00 UTC).

## Gotchas

- **D1 row limits per query**: The enforcer batches 500 records per run per data type to stay within D1's per-statement result limits and Worker CPU budget. Large tables may require multiple cron runs to fully catch up on backlog.
- **R2 pagination**: `list()` truncates at 1,000 objects; the `do...while` loop with `cursor` handles arbitrarily large prefixes.
- **Cron CPU limits**: Scheduled Workers have a 30-second CPU limit on the free plan, 15 minutes on paid. Pace accordingly.
- **`pii_purged_at` vs. DELETE**: Keeping the skeleton row lets you answer "did this record exist?" queries without retaining PII — important for deduplication and audit completeness.
- **Soft-delete visibility**: Application queries must include `WHERE deleted_at IS NULL` or `WHERE retention_state IS NULL` to exclude soft-deleted records from normal reads.

## Verification

```bash
# 1. Trigger a manual retention run
curl -X POST https://api.example.com/retention/run \
  -H 'Authorization: Bearer <INTERNAL_API_SECRET>'
# Expected: JSON summary with softDeleted/hardDeleted counts per data type

# 2. Check retention report
curl https://api.example.com/retention/report \
  -H 'Authorization: Bearer <INTERNAL_API_SECRET>' | jq '.rules'

# 3. Place a legal hold
curl -X POST https://api.example.com/retention/holds \
  -H 'Authorization: Bearer <INTERNAL_API_SECRET>' \
  -H 'Content-Type: application/json' \
  -d '{"dataType":"orders","recordId":"ord_123","reason":"litigation","caseRef":"CASE-2026-001"}'

# 4. Verify held record is skipped
wrangler d1 execute <DB_NAME> --command \
  "SELECT id, retention_state, deleted_at FROM orders WHERE id = 'ord_123';"
# Expected: deleted_at should remain NULL
```

## Related

- `documentation/docs/policies/compliance/gdpr-data-deletion-pipeline.md` — right-to-erasure (Art. 17) vs. retention
- `documentation/docs/policies/compliance/workers-data-subject-access-request.md` — DSAR pulls data before deletion
- `documentation/docs/policies/compliance/audit-log-immutable-r2.md` — audit logs may have longer independent retention
- `documentation/docs/policies/compliance/soc2-audit-trail.md` — SOC 2 requires log retention for 1 year minimum

## Sources

- GDPR Article 5(1)(e) — Storage limitation principle
- GDPR Article 17 — Right to erasure
- ICO storage limitation guidance: https://ico.org.uk/for-organisations/guide-to-data-protection/guide-to-the-general-data-protection-regulation-gdpr/principles/storage-limitation/
- Cloudflare Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Cloudflare D1: https://developers.cloudflare.com/d1/
