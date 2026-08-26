# Wrangler Tail Log Streaming in GitHub Actions CI

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

After deploying a Cloudflare Worker in CI you need to:
- Confirm the Worker boots and handles a smoke-test request without a runtime error
- Capture live console output (`console.log`, uncaught exceptions) during integration tests
- Pipe Worker logs into the GitHub Actions job summary or an artifact for post-mortem debugging
- Detect a `500 Internal Server Error` caused by an unhandled promise rejection and fail the job

`wrangler tail` streams real-time logs from a deployed Worker over a WebSocket. Used inside a
GitHub Actions step it becomes a lightweight observability layer that bridges Cloudflare's
runtime telemetry into your CI pipeline — without deploying a separate observability stack.

---

## Context

`wrangler tail [script-name]` opens a WebSocket to Cloudflare's Tail Workers API and streams
structured JSON log events including:

- `console.*` output
- Uncaught exceptions and their stack traces
- Request metadata (method, URL, status, duration)
- Structured `TailEvent` objects

The command runs until interrupted (`CTRL+C`) or until a `--format` filter finds a match and
exits (with `--once` or via shell signal). In CI, you typically:

1. Deploy the Worker
2. Launch `wrangler tail` in the background
3. Send smoke-test HTTP requests to the Worker
4. Kill the tail process and inspect its output

`wrangler tail` requires `CLOUDFLARE_API_TOKEN` with the **"Workers Tail"** permission
(`com.cloudflare.api.account.worker.tail.read`).

---

## Basic CI Step Pattern

```yaml
# .github/workflows/smoke-test.yml
name: Deploy and smoke test
on:
  push:
    branches: [main]

env:
  CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
  CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

jobs:
  smoke-test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 22

      - run: npm ci

      - name: Deploy Worker
        run: npx wrangler deploy

      - name: Collect tail logs during smoke test
        id: tail
        run: |
          # Write logs to a file so we can inspect them after
          LOG_FILE="${RUNNER_TEMP}/wrangler-tail.log"

          # Start tail in background, capture its PID
          npx wrangler tail api-gateway \
            --format pretty \
            --env production \
            > "$LOG_FILE" 2>&1 &
          TAIL_PID=$!
          echo "tail_pid=$TAIL_PID" >> "$GITHUB_OUTPUT"
          echo "log_file=$LOG_FILE" >> "$GITHUB_OUTPUT"

          # Give the WebSocket time to connect
          sleep 3

          # Send smoke-test requests
          WORKER_URL="https://api-gateway.acme-workers.dev"

          STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$WORKER_URL/health")
          echo "health check status: $STATUS"

          if [ "$STATUS" != "200" ]; then
            echo "::error::Health check returned $STATUS"
            kill $TAIL_PID || true
            exit 1
          fi

          # Run a few more test requests
          curl -s "$WORKER_URL/api/version" | jq .
          curl -s -X POST "$WORKER_URL/api/echo" \
            -H "Content-Type: application/json" \
            -d '{"ping": "ci"}' | jq .

          # Allow logs to flush
          sleep 2

          # Stop tail
          kill $TAIL_PID || true
          wait $TAIL_PID 2>/dev/null || true

      - name: Check tail logs for errors
        run: |
          LOG_FILE="${{ steps.tail.outputs.log_file }}"
          echo "=== Wrangler tail output ==="
          cat "$LOG_FILE"

          # Fail if any uncaught exception was logged
          if grep -q "uncaughtException\|Uncaught\|Error:" "$LOG_FILE"; then
            echo "::error::Worker emitted runtime errors during smoke test"
            exit 1
          fi

          # Fail if any 5xx response was observed
          if grep -qE '5[0-9]{2}' "$LOG_FILE"; then
            echo "::error::Worker returned 5xx responses"
            exit 1
          fi

          echo "::notice::No errors detected in Worker logs"

      - name: Upload tail logs as artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: wrangler-tail-${{ github.run_id }}
          path: ${{ runner.temp }}/wrangler-tail.log
          retention-days: 7
```

---

## JSON Format for Structured Log Parsing

Use `--format json` to capture machine-readable events and parse them with `jq` or a Worker:

```yaml
- name: Tail in JSON mode and detect exceptions
  run: |
    LOG_FILE="${RUNNER_TEMP}/tail-json.log"

    npx wrangler tail api-gateway \
      --format json \
      --env production \
      > "$LOG_FILE" 2>&1 &
    TAIL_PID=$!

    sleep 3
    # ... run tests ...
    sleep 2
    kill $TAIL_PID || true
    wait $TAIL_PID 2>/dev/null || true

    # Parse: count exceptions
    EXCEPTION_COUNT=$(jq -s '
      [.[] | select(.exceptions | length > 0)] | length
    ' "$LOG_FILE")

    echo "Exceptions during smoke test: $EXCEPTION_COUNT"

    if [ "$EXCEPTION_COUNT" -gt "0" ]; then
      echo "::error::$EXCEPTION_COUNT exception(s) caught in Worker"
      jq -s '.[] | select(.exceptions | length > 0) | .exceptions[]' "$LOG_FILE"
      exit 1
    fi

    # Parse: extract all console.log messages
    jq -s '.[] | .logs[]? | select(.level == "log") | .message[]?' "$LOG_FILE"
```

A `wrangler tail` JSON event looks like:

```json
{
  "outcome": "ok",
  "scriptName": "api-gateway",
  "exceptions": [],
  "logs": [
    {
      "message": ["[router] GET /health → 200 in 3ms"],
      "level": "log",
      "timestamp": 1724371200000
    }
  ],
  "eventTimestamp": 1724371200000,
  "event": {
    "request": {
      "url": "https://api-gateway.acme-workers.dev/health",
      "method": "GET",
      "headers": {},
      "cf": {}
    },
    "response": { "status": 200 }
  }
}
```

