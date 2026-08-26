# Wrangler Observe Command Production Debugging

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Workers deployment produces intermittent errors or unexpected behaviour in production that
cannot be reproduced locally. Logs from `wrangler tail` capture structured log lines but
lack timing information about individual subrequests, binding calls, and the CPU timeline.
`wrangler observe` (introduced in Wrangler 3.x) streams Tail Worker event envelopes that
include granular spans for every D1 query, KV read, R2 operation, Durable Object call, and
`fetch()` subrequest — making it the primary tool for post-deploy tracing on a live Worker.

---

## Context

`wrangler observe` is a thin wrapper around the Tail Worker API that automatically creates
a transient Tail Worker, connects it to the target script, streams structured event
envelopes to your terminal, and tears down the Tail Worker on exit.

An event envelope contains:

- **`event`**: the triggering HTTP, Queue, Cron, or Durable Object event
- **`outcome`**: `ok`, `exception`, `exceeded-cpu`, `exceeded-memory`, `killed`, `canceled`
- **`logs`**: array of `console.log` / `console.error` entries with timestamps
- **`exceptions`**: uncaught errors with stack traces
- **`diagnosticsChannelEvents`**: spans for subrequests (not available in `wrangler tail`)

Comparison with `wrangler tail`:

| Feature                     | `wrangler tail` | `wrangler observe` |
|-----------------------------|:---------------:|:------------------:|
| Console log streaming        | Yes             | Yes                |
| Exception stack traces       | Yes             | Yes                |
| Subrequest spans             | No              | Yes                |
| CPU time per span            | No              | Yes (nanoseconds)  |
| Requires Tail Worker deploy  | No              | Transient auto-deploy |
| Filters by status/method     | Yes             | Yes                |

---

## Basic Usage

```bash
# Stream all events from a production Worker
npx wrangler observe my-worker --env production

# Filter to only requests that resulted in exceptions
npx wrangler observe my-worker --env production --status error

# Filter to specific HTTP method
npx wrangler observe my-worker --env production --method POST

# Filter to paths matching a sampling expression (1-in-10 requests)
npx wrangler observe my-worker --env production --sampling-rate 0.1

# Observe a specific Worker version by version ID
npx wrangler observe my-worker --env production \
  --version-id "abc123def456-0000-0000-0000-000000000001"
```

---

## Understanding the Event Envelope Output

`wrangler observe` prints coloured JSON by default. Here is an annotated envelope:

```jsonc
{
  "outcome": "exception",                      // Worker terminated with an unhandled error
  "event": {
    "request": {
      "method": "POST",
      "url": "https://api.example.com/ingest",
      "headers": { "content-type": "application/json" },
      "body": null
    }
  },
  "eventTimestamp": 1724405400123,             // Unix ms: when the request arrived at edge
  "logs": [
    {
      "level": "log",
      "timestamp": 1724405400130,              // ms offset from eventTimestamp
      "message": ["Processing request for user", "usr_abc123"]
    }
  ],
  "exceptions": [
    {
      "name": "TypeError",
      "message": "Cannot read properties of null (reading 'id')",
      "timestamp": 1724405400145
    }
  ],
  "diagnosticsChannelEvents": [
    {
      "timestamp": 1724405400131,
      "type": "subrequest",
      "url": "https://api.stripe.com/v1/charges",
      "method": "POST",
      "durationMs": 312,                       // wall-clock time for this subrequest
      "cpuTimeMs": 2.1                         // CPU time consumed during this span
    },
    {
      "timestamp": 1724405400135,
      "type": "d1",
      "query": "SELECT * FROM users WHERE id = ?",
      "durationMs": 8.4,
      "rowsRead": 1,
      "rowsWritten": 0
    }
  ],
  "cpuTime": 18,                               // total CPU ms consumed by the invocation
  "wallTime": 328                              // total wall-clock ms (includes I/O waits)
}
```

---

## TypeScript Envelope Parser for Structured Log Collection

Pipe `wrangler observe` output through this script to filter and forward critical events to
a logging backend (e.g., Baselime, Grafana Loki, Axiom).

