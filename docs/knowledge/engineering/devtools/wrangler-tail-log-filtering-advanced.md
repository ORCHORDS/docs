# Wrangler Tail Log Filtering Advanced Patterns

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You are running `wrangler tail` against a high-traffic Worker and the raw log volume is too
large to read in real time. You need to focus on specific request paths, status codes,
client IPs, or custom header values without waiting for a post-hoc log export from the
Cloudflare dashboard. You want repeatable filter expressions you can script into a
developer workflow or CI smoke-test.

Advanced filtering also matters when you are debugging a production incident: pinning the
tail stream to error-level events only, or to a specific User-Agent, cuts the signal-to-
noise ratio dramatically and makes root-cause identification faster.

## Context

`wrangler tail` opens a WebSocket connection to Cloudflare's log-streaming infrastructure
and delivers real-time log lines for a deployed Worker. The CLI ships with a set of
`--filter` flags that instruct the log service to apply server-side predicates before the
line is transmitted. This means filtering happens at the edge — you are not downloading
every log line and grepping locally. The supported filter dimensions as of Wrangler v3.x
are: sampling rate, HTTP method, HTTP status code range, client IP address, URL substring
search, and log level. Filters compose with AND semantics by default; OR semantics require
multiple concurrent `wrangler tail` invocations piped through `jq`.

## Server-Side Filter Flags

Every flag below is evaluated on the Cloudflare edge before bytes are sent to your terminal,
so heavy traffic Workers remain usable even at 100 % sampling.

```bash
# Stream only 5xx responses from POST/PUT requests
wrangler tail my-worker \
  --status 500-599 \
  --method POST \
  --method PUT

# Search for a URL substring (case-sensitive)
wrangler tail my-worker \
  --search "/api/payments"

# Lock to a single client IP (useful during manual integration tests)
wrangler tail my-worker \
  --ip-address 203.0.113.42

# Reduce sampling to 10 % of all requests (reduces volume, not just errors)
wrangler tail my-worker \
  --sampling-rate 0.1

# Combine: 1 % sample of only 4xx from a specific IP
wrangler tail my-worker \
  --sampling-rate 0.01 \
  --status 400-499 \
  --ip-address 203.0.113.42
```

The `--status` flag accepts a single code (`--status 429`) or an inclusive range
(`--status 500-599`). Ranges must use the `low-high` dash syntax; open-ended ranges are
not supported.

## Structured JSON Output and jq Pipelines

The default output format is human-readable. Switching to `--format json` emits one JSON
object per log line, which lets `jq` do second-pass filtering on fields not exposed by the
server-side flags (e.g. response headers, custom log properties emitted via
`console.log(JSON.stringify({...}))`).

```bash
# Tail as JSON, filter locally for requests that took > 200 ms
wrangler tail my-worker --format json \
  | jq 'select(.eventTimestamp != null)
        | select((.event.response.duration // 0) > 200)'

# Extract only the URL and status for a quick summary
wrangler tail my-worker --format json \
  | jq -r '[.event.request.url, (.event.response.status | tostring)] | @tsv'

# Capture logs that contain a specific console.log key
wrangler tail my-worker --format json \
  | jq 'select(.logs[]?.message[]? | tostring | contains("\"level\":\"error\""))'
```

`jq` is executed client-side and therefore applies to the already-sampled stream. When
using `--sampling-rate` with `jq` post-filters, remember that the denominator is the
sampled subset, not total traffic.

## Filtering Across Multiple Workers (Fanout Pattern)

Service-binding chains mean a single user request may touch several Workers. To correlate
logs across workers you can open parallel tail sessions and merge them with `jq --slurp`
or pipe both streams into a file.

```bash
# Terminal 1
wrangler tail api-gateway --format json > /tmp/gateway.log &

# Terminal 2
wrangler tail auth-worker --format json > /tmp/auth.log &

# Merge and sort by timestamp
tail -f /tmp/gateway.log /tmp/auth.log \
  | jq --slurp 'sort_by(.eventTimestamp)'
```

For CI smoke tests, a more robust approach uses a small Node script that opens two
WebSocket connections and multiplexes the streams:

```typescript
// scripts/tail-multi.ts
import { execSync } from "node:child_process";
import { spawn } from "node:child_process";

const workers = ["api-gateway", "auth-worker", "queue-consumer"];

const procs = workers.map((name) =>
  spawn("wrangler", ["tail", name, "--format", "json"], {
    stdio: ["ignore", "pipe", "inherit"],
  })
);

procs.forEach((proc, i) => {
  proc.stdout.on("data", (chunk: Buffer) => {
    const lines = chunk.toString().split("\n").filter(Boolean);
    for (const line of lines) {
      try {
        const event = JSON.parse(line);
        console.log(JSON.stringify({ worker: workers[i], ...event }));
      } catch {
        // incomplete JSON chunk, skip
      }
    }
  });
});

process.on("SIGINT", () => procs.forEach((p) => p.kill()));
```

