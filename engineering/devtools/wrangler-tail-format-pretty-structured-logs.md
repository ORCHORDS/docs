# Wrangler Tail --format Flag: Pretty and JSON Structured Log Streaming

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Running `wrangler tail` dumps logs in a compact default format. During an
incident or a local debug session you want either:

1. **Human-readable, coloured output** you can scan in a terminal — use
   `--format pretty`.
2. **Machine-parseable JSON lines** you can pipe into `jq`, store in a file,
   or forward to a SIEM — use `--format json`.

The flag is often overlooked because the docs mention it only in passing, and
the defaults differ between CI and interactive terminals.

---

## Context

`wrangler tail` opens a WebSocket to the Cloudflare Logpush-compatible tail
endpoint for your Worker. The `--format` flag controls how the client
**renders** the raw log events it receives — it does not change what the
runtime captures.

Available formats (as of Wrangler ≥ 3.60):

| Format   | Description |
|----------|-------------|
| `pretty` | Coloured, human-readable multi-line block per request |
| `json`   | One JSON object per line (NDJSON / JSON Lines) |

Default: `pretty` when stdout is a TTY, `json` when stdout is piped.

---

## Basic Usage

```bash
# Pretty output in a terminal
wrangler tail --format pretty

# Explicit JSON Lines — same result as piping without the flag
wrangler tail --format json

# JSON piped to jq for filtering
wrangler tail --format json | jq 'select(.outcome == "exception")'

# Pretty output with environment and region filters
wrangler tail \
  --format pretty \
  --env production \
  --search "TypeError" \
  --status error
```

---

## What Pretty Format Shows

```
GET https://api.example.com/users/42  [ok] 11/23/2024, 14:02:37
  (log) Fetching user from D1
  (log) Cache miss – querying database
  (log) {"userId":42,"name":"Ada"}
  cpu: 1.2ms

POST https://api.example.com/webhooks  [exception] 11/23/2024, 14:02:41
  (exception) TypeError: Cannot read properties of undefined (reading 'id')
      at Object.fetch (worker.js:48:22)
  cpu: 0.4ms
```

Fields surfaced in `pretty` mode:

- HTTP method + URL
- Outcome badge: `ok`, `exception`, `canceled`, `exceededCpu`, `exceededMemory`
- Timestamp
- `console.log` / `console.error` / `console.warn` entries with their level
- CPU time
- Exception stack trace (when present)

---

## JSON Lines Schema

Each line emitted by `--format json` is a single JSON object:

```json
{
  "outcome": "ok",
  "scriptName": "my-worker",
  "exceptions": [],
  "logs": [
    {
      "message": ["Fetching user from D1"],
      "level": "log",
      "timestamp": 1732367357123
    }
  ],
  "eventTimestamp": 1732367357000,
  "event": {
    "request": {
      "url": "https://api.example.com/users/42",
      "method": "GET",
      "headers": {},
      "cf": {}
    },
    "response": { "status": 200 }
  },
  "id": 0,
  "cpuTime": 1.2
}
```

Queue, Cron Trigger, and Email events replace `event.request` with their own
shapes — `event.queue`, `event.cron`, and `event.email` respectively.

---

## Practical jq Recipes

```bash
# Show only exceptions with their stack traces
wrangler tail --format json \
  | jq 'select(.outcome == "exception") | {url: .event.request.url, ex: .exceptions}'

# Tail-grep: show console.error lines containing a keyword
wrangler tail --format json \
  | jq -r 'select(.outcome != "ok") | .logs[] | select(.level == "error") | .message[]'

# Count requests per status code in real time
wrangler tail --format json \
  | jq -r '.event.response.status' \
  | sort | uniq -c

# Latency histogram (requests exceeding 50 ms CPU)
wrangler tail --format json \
  | jq 'select(.cpuTime > 50) | {url: .event.request.url, cpu: .cpuTime}'
```

---

## Sending Structured Logs from the Worker

`console.log` accepts multiple arguments; they are serialised as an array in
`logs[].message`. Passing a single serialised JSON object makes `jq` easier:

```typescript
// src/logger.ts
export function log(level: "info" | "warn" | "error", payload: unknown) {
  const entry = JSON.stringify({ level, ts: Date.now(), ...castRecord(payload) });
  switch (level) {
    case "info":  console.log(entry);   break;
    case "warn":  console.warn(entry);  break;
    case "error": console.error(entry); break;
  }
}

function castRecord(v: unknown): Record<string, unknown> {
  return v !== null && typeof v === "object" ? (v as Record<string, unknown>) : { msg: v };
}
```

