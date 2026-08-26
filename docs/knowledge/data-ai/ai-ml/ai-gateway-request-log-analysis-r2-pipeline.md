# AI Gateway Request Log Analysis R2 Pipeline

- Date: 2026-08-23
- Author: example.com
- Status: production

## Symptom / Use-case

Your AI Gateway processes thousands of inference requests daily. The built-in gateway log viewer only shows recent entries and does not support complex aggregations (e.g. "which prompt templates produce the highest error rates?", "what is token-to-cost efficiency per provider over the last 30 days?"). You need durable, queryable log storage with an analysis layer — without leaving the Cloudflare ecosystem.

## Context

Cloudflare AI Gateway supports a log push webhook that fires an HTTP POST for each request/response pair. A receiver Worker ingests these payloads, enriches them (adding tenant ID, model alias, cost estimate), serializes to newline-delimited JSON (NDJSON), and writes to R2 in a partitioned path structure (`logs/year=YYYY/month=MM/day=DD/hour=HH/{uuid}.ndjson`). Periodic Cron Trigger Workers aggregate the hourly files into daily parquet-style roll-ups. Ad-hoc analysis can query R2 objects directly via a Worker, or the logs can be queried with Workers AI using the `rag-on-logs` pattern.

---

## 1. AI Gateway Log Push Configuration

Configure the log push webhook in the Cloudflare dashboard under **AI Gateway → Logs → Log Push**. Point it to your receiver Worker URL.

Expected payload shape per request (AI Gateway format):
```json
{
  "id": "01J5X...",
  "timestamp": "2026-08-23T14:22:01Z",
  "provider": "workers-ai",
  "model": "@cf/meta/llama-3.1-8b-instruct",
  "status": 200,
  "duration_ms": 843,
  "cost_usd": 0.0,
  "prompt_tokens": 312,
  "completion_tokens": 87,
  "cached": false,
  "metadata": {}
}
```

---

## 2. Log Receiver Worker

The receiver buffers incoming log events and writes them to R2 as time-partitioned NDJSON files.

```typescript
// src/log-receiver.ts
export interface Env {
  LOG_BUCKET: R2Bucket;
  LOG_BUFFER: KVNamespace;   // temp buffer for batching
  GATEWAY_WEBHOOK_SECRET: string;
}

interface GatewayLogEvent {
  id: string;
  timestamp: string;
  provider: string;
  model: string;
  status: number;
  duration_ms: number;
  cost_usd: number;
  prompt_tokens: number;
  completion_tokens: number;
  cached: boolean;
  metadata: Record<string, unknown>;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Verify webhook secret
    const secret = <redacted-secret>'x-webhook-secret');
    if (secret !== env.GATEWAY_WEBHOOK_SECRET) {
      return new Response('Unauthorized', { status: 401 });
    }

    const event = await request.json() as GatewayLogEvent;
    ctx.waitUntil(persistLogEvent(event, env));

    return new Response('ok', { status: 200 });
  },
};

async function persistLogEvent(event: GatewayLogEvent, env: Env): Promise<void> {
  const ts = new Date(event.timestamp);
  const partition = [
    `year=${ts.getUTCFullYear()}`,
    `month=${String(ts.getUTCMonth() + 1).padStart(2, '0')}`,
    `day=${String(ts.getUTCDate()).padStart(2, '0')}`,
    `hour=${String(ts.getUTCHours()).padStart(2, '0')}`,
  ].join('/');

  const key = `logs/${partition}/${event.id}.ndjson`;
  const line = JSON.stringify(event) + '\n';

  await env.LOG_BUCKET.put(key, line, {
    httpMetadata: { contentType: 'application/x-ndjson' },
    customMetadata: {
      provider: event.provider,
      model: event.model,
      status: String(event.status),
    },
  });
}
```

---

## 3. Hourly Roll-up Worker

Consolidate individual per-request NDJSON files into a single aggregated file per hour to reduce R2 API call overhead during analysis.

```typescript
// src/rollup-worker.ts  — cron: "5 * * * *" (5 minutes past each hour)
export interface Env {
  LOG_BUCKET: R2Bucket;
}

export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const now = new Date(event.scheduledTime);
    // Roll up the previous hour
    const rollupHour = new Date(now.getTime() - 60 * 60 * 1000);
    await rollupHour_(rollupHour, env);
  },
};

async function rollupHour_(hour: Date, env: Env): Promise<void> {
  const partition = [
    `year=${hour.getUTCFullYear()}`,
    `month=${String(hour.getUTCMonth() + 1).padStart(2, '0')}`,
    `day=${String(hour.getUTCDate()).padStart(2, '0')}`,
    `hour=${String(hour.getUTCHours()).padStart(2, '0')}`,
  ].join('/');

  const prefix = `logs/${partition}/`;
  const rollupKey = `rollups/${partition}/rollup.ndjson`;

  // Check if rollup already exists
  const existing = await env.LOG_BUCKET.head(rollupKey);
  if (existing) { return; }

  // List all event files in this hour partition
  const listed = await env.LOG_BUCKET.list({ prefix });
  if (listed.objects.length === 0) { return; }

  const lines: string[] = [];
  for (const obj of listed.objects) {
    if (obj.key === rollupKey) continue;
    const body = await env.LOG_BUCKET.get(obj.key);
    if (body) { lines.push(await body.text()); }
  }

  await env.LOG_BUCKET.put(rollupKey, lines.join(''), {
    httpMetadata: { contentType: 'application/x-ndjson' },
    customMetadata: { record_count: String(lines.length), partition },
  });
}
```

---

## 4. Log Query Worker

A simple query Worker reads rollup files for a date range and applies in-memory aggregations.

