# Wrangler Tail: Production Log Streaming and Real-Time Workers Debugging

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

A Worker is behaving unexpectedly in production — returning wrong status codes, silently swallowing errors, or timing out — but the issue does not reproduce locally. `console.log` statements exist in the code but you cannot see their output. You need a live stream of invocation logs, exceptions, and request metadata from the deployed Worker without adding external logging infrastructure.

---

## Context

`wrangler tail` opens a WebSocket connection from your terminal to the Cloudflare Logs streaming API. Every incoming request to the target Worker triggers a log event that includes:

- Request metadata (method, URL, headers, CF properties)
- `console.log` / `console.error` output
- Uncaught exceptions and their stack traces
- CPU time and wall-clock duration
- Response status code

The stream is ephemeral: events are not stored. For persistent storage use the Cloudflare Logpush service or Workers Analytics Engine. `wrangler tail` is designed for debugging sessions, not long-running audit pipelines.

---

## 1. Basic Usage

```bash
# Stream all log events from the deployed Worker named "my-worker"
wrangler tail my-worker

# Stream from a Worker in a specific environment
wrangler tail my-worker --env staging

# Stream from a Workers for Platforms dispatch namespace
wrangler tail --dispatch-namespace my-namespace user-worker-name
```

Output format (default `pretty`):

```
[2026-08-22 14:03:12] [200] GET https://my-worker.example.workers.dev/api/products
  (log) Fetching products from D1 for user abc123
  (log) D1 query returned 42 rows in 12ms
```

---

## 2. Filtering Events

Unfiltered tail on a high-traffic Worker produces thousands of events per second. Use `--filter` flags to narrow the stream:

```bash
# Only log events where the response status is 500
wrangler tail my-worker --status error

# Only requests to a specific URL path (substring match)
wrangler tail my-worker --header "x-debug-me: true"

# Filter by HTTP method
wrangler tail my-worker --method POST

# Filter by IP address (useful for tracing your own requests)
wrangler tail my-worker --ip self

# Combine multiple filters (all must match — AND semantics)
wrangler tail my-worker --status error --method POST
```

Status categories accepted by `--status`:

| Value     | Meaning                         |
|-----------|---------------------------------|
| `ok`      | HTTP 2xx and 3xx responses      |
| `error`   | HTTP 4xx and 5xx responses      |
| `open`    | Requests whose response has not completed (WebSocket upgrades, streaming) |

---

## 3. Structured Output with JSON Format

Switch to `--format json` to pipe events into `jq` for structured analysis:

```bash
wrangler tail my-worker --format json | jq '
  select(.outcome != "ok") |
  {
    time: .eventTimestamp,
    status: .response.status,
    url: .event.request.url,
    logs: [.logs[].message | join(" ")],
    exception: .exceptions[0].message
  }
'
```

The full JSON event schema:

```jsonc
{
  "outcome": "ok",                         // "ok" | "exception" | "exceededCpu" | "killed" | "canceled"
  "scriptName": "my-worker",
  "eventTimestamp": 1724332992000,
  "event": {
    "request": {
      "url": "https://my-worker.example.workers.dev/api",
      "method": "GET",
      "headers": { "cf-connecting-ip": "1.2.3.4" },
      "cf": {
        "colo": "LHR",
        "country": "GB",
        "tlsVersion": "TLSv1.3"
      }
    }
  },
  "logs": [
    { "message": ["Fetching products"], "level": "log", "timestamp": 1724332992010 }
  ],
  "exceptions": [],
  "response": { "status": 200 }
}
```

---

## 4. Sampling High-Volume Workers

Cloudflare's tail API delivers a sampled stream when a Worker processes thousands of requests per second. By default the sample rate is 1/100 under high load. You cannot control the sampling ratio from the CLI. To guarantee seeing a specific request, send it with a distinctive header and filter on that header:

```bash
wrangler tail my-worker --header "x-debug-session: 2026-08-22-ervin"
```

In your test request:

```bash
curl -H "x-debug-session: 2026-08-22-ervin" https://my-worker.example.workers.dev/api
```

This forces the tail stream to surface that specific invocation even during high traffic.

---

## 5. Capturing Unhandled Exceptions and Crash Loops

Unhandled exceptions in Worker code appear as events with `"outcome": "exception"`. Chain `jq` to extract just crash events with full context:

```bash
wrangler tail my-worker --format json \
  | jq --unbuffered 'select(.outcome == "exception") | {
      url: .event.request.url,
      exception: .exceptions[0].message,
      stack: .exceptions[0].stack,
      logs: [.logs[].message | join(" ")]
    }'
```

For a Worker in a crash loop (exiting before it can emit logs), check the `outcome` field:

| `outcome` value | Meaning |
|-----------------|---------|
| `exception`     | JavaScript threw an uncaught error |
| `exceededCpu`   | Worker exceeded the CPU time limit |
| `killed`        | Worker exceeded the wall-clock time limit |
| `canceled`      | Client disconnected before the Worker responded |

---

## 6. TypeScript Workflow: Correlating Logs with Source Maps

Production Workers are bundled and minified. Stack traces reference compiled positions, not TypeScript source. To correlate them back to your source:

### Step 1 — Emit source maps in production

```toml
# wrangler.toml
[build]
command = "pnpm build"

[build.upload]
format = "modules"

# Opt in to source map upload
[source_maps]
enabled = true
```

Or via the Wrangler build flag:

```bash
wrangler deploy --upload-source-maps
```

### Step 2 — Capture the minified stack trace from tail

```bash
wrangler tail my-worker --format json \
  | jq -r 'select(.outcome == "exception") | .exceptions[0].stack'
```

Example output:

```
Error: Cannot read properties of undefined (reading 'id')
  at Object.fetch (index.js:1:3842)
  at __facade_invoke__ (index.js:1:19201)
```

### Step 3 — Resolve with `wrangler sourcemap`

```bash
# Resolve a minified position to TypeScript source
wrangler sourcemap resolve --script my-worker --line 1 --column 3842
# => src/routes/products.ts:47:12
```

This requires that source maps were uploaded with the deployment.

---

## 7. Tail in CI / Automated Smoke Tests

You can run `wrangler tail` in the background during a smoke-test run and collect any errors:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Start tail, write JSON events to a temp file
wrangler tail my-worker --format json --env staging > /tmp/tail.jsonl &
TAIL_PID=$!

# Run smoke tests
pnpm test:e2e

# Stop tail
kill "$TAIL_PID" 2>/dev/null || true

# Fail the build if any exceptions were logged during the test run
EXCEPTION_COUNT=$(jq 'select(.outcome == "exception")' /tmp/tail.jsonl | jq -s 'length')
if [[ "$EXCEPTION_COUNT" -gt 0 ]]; then
  echo "ERROR: $EXCEPTION_COUNT exception(s) caught during smoke test"
  jq 'select(.outcome == "exception") | .exceptions[0].message' /tmp/tail.jsonl
  exit 1
fi

echo "No exceptions. Tail captured $(wc -l < /tmp/tail.jsonl) events."
```

---

## 8. Tailing Durable Objects and Queues

`wrangler tail` also surfaces events from Durable Objects and Queue consumers bound to the Worker:

```bash
# Durable Object logs appear inline with the Worker that owns them
wrangler tail my-worker

# For a Queue consumer, tail the consumer Worker directly
wrangler tail my-queue-consumer
```

Queue consumer events include the batch size and any messages that threw during processing:

```jsonc
{
  "outcome": "exception",
  "event": {
    "queue": "my-queue",
    "batchSize": 5
  },
  "exceptions": [{ "message": "DB write failed: UNIQUE constraint", "name": "Error" }]
}
```

---

## Anti-patterns

- **Using `wrangler tail` as a permanent log aggregation solution** — the stream is lossy and sampled; use Logpush + R2 or a third-party log drain for audit requirements.
- **Logging sensitive data with `console.log`** — tail output is visible to any team member with `wrangler` access and the correct `CLOUDFLARE_API_TOKEN`; scrub PII, tokens, and secrets before logging.
- **Filtering on response status alone** — a Worker that catches all exceptions and returns 200 will not appear under `--status error`; add explicit `console.error` calls in catch blocks.
- **Relying on unfiltered tail for high-traffic Workers** — you will miss events due to sampling; always add a distinctive request header when debugging a specific user flow.

---

## Gotchas

- `wrangler tail` requires the `workers:read` permission on the API token. If you see `403 Forbidden`, add the `Workers Tail Read` permission to the token in the Cloudflare dashboard.
- There is a limit of **10 concurrent tail sessions** per Worker. If you hit the limit, existing sessions must be closed before a new one opens.
- Logs from a Worker's **startup** phase (module-level code) are not captured by tail; only invocation-phase logs appear.
- `--ip self` resolves to the public IP of the machine running `wrangler tail`, not the machine making the request being debugged.
- Source map resolution with `wrangler sourcemap resolve` requires Wrangler 3.22+ and that the deployment was made with `--upload-source-maps`.
- Tail events are delivered with a small delay (typically 100–500 ms) and are **not guaranteed to arrive in order** under high concurrency.

---

## Verification

```bash
# Confirm tail connects and you see events
wrangler tail my-worker &
curl https://my-worker.example.workers.dev/health
# Should print a log event within ~1 second

# Verify API token has tail permission
wrangler whoami

# Check source map upload was successful
wrangler deployments list my-worker --format json \
  | jq '.[0] | {id, hasSourceMaps: .has_source_maps}'
```

---

## Related

- `wrangler-dev-remote-d1-r2-bindings.md` — remote binding dev without full deployment
- `opentelemetry-workers-tracing-setup.md` — structured traces for production observability
- `sentry-error-monitoring-setup.md` — persistent error tracking with source map integration
- `production-source-maps-strategy.md` — source map upload and security considerations

---

## Sources

- `wrangler tail` CLI reference: https://developers.cloudflare.com/workers/wrangler/commands/#tail
- Cloudflare Workers Logs documentation: https://developers.cloudflare.com/workers/observability/logs/workers-logs/
- Logpush for persistent log storage: https://developers.cloudflare.com/logs/about/
- Source map upload guide: https://developers.cloudflare.com/workers/observability/source-maps/
- Workers tail API (REST): https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/tails/
