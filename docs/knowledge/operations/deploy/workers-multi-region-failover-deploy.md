# Multi-Region Failover Deployment Strategy for Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare account-level incident (rare but real) takes your Workers offline for an entire region or globally. You need a secondary Cloudflare account in a separate blast radius, with automated DNS failover, KV data synchronisation, and D1 replication-lag handling — all with a measured RTO and RPO.

## Context

- Cloudflare Workers run at the edge globally, but a single account is subject to account-level incidents. A second account provides true blast-radius isolation.
- Cloudflare Load Balancer health checks can automatically flip DNS from the primary Worker origin to the secondary origin within 60 seconds.
- KV data (configuration, feature flags, cached responses) must be mirrored to the secondary account because KV namespaces are account-scoped.
- D1 has no built-in cross-account replication; the secondary account runs a read replica via CDC (change-data-capture) written to a Queue and replayed on the secondary D1.
- RTO (recovery time objective) and RPO (recovery point objective) are measured by a synthetic canary that probes both primaries and logs latency/errors to Analytics Engine.

## Solution

```typescript
// src/kv-sync/index.ts
// Runs on the PRIMARY account. Mirrors KV writes to the secondary account via a Queue.

import { KVNamespace, Queue } from '@cloudflare/workers-types';

export interface Env {
  KV_PRIMARY: KVNamespace;
  SYNC_QUEUE: Queue<KVSyncMessage>;
}

interface KVSyncMessage {
  action: 'put' | 'delete';
  key: string;
  value?: string;
  metadata?: Record<string, unknown>;
  expirationTtl?: number;
}

// Wrap KV writes to fan out to the sync queue
export async function kvPut(
  env: Env,
  key: string,
  value: string,
  options?: { expirationTtl?: number; metadata?: Record<string, unknown> },
): Promise<void> {
  await env.KV_PRIMARY.put(key, value, options);

  const msg: KVSyncMessage = {
    action: 'put',
    key,
    value,
    metadata: options?.metadata,
    expirationTtl: options?.expirationTtl,
  };
  await env.SYNC_QUEUE.send(msg);
}

export async function kvDelete(env: Env, key: string): Promise<void> {
  await env.KV_PRIMARY.delete(key);
  await env.SYNC_QUEUE.send({ action: 'delete', key });
}
```

```typescript
// src/kv-consumer/index.ts
// Runs on the SECONDARY account. Consumes sync messages and applies them to secondary KV.

import { KVNamespace, MessageBatch } from '@cloudflare/workers-types';

export interface Env {
  KV_SECONDARY: KVNamespace;
  SECONDARY_ACCOUNT_ID: string;
}

interface KVSyncMessage {
  action: 'put' | 'delete';
  key: string;
  value?: string;
  metadata?: Record<string, unknown>;
  expirationTtl?: number;
}

export default {
  async queue(batch: MessageBatch<KVSyncMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { action, key, value, metadata, expirationTtl } = msg.body;
      try {
        if (action === 'put' && value !== undefined) {
          await env.KV_SECONDARY.put(key, value, { metadata, expirationTtl });
        } else if (action === 'delete') {
          await env.KV_SECONDARY.delete(key);
        }
        msg.ack();
      } catch (err) {
        console.error(`KV sync failed for key=${key}:`, err);
        msg.retry();
      }
    }
  },
};
```

```typescript
// src/d1-cdc/index.ts
// Change-data-capture: primary Worker appends every mutating D1 query to a CDC queue.
// The secondary replays these statements on its own D1.

import { D1Database, Queue } from '@cloudflare/workers-types';

export interface Env {
  DB: D1Database;
  CDC_QUEUE: Queue<CDCEvent>;
}

export interface CDCEvent {
  sql: string;
  bindings: (string | number | null)[];
  timestamp: string;
  idempotency_key: string;
}

const idempotencyKey = () =>
  `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;

