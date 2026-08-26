# Data Retention and Automated Deletion with Cloudflare Workers

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

The platform stores data in D1, KV, and R2. There is no
automated process for deleting records past their retention
period, creating GDPR Art. 5(1)(e) (storage limitation)
exposure and inflating storage costs.

## Context

Every data class must have a retention period. Data held
beyond its purpose is a liability: it increases breach
impact, violates storage-limitation principles under GDPR,
CCPA, and HIPAA, and can be ordered produced in litigation.
Automation reduces human error and produces evidence of
systematic deletion for auditors.

Retention is distinct from erasure: retention schedules
apply organisation-wide on a rolling basis; GDPR Art. 17
right-to-erasure is a per-subject request that can override
a retention schedule (delete earlier). A legal hold can
suspend deletion for litigation; erasure requests do not
override legal holds.

## 1. Retention Schedule

Define a single authoritative schedule and reference it from
all deletion jobs:

| Data class            | Storage   | Retention  | Authority          |
|-----------------------|-----------|------------|--------------------|
| Server access logs    | D1 / S3   | 90 days    | GDPR Art.5, HIPAA  |
| Application audit logs| D1 / S3   | 1 year     | SOC 2, ISO 27001   |
| Analytics events      | D1        | 2 years    | Business need      |
| User-generated content| D1 / R2   | Until del. | GDPR Art.17        |
| Financial records     | D1        | 7 years    | HMRC / IRS rules   |
| Employee records      | D1        | 7 years    | Employment law     |
| Session tokens        | KV        | 24 hours   | Security policy    |
| Temp upload objects   | R2        | 7 days     | Storage cost       |

Store this table in `config/retention-policy.json` and
import it into every deletion Worker so there is one source
of truth.

## 2. Automated D1 Deletion via Cron Worker

Cloudflare Workers Cron triggers execute on a schedule with
no inbound HTTP request. Use them for retention sweeps.

```toml
# wrangler.toml
name = "retention-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[d1_databases]]
binding = "DB"
database_name = "production"
database_id   = "YOUR_D1_DATABASE_ID"

[triggers]
crons = ["0 2 * * *"]   # 02:00 UTC daily
```

```typescript
// src/index.ts
import { RetentionPolicy } from "./policy";

export interface Env {
  DB: D1Database;
}

export default {
  async scheduled(
    _event: ScheduledEvent,
    env: Env,
    _ctx: ExecutionContext
  ): Promise<void> {
    const jobs: Array<{ table: string; days: number }> = [
      { table: "access_logs",   days: 90  },
      { table: "audit_logs",    days: 365 },
      { table: "analytics",     days: 730 },
    ];

    for (const job of jobs) {
      const result = await env.DB.prepare(
        `DELETE FROM ${job.table}
         WHERE created_at < date('now', '-${job.days} days')`
      ).run();

      // Emit structured deletion audit event
      console.log(JSON.stringify({
        event:    "retention_deletion",
        table:    job.table,
        days:     job.days,
        deleted:  result.meta.changes,
        ts:       new Date().toISOString(),
      }));
    }
  },
};
```

Deletion audit events written to `console.log` are captured
by Logpush and shipped to your SIEM. Retain deletion audit
records for 1 year — they prove the schedule is running.

**Batch deletion for large tables**: D1 has a 1 000-row-per-
statement limit on some query patterns. For large tables
delete in batches:

```typescript
async function deleteBatch(
  db: D1Database, table: string, days: number, batchSize = 500
): Promise<number> {
  let total = 0;
  while (true) {
    const r = await db.prepare(
      `DELETE FROM ${table}
       WHERE id IN (
         SELECT id FROM ${table}
         WHERE created_at < date('now', '-${days} days')
         LIMIT ${batchSize}
       )`
    ).run();
    total += r.meta.changes ?? 0;
    if ((r.meta.changes ?? 0) < batchSize) break;
  }
  return total;
}
```

## 3. KV TTL for Automatic Expiry

Cloudflare KV supports per-key TTL at write time. Set TTL
when creating short-lived records so the platform deletes
them without a cron job:

```typescript
// Session token expires in 86400 seconds (24 h)
await env.SESSION_KV.put(
  `session:${userId}:${tokenId}`,
  JSON.stringify(sessionPayload),
  { expirationTtl: 86400 }
);

// Temporary upload confirmation — 7 days
await env.UPLOAD_KV.put(
  `upload:${uploadId}`,
  JSON.stringify(meta),
  { expirationTtl: 7 * 24 * 3600 }
);
```

