# Detecting State Drift in Durable Objects Against a D1 Source of Truth

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

After a network partition or a failed flush, a Durable Object's in-memory state and its transactional SQLite storage can diverge from the authoritative record held in D1. Reads served from the DO appear consistent internally but return stale values compared to what D1 holds, causing silent data correctness bugs that are difficult to detect without an explicit reconciliation pass. This article implements a self-healing `reconcileAlarm()` that detects and repairs drift automatically.

## Context

Durable Objects provide strongly consistent, co-located storage via `this.ctx.storage`, but D1 is the canonical source of truth for records that must survive DO eviction or global replication. When a Worker writes to D1 and the DO separately, a failure between the two writes produces drift. Durable Object Alarms fire reliably even after hibernation and are the idiomatic scheduling primitive inside a DO. Analytics Engine captures drift events as a time series so you can trend drift frequency. PagerDuty's Events API v2 accepts a simple `POST` and de-duplicates on `dedup_key`.

## Durable Object with Reconciliation Alarm

```typescript
// src/MyDurableObject.ts
import { DurableObject } from 'cloudflare:workers';

export interface Env {
  DB: D1Database;
  DRIFT_ANALYTICS: AnalyticsEngineDataset;
  PAGERDUTY_ROUTING_KEY: string;
}

interface CanonicalRecord {
  id: string;
  value: string;
  updated_at: number;
}

export class MyDurableObject extends DurableObject<Env> {
  private consecutiveDriftCount = 0;
  private readonly DRIFT_ALERT_THRESHOLD = 3;
  private readonly RECONCILE_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    // Schedule the first reconcile alarm on construction
    this.ctx.storage.setAlarm(Date.now() + this.RECONCILE_INTERVAL_MS);
  }

  async alarm(): Promise<void> {
    await this.reconcileAlarm();
    // Reschedule for next cycle
    this.ctx.storage.setAlarm(Date.now() + this.RECONCILE_INTERVAL_MS);
  }

  private async reconcileAlarm(): Promise<void> {
    const id = this.ctx.id.toString();
    const doValue = await this.ctx.storage.get<string>('value');
    const doUpdatedAt = await this.ctx.storage.get<number>('updated_at');

    // Fetch canonical record from D1
    const row = await this.env.DB
      .prepare('SELECT id, value, updated_at FROM records WHERE id = ?')
      .bind(id)
      .first<CanonicalRecord>();

    if (!row) return; // record not yet written — skip

    const drifted = doValue !== row.value || doUpdatedAt !== row.updated_at;

    if (drifted) {
      this.consecutiveDriftCount++;
      // Write drift event to Analytics Engine
      this.env.DRIFT_ANALYTICS.writeDataPoint({
        blobs: [id, doValue ?? 'null', row.value, 'value_mismatch'],
        doubles: [this.consecutiveDriftCount, Date.now()],
        indexes: [id],
      });

      // Auto-heal: overwrite DO storage with D1 canonical values
      await this.ctx.storage.put('value', row.value);
      await this.ctx.storage.put('updated_at', row.updated_at);

      // Alert PagerDuty after N consecutive drift detections
      if (this.consecutiveDriftCount >= this.DRIFT_ALERT_THRESHOLD) {
        await this.firePagerDutyAlert(id, this.consecutiveDriftCount);
      }
    } else {
      this.consecutiveDriftCount = 0;
    }
  }

  private async firePagerDutyAlert(doId: string, count: number): Promise<void> {
    await fetch('https://events.pagerduty.com/v2/enqueue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        routing_key: this.env.PAGERDUTY_ROUTING_KEY,
        event_action: 'trigger',
        dedup_key: `do-drift-${doId}`,
        payload: {
          summary: `DO state drift detected ${count} times consecutively for ${doId}`,
          severity: 'critical',
          source: 'cloudflare-durable-objects',
          custom_details: { do_id: doId, consecutive_count: count },
        },
      }),
    });
  }

  // Admin RPC: force-sync DO state from D1 immediately
  async forceSync(): Promise<{ synced: boolean; drifted: boolean }> {
    const id = this.ctx.id.toString();
    const doValue = await this.ctx.storage.get<string>('value');
    const row = await this.env.DB
      .prepare('SELECT value, updated_at FROM records WHERE id = ?')
      .bind(id)
      .first<CanonicalRecord>();
    if (!row) return { synced: false, drifted: false };
    const drifted = doValue !== row.value;
    await this.ctx.storage.put('value', row.value);
    await this.ctx.storage.put('updated_at', row.updated_at);
    this.consecutiveDriftCount = 0;
    return { synced: true, drifted };
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === '/admin/force-sync' && request.method === 'POST') {
      const result = await this.forceSync();
      return Response.json(result);
    }
    const value = await this.ctx.storage.get<string>('value');
    return Response.json({ value });
  }
}
```