export async function dbRun(
  env: Env,
  sql: string,
  bindings: (string | number | null)[] = [],
): Promise<D1Result> {
  const stmt = env.DB.prepare(sql);
  const result = await (bindings.length ? stmt.bind(...bindings) : stmt).run();

  if (result.success) {
    const event: CDCEvent = {
      sql,
      bindings,
      timestamp: new Date().toISOString(),
      idempotency_key: idempotencyKey(),
    };
    // Non-blocking: if queue send fails, the primary operation already succeeded
    env.CDC_QUEUE.send(event).catch((e) => console.error('CDC queue send failed:', e));
  }

  return result;
}
```

```typescript
// src/d1-replica/index.ts
// Runs on the SECONDARY account. Replays CDC events on the secondary D1.

import { D1Database, MessageBatch } from '@cloudflare/workers-types';

export interface Env {
  DB_REPLICA: D1Database;
}

interface CDCEvent {
  sql: string;
  bindings: (string | number | null)[];
  timestamp: string;
  idempotency_key: string;
}

export default {
  async queue(batch: MessageBatch<CDCEvent>, env: Env): Promise<void> {
    // Replay events in order; queue delivery is ordered within a batch
    for (const msg of batch.messages) {
      const { sql, bindings, idempotency_key } = msg.body;

      // Idempotency check — skip if already applied
      const exists = await env.DB_REPLICA
        .prepare('SELECT 1 FROM cdc_applied WHERE idempotency_key = ?')
        .bind(idempotency_key)
        .first();

      if (exists) {
        msg.ack();
        continue;
      }

      try {
        const stmt = env.DB_REPLICA.prepare(sql);
        await (bindings.length ? stmt.bind(...bindings) : stmt).run();

        await env.DB_REPLICA
          .prepare('INSERT INTO cdc_applied (idempotency_key, applied_at) VALUES (?, datetime(\'now\'))')
          .bind(idempotency_key)
          .run();

        msg.ack();
      } catch (err) {
        console.error(`CDC replay failed [${idempotency_key}]:`, err);
        msg.retry({ delaySeconds: 10 });
      }
    }
  },
};
```

```typescript
// src/canary/index.ts
// Synthetic canary: measures RTO/RPO by probing both primary and secondary endpoints.

import { AnalyticsEngineDataset } from '@cloudflare/workers-types';

export interface Env {
  ANALYTICS: AnalyticsEngineDataset;
  PRIMARY_URL: string;
  SECONDARY_URL: string;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const probe = async (label: string, url: string) => {
      const start = Date.now();
      let status = 0;
      let ok = false;
      try {
        const res = await fetch(`${url}/health`, { signal: AbortSignal.timeout(5000) });
        status = res.status;
        ok = res.ok;
      } catch {
        ok = false;
      }
      const latencyMs = Date.now() - start;

      env.ANALYTICS.writeDataPoint({
        blobs: [label, ok ? 'up' : 'down'],
        doubles: [latencyMs, ok ? 1 : 0],
        indexes: [label],
      });

      console.log(`Canary [${label}] status=${status} latency=${latencyMs}ms ok=${ok}`);
      return ok;
    };

    const [primaryOk, secondaryOk] = await Promise.all([
      probe('primary', env.PRIMARY_URL),
      probe('secondary', env.SECONDARY_URL),
    ]);

    if (!primaryOk && secondaryOk) {
      console.warn('PRIMARY DOWN — secondary is healthy. DNS failover should be active.');
    }
  },
};
```

```yaml
# Cloudflare Load Balancer health-check configuration (Terraform)
resource "cloudflare_load_balancer_monitor" "workers_health" {
  account_id     = var.cf_account_id
  type           = "https"
  path           = "/health"
  expected_codes = "200"
  interval       = 30
  timeout        = 5
  retries        = 2
  description    = "Workers health check"
}

resource "cloudflare_load_balancer_pool" "primary" {
  account_id = var.cf_account_id
  name       = "workers-primary"
  monitor    = cloudflare_load_balancer_monitor.workers_health.id
  origins {
    name    = "primary"
    address = "orchords-api.orchords.workers.dev"
    enabled = true
  }
}