```typescript
// src/log-query.ts
export interface Env {
  LOG_BUCKET: R2Bucket;
}

interface AggRow {
  provider: string;
  model: string;
  requests: number;
  errors: number;
  total_tokens: number;
  total_cost_usd: number;
  avg_duration_ms: number;
}

export async function aggregateByModel(
  env: Env,
  fromDate: string, // 'YYYY-MM-DD'
  toDate: string
): Promise<AggRow[]> {
  const dates = datRange(fromDate, toDate);
  const agg = new Map<string, AggRow>();

  for (const date of dates) {
    const [year, month, day] = date.split('-');
    for (let hour = 0; hour < 24; hour++) {
      const partition = `year=${year}/month=${month}/day=${day}/hour=${String(hour).padStart(2, '0')}`;
      const rollupKey = `rollups/${partition}/rollup.ndjson`;

      const obj = await env.LOG_BUCKET.get(rollupKey);
      if (!obj) continue;

      const text = await obj.text();
      for (const line of text.split('\n').filter(Boolean)) {
        const event = JSON.parse(line) as { provider: string; model: string; status: number; prompt_tokens: number; completion_tokens: number; cost_usd: number; duration_ms: number };
        const key = `${event.provider}::${event.model}`;
        const existing = agg.get(key) ?? { provider: event.provider, model: event.model, requests: 0, errors: 0, total_tokens: 0, total_cost_usd: 0, avg_duration_ms: 0 };
        existing.requests += 1;
        if (event.status >= 400) existing.errors += 1;
        existing.total_tokens += (event.prompt_tokens ?? 0) + (event.completion_tokens ?? 0);
        existing.total_cost_usd += event.cost_usd ?? 0;
        existing.avg_duration_ms = (existing.avg_duration_ms * (existing.requests - 1) + event.duration_ms) / existing.requests;
        agg.set(key, existing);
      }
    }
  }

  return [...agg.values()].sort((a, b) => b.total_cost_usd - a.total_cost_usd);
}

function datRange(from: string, to: string): string[] {
  const dates: string[] = [];
  const current = new Date(from + 'T00:00:00Z');
  const end = new Date(to + 'T00:00:00Z');
  while (current <= end) {
    dates.push(current.toISOString().slice(0, 10));
    current.setUTCDate(current.getUTCDate() + 1);
  }
  return dates;
}
```

---

## 5. Retention and Lifecycle Policy

Automate log expiration to control R2 storage costs:

```typescript
// src/log-pruner.ts  — cron: "0 2 * * *" (daily at 02:00 UTC)
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const retentionDays = 90;
    const cutoff = new Date(Date.now() - retentionDays * 86400 * 1000);

    // List rollup files older than retention window
    const prefix = 'rollups/';
    let cursor: string | undefined;
    do {
      const listed = await env.LOG_BUCKET.list({ prefix, cursor });
      for (const obj of listed.objects) {
        // Parse partition date from key
        const match = obj.key.match(/year=(\d{4})\/month=(\d{2})\/day=(\d{2})/);
        if (match) {
          const objDate = new Date(`${match[1]}-${match[2]}-${match[3]}T00:00:00Z`);
          if (objDate < cutoff) {
            await env.LOG_BUCKET.delete(obj.key);
          }
        }
      }
      cursor = listed.truncated ? listed.cursor : undefined;
    } while (cursor);
  },
};
```

---

## Anti-patterns

- **Storing one R2 object per request long-term** — R2 Class B operations (reads per object) are billed per call. Always roll up individual event files into hourly or daily aggregates.
- **Writing synchronously inside the webhook response** — use `ctx.waitUntil(persistLogEvent(...))` to return HTTP 200 immediately; gateway may retry on timeouts.
- **Loading entire rollup files into memory for large date ranges** — stream and process line-by-line using `ReadableStream.getReader()` for files larger than ~5MB.
- **Not verifying the webhook secret** — anyone with your receiver URL could inject fake log events; always authenticate with a shared secret or HMAC.
- **Querying raw event files directly** — skip individual event files during analysis and always go through rollup files to minimize R2 Class B operation costs.

## Gotchas

- R2 `list()` returns at most 1000 objects per call; paginate with `cursor` when a partition has more than 1000 event files.
- AI Gateway log push webhooks are best-effort — some events may be missed during gateway outages. Do not use this as a billing-critical source of truth without cross-referencing provider invoices.
- R2 does not natively support SQL queries; for complex aggregations beyond what in-memory Workers can handle, export rollup files to D1 or use Workers AI with a RAG-on-logs pattern.
- The AI Gateway log push payload schema may evolve; always validate required fields before writing, and store raw JSON so schema changes do not corrupt the archive.
- `LOG_BUCKET.put()` with a key that already exists overwrites silently — ensure event IDs are globally unique (use the gateway-provided `id` field, not a local UUID).

## Verification

1. Send one test inference request through the gateway and confirm a matching `.ndjson` file appears in R2 under the correct partition within 30 seconds.
2. Trigger the rollup Worker manually (`wrangler dev --test-scheduled`) and verify `rollups/{partition}/rollup.ndjson` is created.
3. Call `aggregateByModel` for today's date and confirm `requests` count matches the number of test events sent.
4. Simulate a webhook with an invalid secret and assert HTTP 401 is returned.
5. Check R2 object count before and after the pruner to confirm objects older than retention are removed.

## Related

- `ai-gateway-logging.md`
- `cloudflare-ai-gateway-observability.md`
- `ai-gateway-latency-slo-analytics-engine.md`
- `ai-gateway-cost-attribution-per-tenant-d1.md`
- `workers-ai-image-classification-r2-pipeline.md`

## Sources

- https://developers.cloudflare.com/ai-gateway/observability/logging/
- https://developers.cloudflare.com/r2/
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