## Admin Worker — Calling forceSync via RPC

```typescript
// src/admin-worker.ts
export interface Env {
  MY_DO: DurableObjectNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    // POST /admin/do/:id/force-sync
    const match = url.pathname.match(/^\/admin\/do\/([^\/]+)\/force-sync$/);
    if (match && request.method === 'POST') {
      const stub = env.MY_DO.get(env.MY_DO.idFromName(match[1]));
      const result = await stub.fetch(new Request('https://do/admin/force-sync', { method: 'POST' }));
      return result;
    }
    return new Response('not found', { status: 404 });
  },
};
```

## Analytics Engine Drift Query

```graphql
# Query consecutive drift counts per DO id over last 24 hours
{
  viewer {
    accounts(filter: { accountTag: "$ACCOUNT_ID" }) {
      workersAnalyticsEngineAdaptiveGroups(
        limit: 50
        filter: {
          datasetName: "drift_analytics"
          datetimeHour_geq: "2026-08-23T00:00:00Z"
        }
        orderBy: [sum_double1_DESC]
      ) {
        sum { double1 }   # total drift detections
        dimensions { blob1 }  # DO id
      }
    }
  }
}
```

## Anti-patterns

- **Reconciling on every request** — adds latency to every hot-path read; use alarms for background reconciliation.
- **Alerting on the first drift detection** — transient network hiccups cause single-event false positives; wait for N consecutive detections.
- **Overwriting D1 with DO state** — DO state is the derivative; D1 is the source of truth. Always overwrite DO from D1, never the reverse.
- **Storing the entire D1 row in DO storage** — store only the fields you need; large payloads slow alarm execution and storage writes.

## Gotchas

- `this.ctx.storage.setAlarm()` is idempotent if called with the same timestamp; always advance it by the interval from `Date.now()` at the end of `alarm()` to avoid drift in the alarm schedule itself.
- In-memory properties on the DO class (`consecutiveDriftCount`) reset to their constructor default after hibernation; persist counters to `ctx.storage` if you need them to survive eviction.
- D1 queries inside a DO consume the DO's CPU time budget; keep reconcile queries narrow (single row by primary key).
- PagerDuty's `dedup_key` scopes deduplication to 24 hours; after that window the alert will re-trigger even without a resolve event.

## Verification

```bash
# 1. Manually inject drift: update D1 without touching DO
wrangler d1 execute my-db --command "UPDATE records SET value='drifted' WHERE id='test-id'"

# 2. Wait for alarm cycle (up to 5 min) or force-trigger via admin
curl -X POST https://my-admin-worker.example.com/admin/do/test-id/force-sync

# 3. Confirm drift event in Analytics Engine
curl -X POST https://api.cloudflare.com/client/v4/graphql \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -d '{"query": "{ viewer { accounts(filter:{accountTag:\"$ACCOUNT_ID\"}) { workersAnalyticsEngineAdaptiveGroups(limit:5 filter:{datasetName:\"drift_analytics\"}) { count dimensions { blob1 } } } } }"}'
```

## Related

- `workers-error-boundary-analytics-engine.md`
- `tail-worker-multi-destination-fanout.md`
- `alert-deduplication-workers-kv-pagerduty.md`

## Sources

- Cloudflare Durable Objects Alarms — https://developers.cloudflare.com/durable-objects/api/alarms/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- PagerDuty Events API v2 — https://developer.pagerduty.com/api-reference/368ae3d938c9e-send-an-event-to-pager-duty