resource "cloudflare_load_balancer_pool" "secondary" {
  account_id = var.cf_account_id
  name       = "workers-secondary"
  monitor    = cloudflare_load_balancer_monitor.workers_health.id
  origins {
    name    = "secondary"
    address = "orchords-api-secondary.orchords-secondary.workers.dev"
    enabled = true
  }
}

resource "cloudflare_load_balancer" "api" {
  zone_id          = var.cf_zone_id
  name             = "api.example.com"
  fallback_pool_id = cloudflare_load_balancer_pool.secondary.id
  default_pool_ids = [cloudflare_load_balancer_pool.primary.id]
  proxied          = true

  rules {
    name      = "failover"
    condition = "true"
    overrides {
      session_affinity = "none"
    }
  }
}
```

## Implementation Details

**Account isolation** — Primary and secondary accounts are completely separate Cloudflare accounts with separate API tokens, billing, and incident blast radius. Do not use the same account for both.

**KV sync lag** — Cloudflare Queues delivers messages with at-least-once semantics. The consumer uses `msg.ack()` / `msg.retry()` to handle failures. Typical KV sync lag is under 5 seconds; design reads on the secondary to tolerate stale data up to 60 seconds.

**D1 replication lag** — CDC via Queues is eventually consistent. The secondary D1 may lag by seconds to minutes depending on queue throughput. For the failover case, this defines your RPO — measure it with the canary's Analytics Engine data.

**Idempotency** — The `cdc_applied` table prevents replaying the same mutation if a message is delivered twice. Prune it periodically: `DELETE FROM cdc_applied WHERE applied_at < datetime('now', '-7 days')`.

**Automated failover testing** — Monthly, simulate a failover by temporarily pointing the Load Balancer to the secondary pool and running the full smoke test suite. Document the RTO (time from primary failure to secondary serving traffic) and RPO (data loss window measured by the latest applied CDC event).

**DNS TTL** — Set a short TTL (60 seconds) on the Load Balancer DNS record so DNS changes propagate quickly during failover. Cloudflare-proxied records bypass TTL for clients using Cloudflare's resolver.

## Anti-patterns

- Sharing API tokens between primary and secondary accounts — defeats blast-radius isolation.
- Using KV as the sole data store for mutable state without sync — the secondary will serve stale or empty data after failover.
- Relying on Workers' global availability without health checks — automatic failover requires an active monitor.
- Applying CDC events out of order — Queue messages within a batch are ordered, but between batches you must use the `timestamp` field to detect out-of-order delivery.

## Gotchas

- Cloudflare Load Balancer is a paid add-on — it is not included in the Workers free tier.
- `AbortSignal.timeout()` requires compatibility date `2023-03-01` or later.
- Queues have a maximum message size of 128 KB — large D1 payloads (e.g. bulk inserts) must be chunked before enqueuing.
- The secondary account's Workers must be deployed separately; there is no cross-account Worker sharing.
- If the CDC queue itself is on the primary account, a full primary account outage also stops CDC delivery. For maximum resilience, use an external queue (e.g. Cloudflare Queues on a third account or a durable external broker).

## Verification

```bash
# Query canary metrics from Analytics Engine
curl -s \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  --data 'SELECT blob1 AS region, AVG(double1) AS avg_latency_ms, SUM(double2) AS up_count
          FROM canary_metrics
          WHERE timestamp > NOW() - INTERVAL \'1\' HOUR
          GROUP BY blob1'

# Simulate failover: temporarily disable the primary pool
curl -s -X PATCH \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/load_balancers/pools/$PRIMARY_POOL_ID" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'

# Run smoke tests against secondary
npm run test:smoke -- --base-url https://api.example.com

# Re-enable primary
curl -s -X PATCH \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/load_balancers/pools/$PRIMARY_POOL_ID" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

## Related

- `documentation/docs/policies/deploy/workers-version-pinning-gradual-rollout.md` — gradual rollout before exposing traffic to secondary
- `documentation/docs/policies/deploy/workers-deployment-approval-gates.md` — approval gates for deploying to both primary and secondary
- Cloudflare Load Balancer documentation
- Cloudflare Queues documentation
- Terraform Cloudflare provider

## Sources

- https://developers.cloudflare.com/load-balancing/
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs
