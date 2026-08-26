# Wrangler Tail Logs for Deployment Verification

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

After deploying a Cloudflare Worker you need real-time evidence that the new
version is handling live traffic correctly—before closing the deployment window
or removing the old version from a gradual rollout. Traditional smoke tests
fire synthetic requests but miss edge-case production traffic patterns.
`wrangler tail` streams live request logs, unhandled exceptions, and
`console.log()` output from the running Worker, making it the fastest feedback
loop available post-deploy.

## Context

`wrangler tail` opens a WebSocket connection to the Cloudflare Tail Workers
infrastructure and receives a structured JSON event for every request the
Worker processes. Each event includes: request metadata (URL, method, CF ray
ID, country), response status, CPU time, logs emitted via `console.*`, and
full exception stack traces. The stream is filtered at the edge, so only
matching events transit the wire.

Because tail is a live stream it is most useful during the first 5–15 minutes
after a deployment while you watch for error spikes, unexpected 5xx responses,
or latency outliers. It can also be scripted: pipe the JSON stream through
`jq` or a small Node script to assert invariants and exit non-zero if
violations are detected, integrating naturally into CI post-deploy steps.

Tail logs are ephemeral—they are not stored by Cloudflare unless you route
them through a Tail Worker that persists to R2 or Analytics Engine. For
persistent observability use `logpush` or Analytics Engine; tail is for
interactive or scripted short-window verification.

## Section 1: Interactive Tail During Manual Deployments

### Deploy and immediately attach tail

```bash
#!/usr/bin/env bash
set -euo pipefail

WORKER_NAME="api-gateway"
ENV="production"

# Deploy
wrangler deploy --name "$WORKER_NAME" --env "$ENV"

echo "Deployment complete. Attaching tail for 120 seconds..."

# Tail with structured JSON output; Ctrl-C or timeout ends the session
timeout 120 wrangler tail "$WORKER_NAME" \
  --env "$ENV" \
  --format json \
  2>/dev/null | jq --unbuffered '
    select(.event.response.status >= 500) |
    "ERROR \(.event.response.status) \(.event.request.url) ray=\(.event.rayId)"
  ' || true

echo "Tail window closed."
```

### Filter flags available in wrangler tail

```bash
# Errors only (status >= 500 or uncaught exceptions)
wrangler tail api-gateway --env production \
  --status error

# Filter by sampling rate (1–100 %; default 100)
wrangler tail api-gateway --env production \
  --sampling-rate 10 \
  --format json

# Filter by specific IP (useful for smoke-test client)
wrangler tail api-gateway --env production \
  --ip 203.0.113.42 \
  --format json

# Filter by request method
wrangler tail api-gateway --env production \
  --method POST \
  --format json
```

### Extract exception detail interactively

```bash
wrangler tail api-gateway --env production --format json 2>/dev/null \
  | jq --unbuffered '
      select(.exceptions | length > 0)
      | .exceptions[]
      | "\(.name): \(.message)"
    '
```

## Section 2: Scripted Post-Deploy Gate Using Tail Output

Pipe tail output through a verification script that runs for a fixed window and
fails if error thresholds are exceeded. Call this from CI immediately after
`wrangler deploy`.

### verify-tail.mjs

```javascript
#!/usr/bin/env node
// verify-tail.mjs — run after wrangler deploy
// Usage: WORKER=api-gateway ENV=production node verify-tail.mjs

import { spawn } from "node:child_process";

const WORKER = process.env.WORKER ?? "api-gateway";
const ENV = process.env.ENV ?? "production";
const WINDOW_MS = Number(process.env.WINDOW_MS ?? 90_000);   // 90 s
const ERROR_THRESHOLD = Number(process.env.ERROR_THRESHOLD ?? 5); // max 5xx count

let errors = 0;
let total = 0;

const proc = spawn(
  "wrangler",
  ["tail", WORKER, "--env", ENV, "--format", "json", "--sampling-rate", "100"],
  { stdio: ["ignore", "pipe", "inherit"] }
);

let buf = "";

proc.stdout.on("data", (chunk) => {
  buf += chunk.toString();
  const lines = buf.split("\n");
  buf = lines.pop() ?? "";

  for (const line of lines) {
    if (!line.trim()) continue;
    let event;
    try { event = JSON.parse(line); } catch { continue; }

    total++;
    const status = event?.event?.response?.status ?? 0;

    if (status >= 500 || (event.exceptions?.length ?? 0) > 0) {
      errors++;
      console.error(`[TAIL] ERROR status=${status} url=${event?.event?.request?.url}`);
    }
  }
});

setTimeout(() => {
  proc.kill("SIGTERM");

  console.log(`[TAIL] window closed. total=${total} errors=${errors}`);

  if (errors > ERROR_THRESHOLD) {
    console.error(`[TAIL] FAIL: ${errors} errors exceed threshold ${ERROR_THRESHOLD}`);
    process.exit(1);
  }

  console.log("[TAIL] PASS: error count within threshold");
  process.exit(0);
}, WINDOW_MS);

proc.on("error", (err) => {
  console.error("[TAIL] wrangler process error:", err.message);
  process.exit(2);
});
```