```typescript
// scripts/observe-pipe.ts
// Usage: npx wrangler observe my-worker --env production | npx tsx scripts/observe-pipe.ts

import * as readline from "node:readline";

interface DiagnosticsEvent {
  timestamp: number;
  type: "subrequest" | "d1" | "kv" | "r2" | "do";
  url?: string;
  method?: string;
  query?: string;
  durationMs?: number;
  cpuTimeMs?: number;
  rowsRead?: number;
  rowsWritten?: number;
}

interface TailEvent {
  outcome: "ok" | "exception" | "exceeded-cpu" | "exceeded-memory" | "killed";
  event: { request?: { method: string; url: string } };
  eventTimestamp: number;
  logs: Array<{ level: string; timestamp: number; message: unknown[] }>;
  exceptions: Array<{ name: string; message: string; timestamp: number }>;
  diagnosticsChannelEvents?: DiagnosticsEvent[];
  cpuTime?: number;
  wallTime?: number;
}

const SLOW_SUBREQUEST_THRESHOLD_MS = 500;
const SLOW_D1_QUERY_THRESHOLD_MS = 50;
const LOG_EXCEPTIONS_ONLY = process.env.EXCEPTIONS_ONLY === "true";

function formatDuration(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${ms.toFixed(1)}ms`;
}

function analyzeEvent(event: TailEvent): void {
  const url = event.event?.request?.url ?? "unknown";
  const method = event.event?.request?.method ?? "?";
  const ts = new Date(event.eventTimestamp).toISOString();

  if (LOG_EXCEPTIONS_ONLY && event.outcome === "ok") return;

  const prefix = event.outcome !== "ok"
    ? `\x1b[31m[${event.outcome.toUpperCase()}]\x1b[0m`
    : `\x1b[32m[OK]\x1b[0m`;

  console.log(`${prefix} ${ts} ${method} ${url}`);
  console.log(`  CPU: ${event.cpuTime ?? "?"}ms  Wall: ${event.wallTime ?? "?"}ms`);

  // Print exceptions
  for (const ex of event.exceptions) {
    console.error(`  \x1b[31mException: ${ex.name}: ${ex.message}\x1b[0m`);
  }

  // Print slow subrequests
  for (const span of event.diagnosticsChannelEvents ?? []) {
    const dur = span.durationMs ?? 0;
    const isSlowFetch = span.type === "subrequest" && dur > SLOW_SUBREQUEST_THRESHOLD_MS;
    const isSlowD1 = span.type === "d1" && dur > SLOW_D1_QUERY_THRESHOLD_MS;

    if (isSlowFetch) {
      console.warn(
        `  \x1b[33mSLOW fetch\x1b[0m ${span.method} ${span.url} — ${formatDuration(dur)}`
      );
    }
    if (isSlowD1) {
      console.warn(
        `  \x1b[33mSLOW D1\x1b[0m "${span.query}" — ${formatDuration(dur)} ` +
          `(rows read: ${span.rowsRead ?? 0})`
      );
    }
  }
}

const rl = readline.createInterface({ input: process.stdin });
rl.on("line", (line) => {
  const trimmed = line.trim();
  if (!trimmed || !trimmed.startsWith("{")) return;
  try {
    const event = JSON.parse(trimmed) as TailEvent;
    analyzeEvent(event);
  } catch {
    // non-JSON line (banner, header) — ignore
  }
});
```

Run it:

```bash
EXCEPTIONS_ONLY=true \
  npx wrangler observe my-worker --env production | \
  npx tsx scripts/observe-pipe.ts
