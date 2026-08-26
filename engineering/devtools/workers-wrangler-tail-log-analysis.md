# Analyzing Workers Logs with `wrangler tail`

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have a Cloudflare Worker deployed to production and need to observe live request/response logs, diagnose intermittent 5xx errors, measure latency across endpoints, or capture structured JSON log payloads for post-mortem analysis — without instrumenting a full third-party logging pipeline.

---

## Context

`wrangler tail` opens a WebSocket connection to Cloudflare's tail API and streams `TailEvent` objects in real time. Each event contains the request metadata, response status, CPU time, wall time, console log lines, and any unhandled exceptions thrown during the invocation. Events can be filtered server-side before transmission so only relevant traffic consumes the WebSocket bandwidth.

By default `wrangler tail` pretty-prints events to stdout. Passing `--format json` emits one JSON object per line (NDJSON), which is compatible with `jq`, `grep`, file redirection, and any log aggregation tooling that understands line-delimited JSON.

Key flags:

| Flag | Purpose |
|------|---------|
| `--format json` | NDJSON output |
| `--status ok\|error\|canceled` | Filter by HTTP status class |
| `--method GET,POST` | Filter by HTTP method |
| `--header 'X-Debug: true'` | Filter by request header |
| `--sampling-rate 0.1` | Sample 10 % of requests |
| `--search <substring>` | Filter by log message substring |
| `--ip self` | Filter to your own IP |

---

## Solution

```typescript
// src/index.ts — Worker that emits structured logs for wrangler tail analysis
import { Env } from './worker-configuration';

interface RequestLog {
  requestId: string;
  method: string;
  url: string;
  cf: Record<string, unknown>;
  startMs: number;
}

interface ResponseLog extends RequestLog {
  status: number;
  durationMs: number;
  route: string;
  error?: string;
}

/** Derive a short route key from a URL for grouping in tail analysis. */
function routeKey(url: URL): string {
  // Replace numeric IDs so /users/123 and /users/456 both become /users/:id
  return url.pathname.replace(/\/\d+/g, '/:id').replace(/\/[\w-]{20,}/g, '/:uid');
}

/** Emit a structured log line that wrangler tail --format json will surface. */
function logEvent(event: ResponseLog): void {
  console.log(JSON.stringify(event));
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const startMs = Date.now();
    const requestId = crypto.randomUUID();
    const url = new URL(request.url);

    const reqLog: RequestLog = {
      requestId,
      method: request.method,
      url: request.url,
      cf: (request.cf ?? {}) as Record<string, unknown>,
      startMs,
    };

    try {
      const response = await handleRequest(request, env, ctx);
      const durationMs = Date.now() - startMs;

      logEvent({
        ...reqLog,
        status: response.status,
        durationMs,
        route: routeKey(url),
      });

      // Attach requestId header so tail events can be correlated with client logs
      const headers = new Headers(response.headers);
      headers.set('X-Request-Id', requestId);
      return new Response(response.body, { status: response.status, headers });
    } catch (err) {
      const durationMs = Date.now() - startMs;
      const error = err instanceof Error ? err.message : String(err);

      logEvent({
        ...reqLog,
        status: 500,
        durationMs,
        route: routeKey(url),
        error,
      });

      throw err; // re-throw so Cloudflare records the unhandled exception
    }
  },
} satisfies ExportedHandler<Env>;

async function handleRequest(request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
  const url = new URL(request.url);

  if (url.pathname === '/health') {
    return Response.json({ ok: true });
  }

  if (url.pathname.startsWith('/api/')) {
    // Simulate business logic
    return Response.json({ path: url.pathname }, { status: 200 });
  }

  return new Response('Not found', { status: 404 });
}
```

```bash
# 1. Stream all live logs in pretty mode
wrangler tail my-worker

# 2. Stream only errors as NDJSON and pipe to jq for pretty-printing
wrangler tail my-worker --format json --status error | jq .

# 3. Extract route + duration + status for a quick latency report
wrangler tail my-worker --format json \
  | jq -r '[.event.request.url, .event.response.status, .event.cpuTime] | @tsv'

# 4. Tail your own traffic only during manual QA
wrangler tail my-worker --ip self --format json | jq .

# 5. Save a 10-minute tail session to file for post-mortem, then analyse
wrangler tail my-worker --format json > /tmp/tail-$(date +%s).ndjson &
TAIL_PID=$!
sleep 600 && kill $TAIL_PID

# Post-mortem: error rate per route
jq -r 'select(.event.response.status >= 500) | .event.request.url' tail-*.ndjson \
  | sed 's|https://[^/]*/||' \
  | sort | uniq -c | sort -rn | head -20

# 6. Filter by custom header to trace a specific session
wrangler tail my-worker --header 'X-Session-Id: abc123' --format json

# 7. Sample 5 % of POST requests to reduce noise on busy endpoints
wrangler tail my-worker --method POST --sampling-rate 0.05 --format json
```