KV TTL deletion is not auditable — KV does not emit events
when keys expire. For data classes requiring deletion proof
(HIPAA, GDPR high-risk), use D1 with the cron approach
instead.

## 4. R2 Object Lifecycle Rules

R2 supports lifecycle rules to auto-delete objects by
prefix and age. Configure via the Cloudflare API:

```bash
curl -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/r2/buckets/${BUCKET}/lifecycle" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "rules": [
      {
        "id": "delete-temp-uploads",
        "status": "Enabled",
        "filter": { "prefix": "tmp/" },
        "expiration": { "days": 7 }
      },
      {
        "id": "delete-old-exports",
        "status": "Enabled",
        "filter": { "prefix": "exports/" },
        "expiration": { "days": 90 }
      }
    ]
  }'
```

Like KV TTL, R2 lifecycle deletions are not individually
logged. Use a separate inventory Worker if you need to
record which objects were deleted.

## 5. GDPR Erasure vs. Retention Conflict Resolution

Art. 17 erasure requests must be fulfilled "without undue
delay" (in practice ≤30 days). However, Art. 17(3) lists
exemptions where retention overrides erasure:

| Situation                         | Delete?           |
|-----------------------------------|-------------------|
| Data still needed for contract    | No — inform user  |
| Legal obligation to retain        | No — inform user  |
| Active legal hold / litigation    | No — suspend      |
| Public interest / research        | Possible exemption|
| No remaining lawful basis         | Yes — delete all  |

Implementation pattern for erasure requests:

```typescript
async function handleErasureRequest(
  userId: string, env: Env
): Promise<{ deleted: boolean; reason?: string }> {
  const legalHold = await env.DB.prepare(
    "SELECT * FROM legal_holds WHERE user_id = ? AND active = 1"
  ).bind(userId).first();

  if (legalHold) {
    return { deleted: false, reason: "active_legal_hold" };
  }

  const financialData = await env.DB.prepare(
    "SELECT COUNT(*) as n FROM financial_records WHERE user_id = ?"
  ).bind(userId).first<{ n: number }>();

  // Financial records have a 7-year statutory hold
  if ((financialData?.n ?? 0) > 0) {
    // Pseudonymise rather than delete
    await env.DB.prepare(
      "UPDATE financial_records SET user_id = 'REDACTED-' || id WHERE user_id = ?"
    ).bind(userId).run();
  }

  // Delete all other user data
  for (const table of ["users", "sessions", "analytics", "access_logs"]) {
    await env.DB.prepare(`DELETE FROM ${table} WHERE user_id = ?`)
      .bind(userId).run();
  }

  return { deleted: true };
}
```

Log every erasure outcome (deleted / exempt / partial) to
the audit trail with the user ID, timestamp, and reason.

## Anti-patterns

- Deleting with `DELETE FROM table` (no WHERE clause) —
  will wipe the entire table if the cron fires with an
  incorrect configuration.
- Setting KV TTL for data requiring deletion audit — use
  D1 + cron instead.
- Running retention deletes during business-hours peak —
  schedule during off-peak (e.g. 02:00 UTC).
- Treating legal hold as a permanent exemption — review
  holds quarterly and release them when litigation ends.
- Forgetting to delete data in backups — document that
  backups are rotated on a schedule ≤ the shortest
  retention period of the data they contain.

## Gotchas

- D1 `result.meta.changes` can be `undefined` if the
  query does not trigger a write; guard with `?? 0`.
- Cloudflare Workers Cron does not guarantee exact-second
  precision; expect ± 30 seconds variation on schedule.
- R2 lifecycle rules evaluate once per day; a rule with
  `days: 7` may retain objects for up to 8 days.
- KV `expirationTtl` must be at least 60 seconds; lower
  values are rejected.

## Verification

1. After deploying the cron Worker, trigger it manually:
   `npx wrangler dev --test-scheduled` and check console
   for `retention_deletion` events.
2. Insert a row with `created_at = date('now', '-91 days')`
   into `access_logs` in a staging D1, run the cron, and
   confirm the row is gone.
3. Set a KV key with `expirationTtl: 60`, wait 90 seconds,
   and confirm `GET` returns `null`.
4. Review Logpush output — confirm deletion events appear
   within 2 minutes of the cron run.

## Related

- `/compliance/gdpr-article-17-erasure.md`
- `/compliance/gdpr-data-retention-policy.md`
- `/compliance/data-retention-policy-engineering.md`
- `/compliance/audit-log-mandatory.md`
- `/compliance/document-retention-legal-hold.md`

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/#expiring-keys
- https://developers.cloudflare.com/r2/buckets/object-lifecycles/
- https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32016R0679
