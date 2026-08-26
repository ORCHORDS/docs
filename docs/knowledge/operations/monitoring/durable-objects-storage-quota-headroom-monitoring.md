# Durable Objects Storage Quota Headroom Monitoring

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Durable Object that accumulates per-session or per-tenant state (chat history, game state, CRDT snapshots) approaches the per-object storage limit. Writes start failing silently or the object enters a degraded state that is hard to distinguish from a logic bug. Unlike D1 table size, there is no built-in Cloudflare notification for a single Durable Object's storage usage. You need proactive real-time monitoring of storage fill ratio and alerting before the limit is hit.

## Context

Each Durable Object has a separate key-value storage namespace capped at a hard limit (currently 10 GB on paid plans). The `DurableObjectStorage` API exposes `list()` to enumerate keys but not a direct byte-count endpoint; you must track usage via `storage.put()` return values or by periodically sampling `storage.list()` with byte estimation. The most practical production approach is to maintain a running usage counter inside each object and emit it to Analytics Engine at every write and during hibernation-wake events. Tail Workers provide the fallback for objects that do not self-report.

---

## 1. Self-Reporting Storage Counter Inside a Durable Object

```typescript
// src/do/session-store.ts
import type { DurableObjectState, AnalyticsEngineDataset } from '@cloudflare/workers-types';

export interface Env {
  AE_DATASET: AnalyticsEngineDataset;
}

const STORAGE_LIMIT_BYTES = 10 * 1024 * 1024 * 1024; // 10 GB
const HEADROOM_WARN_PCT   = 20;

export class SessionStore implements DurableObject {
  private usageBytes = 0;
  private readonly id: string;

  constructor(private state: DurableObjectState, private env: Env) {
    this.id = state.id.toString();
    state.blockConcurrencyWhile(async () => {
      this.usageBytes = (await state.storage.get<number>('__usage_bytes__')) ?? 0;
    });
  }

  async fetch(request: Request): Promise<Response> {
    const { key, value } = await request.json<{ key: string; value: unknown }>();
    const encoded  = JSON.stringify(value);
    const byteSize = new TextEncoder().encode(encoded).byteLength;

    // Check headroom before writing
    if (this.usageBytes + byteSize > STORAGE_LIMIT_BYTES) {
      this.emitUsage('limit-exceeded');
      return new Response('Storage limit reached', { status: 507 });
    }

    await this.state.storage.put(key, value);
    this.usageBytes += byteSize;
    await this.state.storage.put('__usage_bytes__', this.usageBytes);

    const headroomPct = ((STORAGE_LIMIT_BYTES - this.usageBytes) / STORAGE_LIMIT_BYTES) * 100;
    if (headroomPct < HEADROOM_WARN_PCT) {
      this.emitUsage('low-headroom');
    } else {
      this.emitUsage('ok');
    }

    return new Response('ok');
  }

  private emitUsage(status: string): void {
    const headroomPct = ((STORAGE_LIMIT_BYTES - this.usageBytes) / STORAGE_LIMIT_BYTES) * 100;

    this.env.AE_DATASET.writeDataPoint({
      indexes: [this.id.slice(0, 32)],   // truncate to fit index limit
      blobs: [status, 'session-store'],
      doubles: [
        this.usageBytes,
        STORAGE_LIMIT_BYTES,
        headroomPct,
        this.usageBytes / STORAGE_LIMIT_BYTES, // fill ratio
      ],
    });
  }
}
```

---

## 2. Periodic Heartbeat — Alarm-Based Storage Sampling

```typescript
// src/do/session-store.ts (continued — alarm handler)
export class SessionStore implements DurableObject {
  // ... constructor from above ...

  async alarm(): Promise<void> {
    // Re-sample storage to detect drift (e.g. bulk deletes that reduce usage)
    const allKeys = await this.state.storage.list({ allowConcurrency: true });
    let sampledBytes = 0;

    for (const [_key, val] of allKeys) {
      sampledBytes += new TextEncoder().encode(JSON.stringify(val)).byteLength;
    }

    this.usageBytes = sampledBytes;
    await this.state.storage.put('__usage_bytes__', sampledBytes);
    this.emitUsage('heartbeat');

    // Re-schedule next heartbeat (every 6 hours)
    await this.state.storage.setAlarm(Date.now() + 6 * 60 * 60 * 1000);
  }
}
```

---

## 3. Tail Worker — Passive Detection for Unmodified Objects

```typescript
// tail/do-storage-tail.ts
// Catches exceptions from objects that hit the storage limit without self-monitoring.

export interface Env {
  AE_DATASET: AnalyticsEngineDataset;
}

const STORAGE_LIMIT_PATTERNS = [
  /storage limit/i,
  /DO_STORAGE_LIMIT/i,
  /DURABLE_OBJECT_STORAGE_LIMIT/i,
  /507/,
];

export default {
  async tail(events: TailEvent[], env: Env): Promise<void> {
    for (const ev of events) {
      for (const ex of ev.exceptions) {
        const isStorageLimit = STORAGE_LIMIT_PATTERNS.some(p => p.test(ex.message));
        if (!isStorageLimit) continue;

        // Extract DO id from URL if present: /do/:id/...
        const doIdMatch = /\/do\/([a-f0-9]{64})/i.exec(ev.event.request.url);
        const doId = doIdMatch?.[1]?.slice(0, 32) ?? 'unknown';

        env.AE_DATASET.writeDataPoint({
          indexes: [doId],
          blobs: ['limit-exceeded', 'tail-detected', ev.scriptName],
          doubles: [
            10 * 1024 * 1024 * 1024, // at limit
            10 * 1024 * 1024 * 1024,
            0,   // 0% headroom
            1.0, // fill ratio
          ],
        });
      }
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## 4. Analytics Engine SQL Queries

```sql
-- Objects with < 20% headroom in the last 6 hours
SELECT
  index1                     AS do_id,
  LAST(double1) / 1073741824 AS usage_gb,
  LAST(double3)              AS headroom_pct,
  LAST(blob1)                AS status