```

---

## Post-Deploy Validation Workflow Using `wrangler observe`

Use `wrangler observe` as a 5-minute post-deploy watch window in CI.

```yaml
# .github/workflows/deploy-with-observe.yml
name: Deploy and Observe

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    outputs:
      version_id: ${{ steps.deploy.outputs.version_id }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
      - run: npm ci

      - name: Deploy Worker
        id: deploy
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          command: deploy --env production

  post-deploy-observe:
    needs: deploy
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci

      - name: Observe for exception events (60 seconds)
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
        run: |
          # Run observe in background, capture output, fail if exceptions appear
          timeout 60 npx wrangler observe my-worker --env production --status error \
            > /tmp/observe-output.txt 2>&1 || true

          if grep -q '"outcome":"exception"' /tmp/observe-output.txt; then
            echo "ERROR: Exception events detected post-deploy:"
            cat /tmp/observe-output.txt
            exit 1
          fi
          echo "No exception events in 60s observation window."
```

---

## Filtering by Sampling Rate for High-Traffic Workers

On high-traffic Workers, streaming 100% of events floods your terminal. Use sampling
expressions to reduce noise while still catching errors.

```bash
# Sample 1% of all requests, but capture 100% of errors
npx wrangler observe my-worker --env production \
  --sampling-rate 0.01 \
  --status error

# Observe only requests to /api/* paths (requires wrangler ≥ 3.78)
npx wrangler observe my-worker --env production \
  --url-path-prefix "/api/"

# Observe a canary version only
CANARY_VERSION="abc123def456-0000-0000-0000-000000000001"
npx wrangler observe my-worker --env production \
  --version-id "$CANARY_VERSION" \
  --sampling-rate 0.1
```

---

## Anti-patterns

- **Leaving `wrangler observe` running indefinitely in CI** — it is a debugging tool, not a
  monitoring solution. For long-running observability, deploy a persistent Tail Worker to
  send events to a log analytics platform.
- **Piping observe output to a file with no timeout** — the process never exits on its own.
  Always wrap with `timeout` in CI contexts.
- **Forgetting that observe creates a transient Tail Worker** — on Workers Free, you have a
  10 Tail Worker limit. Running multiple observe sessions simultaneously may exhaust it.
- **Using observe in place of `wrangler tail` for simple log checks** — `wrangler tail` has
  lower overhead for viewing `console.log` output. Use `observe` specifically when you need
  subrequest span data.
- **Treating exception-free observe output as a guarantee of correctness** — observe only
  captures what fires during the observation window. Silent data corruption will not appear.

---

## Gotchas

- `wrangler observe` requires **Workers Free or Paid** — it is not available on Workers KV
  only accounts.
- `diagnosticsChannelEvents` are only available on Workers using `compatibility_date ≥
  2024-09-23`. Older compatibility dates expose the diagnostics channel but the span data
  may be incomplete.
- The transient Tail Worker created by `wrangler observe` counts against your Tail Worker
  quota. On Free plans, this quota is 10. If you see
  `"Too many Tail Workers"`, detach any existing Tail Workers first.
- `wrangler observe` does not support Workers on Routes (zone-based); it only connects to
  Workers accessed via `*.workers.dev`. For zone-routed Workers, you must deploy a named
  Tail Worker instead.
- Sampling rate flags may not apply to error events — depending on configuration, error
  events may always be forwarded regardless of sampling.

---

## Verification

```bash
# 1. Confirm wrangler observe is available
npx wrangler --version  # must be ≥ 3.x

# 2. Start observe and send a test request in a separate terminal
npx wrangler observe my-worker --env production &
curl https://my-worker.workers.dev/healthz
sleep 5 && kill %1

# 3. Check for the healthz event in stdout
# You should see a JSON envelope with outcome: "ok"

# 4. Trigger an intentional error to verify exception capture
curl https://my-worker.workers.dev/api/force-error

# 5. Confirm transient Tail Worker was cleaned up after observe exits
curl -s "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/workers/scripts/my-worker/tails" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" | jq '.result | length'
# Should return 0 after observe exits cleanly
```

---

## Related

- `wrangler-tail-logs-deployment-verification.md`
- `workers-tail-sampling-progressive-rollout.md`
- `workers-tail-worker-deploy-validation.md`
- `post-deploy-monitoring-checklist.md`
- `deployment-health-gates-automated-rollback.md`

---

## Sources

- Cloudflare Docs: `wrangler observe` — https://developers.cloudflare.com/workers/observability/logs/real-time-logs/
- Cloudflare Docs: Tail Workers — https://developers.cloudflare.com/workers/observability/logs/tail-workers/
- Cloudflare Docs: Workers diagnostics channel — https://developers.cloudflare.com/workers/observability/logs/workers-logs/
- Cloudflare Blog: Real-time debugging with Workers Trace Events — https://blog.cloudflare.com/workers-trace-events-security-analytics/
- Wrangler changelog: `observe` command — https://github.com/cloudflare/workers-sdk/releases