## Scripted Smoke-Test Assert Pattern

You can use `wrangler tail` inside an end-to-end test harness to assert that a deployed
Worker did not emit any errors during a test request batch.

```typescript
// e2e/smoke-tail.ts
import { spawn } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";

export async function assertNoErrors(
  workerName: string,
  fn: () => Promise<void>
): Promise<void> {
  const errors: string[] = [];

  const tail = spawn(
    "wrangler",
    ["tail", workerName, "--format", "json", "--status", "500-599"],
    { stdio: ["ignore", "pipe", "inherit"] }
  );

  tail.stdout.on("data", (chunk: Buffer) => {
    const lines = chunk.toString().split("\n").filter(Boolean);
    for (const line of lines) {
      try {
        const ev = JSON.parse(line);
        errors.push(
          `${ev.event?.request?.url} → ${ev.event?.response?.status}`
        );
      } catch {
        /* partial chunk */
      }
    }
  });

  // Give the WebSocket a moment to connect
  await delay(1500);

  await fn();

  // Drain any buffered events
  await delay(2000);
  tail.kill();

  if (errors.length > 0) {
    throw new Error(`Worker errors detected:\n${errors.join("\n")}`);
  }
}
```

```typescript
// e2e/payment.test.ts
import { assertNoErrors } from "./smoke-tail.js";
import { fetchPaymentEndpoint } from "./helpers.js";

test("payment flow produces no 5xx", async () => {
  await assertNoErrors("payment-worker", async () => {
    await fetchPaymentEndpoint({ amount: 100, currency: "USD" });
  });
});
```

## Anti-patterns

- Using `--sampling-rate 1.0` (the default) in production at very high RPS — the volume
  can overwhelm the terminal buffer and cause tail to drop events silently; always combine
  with a status or search filter on busy Workers.
- Relying on client-side `grep` instead of server-side `--search` — this downloads all
  events before filtering and wastes bandwidth when the Worker handles thousands of RPS.
- Opening `wrangler tail` inside a CI job without a timeout — if the test process hangs,
  the tail process keeps the CI job alive indefinitely.
- Storing tail output files that contain user IP addresses without scrubbing — these are
  personal data and subject to GDPR/CCPA retention limits.
- Using `--ip-address self` to filter to your own IP during staging and forgetting to
  remove the flag before committing a shared test script.

## Gotchas

- `--status` ranges only cover HTTP response codes; Cloudflare Workers exceptions that
  never produce a response (uncaught exceptions) appear with status `0` in the JSON
  output and will NOT match `--status 500-599`.
- The `--search` flag matches the full request URL including query string. Regex is not
  supported; it is a plain substring match.
- Log lines emitted from Durable Objects accessed via a Worker do NOT appear in the tail
  for the calling Worker. You must run a separate `wrangler tail` for the Durable Object's
  Worker script.
- `wrangler tail` requires an active internet connection to Cloudflare's infrastructure
  even for Workers deployed with `--env dev`. It cannot tail a `wrangler dev` local
  session; for local debugging use `console.log` output in the `wrangler dev` terminal.
- The WebSocket connection is dropped by Cloudflare after approximately 60 minutes; build
  reconnect logic into long-running tail scripts.

## Verification

1. Deploy a Worker that intentionally returns a 500 for requests to `/error`:

```typescript
// src/index.ts
export default {
  fetch(req: Request): Response {
    if (new URL(req.url).pathname === "/error") {
      return new Response("boom", { status: 500 });
    }
    return new Response("ok");
  },
};
```

2. In one terminal: `wrangler tail my-worker --format json --status 500-599 --search /error`
3. In another terminal: `curl https://my-worker.example.workers.dev/error`
4. Verify that exactly one JSON event appears in the tail terminal with `status: 500`.
5. Send `curl https://my-worker.example.workers.dev/ok` and confirm no event appears.

## Related

- `wrangler-tail-log-streaming-production.md` — baseline streaming setup
- `wrangler-dev-local-vs-remote-mode-decision-tree.md` — choosing the right dev mode
- `opentelemetry-workers-tracing-setup.md` — structured tracing as an alternative to log tailing
- `durable-objects-local-debugging.md` — debugging DO-specific log events

## Sources

- Cloudflare Docs: "wrangler tail" — https://developers.cloudflare.com/workers/wrangler/commands/#tail
- Cloudflare Docs: "Logpush" (production alternative) — https://developers.cloudflare.com/logs/logpush/
- Wrangler GitHub source: packages/wrangler/src/tail — https://github.com/cloudflare/workers-sdk