---

## Filtering by Sampling Rate and Status

`wrangler tail` samples at 1% by default on high-traffic Workers. In CI with low request rates,
raise sampling to 100% to capture every event:

```yaml
- name: Tail with 100% sampling during smoke test
  run: |
    npx wrangler tail api-gateway \
      --format json \
      --sampling-rate 1  \     # 1 = 100%
      --status error     \     # only stream events with errors (reduces noise)
      --env production \
      > "${RUNNER_TEMP}/errors-only.log" 2>&1 &
```

Available `--status` values: `ok`, `error`, `canceled`. Combining
`--sampling-rate 1 --status error` streams only errored requests, dramatically reducing
log volume in integration tests.

---

## Attaching Logs to the Job Summary

```yaml
- name: Write tail summary to job summary
  if: always()
  run: |
    LOG_FILE="${{ steps.tail.outputs.log_file }}"
    {
      echo "## Wrangler Tail — Smoke Test Logs"
      echo ""
      echo "\`\`\`"
      tail -n 50 "$LOG_FILE" || echo "(no logs captured)"
      echo "\`\`\`"
    } >> "$GITHUB_STEP_SUMMARY"
```

---

## TypeScript: Parsing Tail Events in a Worker Receiver

If you forward tail events to a second Worker (via a Tail Worker binding), you can store them
in D1 or R2 for long-term retention:

```typescript
// src/workers/tail-receiver.ts
// wrangler.toml: [[tail_consumers]] binding = "LOG_RECEIVER"

interface TailEvent {
  scriptName: string;
  outcome: "ok" | "error" | "canceled" | "exceededCpu" | "exceededMemory";
  exceptions: Array<{ name: string; message: string; timestamp: number }>;
  logs: Array<{ message: unknown[]; level: string; timestamp: number }>;
  eventTimestamp: number;
}

export default {
  async tail(events: TailEvent[], env: { DB: D1Database }): Promise<void> {
    const errorEvents = events.filter(
      (e) => e.outcome !== "ok" || e.exceptions.length > 0,
    );

    if (errorEvents.length === 0) return;

    const stmts = errorEvents.map((e) =>
      env.DB.prepare(
        `INSERT INTO worker_errors
           (script_name, outcome, exception_json, ts)
         VALUES (?, ?, ?, datetime('now'))`,
      ).bind(
        e.scriptName,
        e.outcome,
        JSON.stringify(e.exceptions),
      ),
    );

    await env.DB.batch(stmts);
  },
};
```

---

## Anti-patterns

- **Running `wrangler tail` without a timeout** — if the tail process is not killed, it will
  run until the GitHub Actions job hits its `timeout-minutes` limit. Always kill the PID
  explicitly or use a timeout wrapper:
  ```bash
  timeout 30s npx wrangler tail api-gateway --format json > "$LOG_FILE" 2>&1 || true
  ```

- **Parsing `pretty` output with grep for structured data** — `--format pretty` is
  human-readable and its format is not stable across wrangler versions. Always use
  `--format json` when you need to parse log data programmatically.

- **Forgetting that tail has 30-second startup latency on first use** — Cloudflare provisions
  a tail session asynchronously. If your smoke tests complete in under 5 seconds, the tail
  may not capture any events. Add a `sleep 3` after starting tail before sending requests.

- **Using `--env` mismatch** — if you deployed to `--env staging` but tail to `--env production`
  (or vice versa), the tail connects to the wrong Worker instance and you'll see no events.
  Always match the deployment environment.

---

## Gotchas

- **Tail Workers vs `wrangler tail`** — Tail Workers (configured in `wrangler.toml` under
  `[[tail_consumers]]`) receive events asynchronously in production. `wrangler tail` is a
  developer/CI tool that opens a temporary WebSocket session — events are not guaranteed to
  arrive if the Worker is under high load.

- **`--format json` outputs one JSON object per line**, not a JSON array. Use
  `jq -s '...'` (slurp mode) to parse multiple events as an array.

- **Tail sessions expire after 10 minutes** — if integration tests run longer than 10 minutes,
  the WebSocket is closed by Cloudflare. Restart the tail process or use a Tail Worker for
  long-running test suites.

- **Account-scoped tail** — the `CF_API_TOKEN` must have the **Workers Tail** permission at
  the account level (not just per-script). An API token with only "Edit Workers" does not
  suffice for `wrangler tail`.

---

## Verification

```bash
# Manually verify tail works with the CI token before adding to workflow
CLOUDFLARE_API_TOKEN=$CF_API_TOKEN \
CLOUDFLARE_ACCOUNT_ID=$CF_ACCOUNT_ID \
  npx wrangler tail api-gateway --format json --env production &
TAIL_PID=$!
curl https://api-gateway.acme-workers.dev/health
sleep 5
kill $TAIL_PID
# Expected: one JSON event line with outcome:"ok"
```

---

## Related

- `github-actions-cloudflare-deploy-workflow.md` — wrangler deploy CI setup
- `github-actions-wrangler-d1-seeding-preview-environment.md` — preview environment seeding
- `github-actions-job-summaries-wrangler-deploy-report.md` — deploy report in job summary
- `github-actions-retry-failed-workers-deploy.md` — deployment retry patterns

---

## Sources

- https://developers.cloudflare.com/workers/observability/logs/logpush/
- https://developers.cloudflare.com/workers/wrangler/commands/#tail
- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/workflow-commands-for-github-actions#adding-a-job-summary