FROM do_storage_quota
WHERE timestamp > NOW() - INTERVAL '6' HOUR
GROUP BY do_id
HAVING headroom_pct < 20
ORDER BY headroom_pct ASC
LIMIT 50;

-- Storage usage growth rate per object over the last 7 days
SELECT
  index1                                       AS do_id,
  FIRST(double1)                               AS usage_7d_ago,
  LAST(double1)                                AS usage_now,
  (LAST(double1) - FIRST(double1)) / 7.0       AS bytes_per_day,
  LAST(double3)                                AS headroom_pct
FROM do_storage_quota
WHERE timestamp > NOW() - INTERVAL '7' DAY
GROUP BY do_id
HAVING bytes_per_day > 0
ORDER BY headroom_pct ASC
LIMIT 20;

-- Count of 'limit-exceeded' events in the last 24 h
SELECT
  index1                 AS do_id,
  COUNT()                AS limit_hit_count
FROM do_storage_quota
WHERE blob1 = 'limit-exceeded'
  AND timestamp > NOW() - INTERVAL '24' HOUR
GROUP BY do_id
ORDER BY limit_hit_count DESC;
```

---

## 5. Alert Worker

```typescript
// alert-worker/do-storage-alert.ts
// Cron: 0 */6 * * *  (every 6 hours, aligned to heartbeat)

const WARN_HEADROOM_PCT = 20;
const CRIT_HEADROOM_PCT = 5;

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const sql = `
      SELECT index1 AS do_id,
             LAST(double1) / 1073741824 AS usage_gb,
             LAST(double3) AS headroom_pct
      FROM do_storage_quota
      WHERE timestamp > NOW() - INTERVAL '7' HOUR
      GROUP BY do_id
      HAVING headroom_pct < ${WARN_HEADROOM_PCT}
      ORDER BY headroom_pct ASC LIMIT 10
    `;

    const rows = await cfAeQuery<{ do_id: string; usage_gb: number; headroom_pct: number }>(env, sql);
    if (!rows.length) return;

    const lines = rows.map(r => {
      const level = r.headroom_pct < CRIT_HEADROOM_PCT ? 'CRIT' : 'WARN';
      return `[${level}] DO ${r.do_id}: ${r.headroom_pct.toFixed(1)}% headroom (${r.usage_gb.toFixed(2)} GB used)`;
    });

    await sendSlackAlert(env.SLACK_WEBHOOK, {
      text: `Durable Object storage headroom alert:\n${lines.join('\n')}`,
    });
  },
} satisfies ExportedHandler<Env>;
```

---

## Anti-patterns

- **Estimating usage from key count alone** — a Durable Object with 1,000 large JSON blobs can hit the limit faster than one with 1,000,000 small integer keys; always track byte size.
- **Sampling storage with `list()` on every request** — `list()` is O(keys) and blocks concurrency; use the running counter for per-request writes and `list()` only in the alarm heartbeat.
- **Treating the 10 GB limit as effectively infinite** — objects accumulating historical records, logs, or snapshots without a compaction/eviction strategy routinely hit the limit in production.
- **Not handling 507 responses in the caller** — if the Durable Object returns 507, the calling Worker must surface this to the user or trigger a compaction flow rather than retrying indefinitely.

## Gotchas

- The `__usage_bytes__` counter key itself consumes ~16 bytes and must not be excluded from the usage calculation.
- Alarm scheduling requires the object to receive at least one request first; an object created via stub but never `fetch()`-ed will not self-schedule its heartbeat alarm.
- `storage.list()` in the alarm handler blocks I/O for the entire key space; objects with millions of keys should sample a prefix or rely on the running counter only.
- The 10 GB per-object limit applies to key+value bytes combined; Cloudflare counts the key length against the quota.
- Analytics Engine `indexes` field has a 512-byte limit; Durable Object IDs are 64 hex characters — safe to use directly, but slice to 32 if you concatenate other metadata.

## Verification

```bash
# Manually inspect a specific DO's storage key count via REST API
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/durable-objects/namespaces/$DO_NAMESPACE_ID/objects/$DO_ID/storage" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result | length'

# Check AE for headroom data on a specific DO id
curl -s "$CF_AE_SQL_URL" -H "Authorization: Bearer $CF_API_TOKEN" \
  -d "{\"query\":\"SELECT LAST(double1)/1073741824 AS gb, LAST(double3) AS headroom_pct FROM do_storage_quota WHERE index1 = '$DO_ID' AND timestamp > NOW() - INTERVAL '12' HOUR\"}" \
  | jq '.data'
```

## Related

- `durable-objects-storage-growth-forecasting-analytics-engine.md`
- `durable-objects-capacity-planning.md`
- `durable-objects-alarm-heartbeat-monitoring.md`
- `durable-objects-hibernation-wake-monitoring.md`
- `error-budget-calculation.md`

## Sources

- Durable Objects storage limits: https://developers.cloudflare.com/durable-objects/platform/limits/
- DurableObjectStorage API: https://developers.cloudflare.com/durable-objects/api/storage-api/
- Durable Object alarms: https://developers.cloudflare.com/durable-objects/api/alarms/
- Analytics Engine overview: https://developers.cloudflare.com/analytics/analytics-engine/