```typescript
// scripts/tail-metrics.ts — parse saved NDJSON and compute P50/P95/P99 latency
import * as fs from 'fs';
import * as readline from 'readline';

interface TailEvent {
  event: {
    request: { url: string; method: string };
    response: { status: number };
    cpuTime: number; // microseconds
  };
  logs: Array<{ message: string[] }>;
}

function percentile(sorted: number[], p: number): number {
  const idx = Math.ceil((p / 100) * sorted.length) - 1;
  return sorted[Math.max(0, idx)];
}

async function analyseFile(path: string): Promise<void> {
  const rl = readline.createInterface({ input: fs.createReadStream(path) });
  const cpuByRoute = new Map<string, number[]>();
  let errors = 0;
  let total = 0;

  for await (const line of rl) {
    if (!line.trim()) continue;
    try {
      const ev: TailEvent = JSON.parse(line);
      total++;
      const url = new URL(ev.event.request.url);
      const route = url.pathname.replace(/\/\d+/g, '/:id');
      const bucket = cpuByRoute.get(route) ?? [];
      bucket.push(ev.event.cpuTime / 1000); // convert to ms
      cpuByRoute.set(route, bucket);
      if (ev.event.response.status >= 500) errors++;
    } catch {
      // skip malformed lines
    }
  }

  console.log(`\nTotal events: ${total}  |  Errors: ${errors} (${((errors / total) * 100).toFixed(1)}%)\n`);
  console.log('Route'.padEnd(40), 'P50'.padStart(8), 'P95'.padStart(8), 'P99'.padStart(8), 'Count'.padStart(8));
  console.log('-'.repeat(72));

  for (const [route, values] of [...cpuByRoute.entries()].sort((a, b) => b[1].length - a[1].length)) {
    const sorted = values.sort((a, b) => a - b);
    console.log(
      route.padEnd(40),
      `${percentile(sorted, 50).toFixed(1)}ms`.padStart(8),
      `${percentile(sorted, 95).toFixed(1)}ms`.padStart(8),
      `${percentile(sorted, 99).toFixed(1)}ms`.padStart(8),
      String(sorted.length).padStart(8),
    );
  }
}

const file = process.argv[2];
if (!file) {
  console.error('Usage: npx tsx scripts/tail-metrics.ts <tail.ndjson>');
  process.exit(1);
}
analyseFile(file).catch(console.error);
```

---

## Implementation Details

- **`wrangler tail` requires authentication** — the CLI must be logged in (`wrangler login`) or have `CLOUDFLARE_API_TOKEN` set with the `Workers Tail Read` permission.
- **CPU time vs wall time** — `event.cpuTime` measures actual JS execution microseconds; wall time includes I/O wait. For fetch-heavy Workers, cpuTime will be far lower than actual latency.
- **Log message payload** — each `console.log(...)` call inside the Worker surfaces as an entry in `logs[].message[]`. When the Worker logs structured JSON, the string must be parsed again client-side (the tail API wraps it as a string).
- **Sampling is server-side** — `--sampling-rate` reduces traffic before it reaches the WebSocket; it is not a client-side filter, so it genuinely reduces load on the tail connection.
- **NDJSON compatibility** — one JSON object per newline with no trailing comma; compatible with `jq` streaming mode (`jq -c '.' --stream` is not needed — standard `jq .` works line-by-line when piped).

---

## Anti-patterns

- **Logging PII in console.log** — `wrangler tail` output is visible to anyone with the API token. Strip emails, tokens, and payment data before logging.
- **Over-logging in production** — logging every key/value lookup in hot paths inflates CPU time billing. Log at entry/exit points only.
- **Relying on tail for alerting** — `wrangler tail` is an ad-hoc debugging tool, not a reliable alerting channel. Use Cloudflare Logpush + a SIEM for production alerting.
- **Blocking on `console.log`** — `console.log` in Workers is synchronous from the user's perspective but does not block the response. Do not use it as a timing gate.

---

## Gotchas

- Tail events may arrive **out of order** for concurrent requests; always sort by `startMs` when doing post-mortem analysis.
- The `--search` flag matches against the entire serialised event JSON, not just log messages — it can match on URLs, headers, and CF properties too.
- `wrangler tail` **disconnects after 10 minutes** of inactivity by default. For long capture sessions, use a loop: `while true; do wrangler tail my-worker --format json >> tail.ndjson; sleep 1; done`.
- **Free plan Workers** do not support tail. A paid Workers plan (or Workers Paid) is required.

---

## Verification

```bash
# Confirm tail connects and events flow
wrangler tail my-worker --format json --sampling-rate 1.0 &
curl https://my-worker.example.workers.dev/health
# Expect: one JSON event printed within ~2 s with status 200

# Verify structured log extraction
wrangler tail my-worker --format json | jq '.logs[].message[]' -r | jq . 2>/dev/null | head -20
```

---

## Related

- `documentation/categories/devtools/wrangler-dev-workflow.md`
- `documentation/categories/devtools/sourcemap-debugging.md`
- `documentation/categories/devtools/bundle-size-analysis.md`

---

## Sources

- https://developers.cloudflare.com/workers/observability/log-from-workers/
- https://developers.cloudflare.com/workers/wrangler/commands/#tail
- https://developers.cloudflare.com/workers/observability/tail-workers/