### CI step wrapping deploy + tail verification

```yaml
# .github/workflows/deploy.yml (relevant step only)
- name: Deploy and verify via tail
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
    WORKER: api-gateway
    ENV: production
    WINDOW_MS: "90000"
    ERROR_THRESHOLD: "3"
  run: |
    wrangler deploy --name "$WORKER" --env "$ENV"
    node scripts/verify-tail.mjs
```

## Section 3: Tail Worker for Persistent Post-Deploy Evidence

When you need a durable audit trail of the first N minutes of traffic after
each deployment, route tail events through a Tail Worker that writes to R2.

### Tail Worker definition (tail-logger/src/index.ts)

```typescript
export default {
  async tail(
    events: TraceItem[],
    env: { DEPLOY_LOGS: R2Bucket; DEPLOY_ID: string }
  ): Promise<void> {
    const key = `${env.DEPLOY_ID}/${Date.now()}.ndjson`;
    const body = events
      .map((e) => JSON.stringify(e))
      .join("\n");

    await env.DEPLOY_LOGS.put(key, body, {
      httpMetadata: { contentType: "application/x-ndjson" },
    });
  },
};
```

### wrangler.toml for the Tail Worker

```toml
name = "tail-logger"
main = "src/index.ts"
compatibility_date = "2026-01-01"

[[tail_consumers]]
service = "api-gateway"        # Worker whose tail to consume

[[r2_buckets]]
binding = "DEPLOY_LOGS"
bucket_name = "deploy-tail-logs"

[vars]
DEPLOY_ID = ""    # Overridden per deploy via --var DEPLOY_ID:<git-sha>
```

### Deploy Tail Worker with deploy ID injected

```bash
DEPLOY_ID=$(git rev-parse --short HEAD)
wrangler deploy --name tail-logger \
  --var "DEPLOY_ID:${DEPLOY_ID}"
```

## Anti-patterns

- **Leaving tail attached in production indefinitely**: tail is sampling
  infrastructure; extended sessions add overhead and consume API rate quota.
  Limit tail windows to the post-deploy verification period (≤15 min).

- **Using tail as the sole error detection mechanism**: tail operates at
  sampling rates below 100 % under high load. Complement with Cloudflare
  Analytics Engine metrics for aggregate error rate tracking.

- **Parsing wrangler tail in `--pretty` format**: the human-readable format
  changes across wrangler versions. Always use `--format json` in scripts.

- **Ignoring the `exceptions` array**: a Worker can return status 200 and
  still populate `exceptions` (e.g., background `waitUntil` tasks that threw).
  Check both `response.status` and `exceptions.length`.

- **Blocking the deploy step on a long tail window**: if the verification
  window is too long (>5 min), gate the rollout with canary traffic splitting
  instead and tail only the canary slice.

## Gotchas

- `wrangler tail` requires the `Workers Tail` permission on the API token
  (`com.cloudflare.api.account.worker.tail.read`). Add it explicitly—it is not
  included in the generic "Edit Workers" template.

- Tail events arrive with up to ~2 s latency; scripted windows should account
  for this and not terminate immediately after the last synthetic request.

- If a Worker has a Tail Worker consumer defined, `wrangler tail` and the Tail
  Worker both receive events independently—they do not compete.

- Free and Workers Bundled plans support tail, but there are per-account
  concurrency limits on simultaneous tail connections (typically 10).

- The `--ip self` flag resolves to your current outbound IP at session start;
  if your CI runner uses ephemeral IPs, filter by `--status error` instead.

## Verification

```bash
# Confirm wrangler tail permission is present on the token
curl -s -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/user/tokens/verify" \
  | jq '.result.status'
# expected: "active"

# Confirm tail opens and closes cleanly (10 s window)
timeout 10 wrangler tail api-gateway --env production \
  --format json --sampling-rate 1 2>&1 \
  | head -5

# Confirm verify-tail.mjs exits 0 after a clean deploy
WORKER=api-gateway ENV=production WINDOW_MS=30000 ERROR_THRESHOLD=0 \
  node scripts/verify-tail.mjs
echo "Exit code: $?"
```

## Related

- `deployment-verification-smoke-tests.md`
- `cloudflare-analytics-engine-deploy-observability.md`
- `rollback-decision-automation-slo-monitoring.md`
- `worker-versioning-gradual-rollout.md`
- `wrangler-deploy-github-actions-workers.md`

## Sources

- Cloudflare Workers Tail documentation: https://developers.cloudflare.com/workers/observability/tail-workers/
- Wrangler CLI tail reference: https://developers.cloudflare.com/workers/wrangler/commands/#tail
- Cloudflare API token permissions: https://developers.cloudflare.com/fundamentals/api/reference/permissions/
- Tail Workers limits: https://developers.cloudflare.com/workers/platform/limits/#tail-workers