```typescript
// src/worker.ts
import { log } from "./logger";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    log("info", { event: "request.start", url: request.url });

    try {
      const result = await processRequest(request, env);
      log("info", { event: "request.ok", status: 200 });
      return result;
    } catch (err) {
      log("error", { event: "request.error", message: String(err) });
      throw err;
    }
  },
} satisfies ExportedHandler<Env>;
```

With this pattern, `jq` can parse the first element of `logs[].message`:

```bash
wrangler tail --format json \
  | jq '.logs[] | .message[0] | fromjson | select(.event == "request.error")'
```

---

## Filtering Flags That Complement --format

```bash
# Only see logs from requests that resulted in an error outcome
wrangler tail --format pretty --status error

# Full-text search in log lines (server-side filter, reduces noise)
wrangler tail --format pretty --search "D1_ERROR"

# Combine IP allowlist with pretty format for local dev
wrangler tail --format pretty --ip self

# Sampling (useful on high-traffic workers)
wrangler tail --format json --sampling-rate 0.1
```

---

## Saving a Tail Session to a File

```bash
# Record a session and view later
wrangler tail --format json > tail-$(date +%Y%m%dT%H%M%S).ndjson

# Replay and query
jq 'select(.outcome == "exception")' tail-20260823T140237.ndjson

# Pretty-print a saved NDJSON file (no live connection needed)
cat tail-20260823T140237.ndjson | jq -r '
  "\(.event.request.method) \(.event.request.url) [\(.outcome)]",
  (.logs[] | "  (\(.level)) \(.message[0])")
'
```

---

## CI / Automated Drain Pattern

To forward tail events to an external log drain from a CI job or sidecar:

```bash
#!/usr/bin/env bash
# scripts/tail-drain.sh
set -euo pipefail

DRAIN_URL="${LOG_DRAIN_URL:?must be set}"

wrangler tail --format json --env production \
  | while IFS= read -r line; do
      curl -s -X POST "$DRAIN_URL" \
        -H "Content-Type: application/json" \
        --data-raw "$line" > /dev/null
    done
```

---

## Anti-patterns

- **Parsing `pretty` output in scripts.** The coloured human-readable format
  is not stable. Pipe `--format json` and use `jq` instead.
- **Running `wrangler tail` in CI without `--format json`.** Default `pretty`
  mode emits ANSI escape codes that pollute CI logs. Always set
  `--format json` in non-interactive contexts.
- **Logging sensitive data via `console.log`.** Tail events are visible to
  anyone with `wrangler` access to the account. Redact tokens, passwords, and
  PII before logging.
- **Using `--search` as a replacement for proper structured logging.** The
  `--search` flag does a simple substring match on the raw log line. It cannot
  filter on JSON keys.

---

## Gotchas

- `wrangler tail` requires the `workers:read` and `workers:write` scopes on
  your API token. A token scoped only to deployment will receive a 403.
- Tail events have a **30-second buffer window** on the Cloudflare side. Very
  bursty traffic may arrive in batches rather than per-request.
- `cpuTime` is wall-clock CPU time inside the isolate, not wall-clock request
  latency. Waiting on fetch() or await does not count toward `cpuTime`.
- Cron Trigger events do not have `event.request`. Unconditionally accessing
  `.event.request.url` in a `jq` expression will output `null` for cron rows.
- The `--ip self` filter resolves your current egress IP at connection time.
  If you are behind a rotating proxy this filter may not match your requests.

---

## Verification

```bash
# Confirm wrangler version supports --format
wrangler --version  # must be ≥ 3.60

# Send a test request and see it appear
wrangler tail --format pretty &
TAIL_PID=$!
curl -s https://my-worker.workers.dev/ > /dev/null
sleep 2
kill $TAIL_PID

# Validate JSON Lines schema of first event
wrangler tail --format json | head -1 | jq 'keys'
```

---

## Related

- `wrangler-tail-log-filtering-advanced.md`
- `wrangler-tail-log-streaming-production.md`
- `wrangler-logpush-local-dev-debugging.md`
- `opentelemetry-workers-tracing-setup.md`
- `workers-devtools-protocol-chrome-debugger.md`

---

## Sources

- https://developers.cloudflare.com/workers/observability/logs/tail-workers/
- https://developers.cloudflare.com/workers/wrangler/commands/#tail
- https://developers.cloudflare.com/workers/observability/logs/real-time-logs/
- https://github.com/cloudflare/workers-sdk/blob/main/packages/wrangler/src/tail/
