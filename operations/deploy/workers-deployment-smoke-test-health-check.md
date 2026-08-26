# Post-Deployment Smoke Tests and Health Checks for Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

After `wrangler deploy` exits successfully you have no guarantee that the Worker is actually serving requests correctly. A smoke test suite that immediately hits critical endpoints and validates response shape catches deployment regressions before they reach users, and writing the results to D1 builds an auditable deployment history.

---

## Context

Smoke tests run as a TypeScript script in the CI pipeline immediately after `wrangler deploy`. The script uses the native `fetch` API (Node 20+ built-in) with an `AbortController` timeout to call `/health`, `/api/ping`, and `/api/version` on the freshly deployed Worker. Response shapes are validated with Zod so any schema drift causes an immediate failure. All check results — pass/fail, response time, status code, timestamp — are written to a D1 table named `deployment_checks` for long-term audit and trend analysis. If any check fails the script exits with a non-zero code, which fails the CI job and can trigger the rollback workflow.

---

## Section 1 — Config / wrangler.toml

```toml
name = "api"
main = "src/worker.ts"
compatibility_date = "2026-08-01"

[[d1_databases]]
binding = "DB"
database_name = "deployment-audits"
database_id = "<your-d1-database-id>"

# The smoke-test script accesses D1 via REST API (not binding),
# so only the database_id is needed here for reference.
```

```sql
-- migrations/0001_create_deployment_checks.sql
CREATE TABLE IF NOT EXISTS deployment_checks (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id      TEXT    NOT NULL,
  endpoint    TEXT    NOT NULL,
  passed      INTEGER NOT NULL CHECK (passed IN (0, 1)),
  status_code INTEGER,
  latency_ms  INTEGER,
  error       TEXT,
  checked_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_deployment_checks_run_id
  ON deployment_checks (run_id);
```

---

## Section 2 — Implementation / Smoke Test Script

```typescript
// scripts/smoke-test.ts
// Run: npx tsx scripts/smoke-test.ts https://api.example.com <run-id>
import { z } from "zod";

// ---------------------------------------------------------------------------
// Zod schemas for each endpoint
// ---------------------------------------------------------------------------

const HealthSchema = z.object({
  status: z.literal("ok"),
  version: z.string().optional(),
  timestamp: z.string().datetime({ offset: true }).optional(),
});

const PingSchema = z.object({
  pong: z.boolean(),
});

const VersionSchema = z.object({
  version: z.string().min(1),
  env: z.string().optional(),
});

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CheckResult {
  endpoint: string;
  passed: boolean;
  statusCode?: number;
  latencyMs: number;
  error?: string;
}

interface SmokeConfig {
  baseUrl: string;
  timeoutMs: number;
  runId: string;
  d1AccountId: string;
  d1DatabaseId: string;
  cfApiToken: string;
}

// ---------------------------------------------------------------------------
// Fetch with timeout
// ---------------------------------------------------------------------------

async function fetchWithTimeout(
  url: string,
  timeoutMs: number
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

// ---------------------------------------------------------------------------
// Individual checks
// ---------------------------------------------------------------------------

async function checkEndpoint<T>(
  label: string,
  url: string,
  schema: z.ZodType<T>,
  config: Pick<SmokeConfig, "timeoutMs">
): Promise<CheckResult> {
  const start = Date.now();
  try {
    const res = await fetchWithTimeout(url, config.timeoutMs);
    const latencyMs = Date.now() - start;

    if (!res.ok) {
      return {
        endpoint: label,
        passed: false,
        statusCode: res.status,
        latencyMs,
        error: `HTTP ${res.status} ${res.statusText}`,
      };
    }

    const json: unknown = await res.json();
    const parsed = schema.safeParse(json);

    if (!parsed.success) {
      return {
        endpoint: label,
        passed: false,
        statusCode: res.status,
        latencyMs,
        error: `Schema validation failed: ${parsed.error.message}`,
      };
    }

    return { endpoint: label, passed: true, statusCode: res.status, latencyMs };
  } catch (err) {
    return {
      endpoint: label,
      passed: false,
      latencyMs: Date.now() - start,
      error: err instanceof Error ? err.message : String(err),
    };
  }
}

// ---------------------------------------------------------------------------
// Write results to D1 via REST API
// ---------------------------------------------------------------------------

async function writeResultsToD1(
  results: CheckResult[],
  config: SmokeConfig
): Promise<void> {
  const statements = results.map((r) => ({
    sql: `INSERT INTO deployment_checks
            (run_id, endpoint, passed, status_code, latency_ms, error)
          VALUES (?, ?, ?, ?, ?, ?)`,
    params: [
      config.runId,
      r.endpoint,
      r.passed ? 1 : 0,
      r.statusCode ?? null,
      r.latencyMs,
      r.error ?? null,
    ],
  }));

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${config.d1AccountId}/d1/database/${config.d1DatabaseId}/query`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${config.cfApiToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(statements),
    }
  );

  const json = (await res.json()) as { success: boolean; errors?: unknown[] };
  if (!json.success) {
    console.warn("D1 write failed (non-fatal):", json.errors);
  } else {
    console.log(`Wrote ${results.length} check result(s) to D1 run ${config.runId}`);
  }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  const [, , baseUrl, runId = crypto.randomUUID()] = process.argv;

  if (!baseUrl) {
    console.error("Usage: tsx scripts/smoke-test.ts <baseUrl> [runId]");
    process.exit(1);
  }

  const config: SmokeConfig = {
    baseUrl,
    timeoutMs: 10_000,
    runId,
    d1AccountId: process.env.CF_ACCOUNT_ID ?? "",
    d1DatabaseId: process.env.D1_DATABASE_ID ?? "",
    cfApiToken: process.env.CLOUDFLARE_API_TOKEN ?? "",
  };

  console.log(`\nSmoke test run: ${config.runId}`);
  console.log(`Target:         ${config.baseUrl}\n`);

  const checks: Array<Promise<CheckResult>> = [
    checkEndpoint("GET /health", `${baseUrl}/health`, HealthSchema, config),
    checkEndpoint("GET /api/ping", `${baseUrl}/api/ping`, PingSchema, config),
    checkEndpoint("GET /api/version", `${baseUrl}/api/version`, VersionSchema, config),
  ];

  const results = await Promise.all(checks);

  // Print table
  const colW = 20;
  console.log(
    "Endpoint".padEnd(colW),
    "Pass".padEnd(8),
    "Status".padEnd(8),
    "Latency"
  );
  console.log("-".repeat(colW + 8 + 8 + 10));
  for (const r of results) {
    const icon = r.passed ? "PASS" : "FAIL";
    console.log(
      r.endpoint.padEnd(colW),
      icon.padEnd(8),
      String(r.statusCode ?? "-").padEnd(8),
      `${r.latencyMs} ms`
    );
    if (!r.passed) console.log("  Error:", r.error);
  }

  // Write to D1 (best-effort)
  if (config.d1AccountId && config.d1DatabaseId && config.cfApiToken) {
    await writeResultsToD1(results, config).catch(console.warn);
  }

  const failures = results.filter((r) => !r.passed);
  if (failures.length > 0) {
    console.error(`\n${failures.length} smoke test(s) FAILED. Exiting with code 1.`);
    process.exit(1);
  }

  console.log(`\nAll ${results.length} smoke tests PASSED.`);
}

main().catch((err) => {
  console.error("Unexpected error:", err);
  process.exit(1);
});
```

---

## Section 3 — CI / Automation

```yaml
# .github/workflows/deploy-and-smoke-test.yml
name: Deploy and Smoke Test

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    env:
      CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
      CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
      D1_DATABASE_ID: ${{ secrets.D1_DATABASE_ID }}
      WORKER_URL: ${{ vars.WORKER_URL }}

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - run: npm ci

      - name: Install wrangler + tsx + zod
        run: npm install -g wrangler && npm install --save-dev tsx zod

      - name: Apply D1 migrations
        run: |
          wrangler d1 migrations apply deployment-audits --remote

      - name: Deploy Worker
        id: deploy
        run: |
          wrangler deploy
          echo "run_id=$(git rev-parse --short HEAD)-$(date +%s)" >> $GITHUB_OUTPUT

      - name: Wait for propagation
        run: sleep 5

      - name: Run smoke tests
        env:
          RUN_ID: ${{ steps.deploy.outputs.run_id }}
        run: |
          npx tsx scripts/smoke-test.ts "$WORKER_URL" "$RUN_ID"

      - name: Rollback on smoke-test failure
        if: failure()
        run: |
          echo "Smoke tests failed — rolling back to previous version"
          PREV=$(wrangler versions list --json 2>/dev/null \
            | jq -r '[.result // .][0][1].id // empty')
          if [[ -n "$PREV" ]]; then
            wrangler versions deploy --version-id "$PREV" --percentage 100 --yes
            echo "Rolled back to $PREV"
          else
            echo "No previous version found; manual intervention required"
          fi
          exit 1
```

---

## Anti-patterns

- **Smoke-testing against a staging URL instead of production** — validates the wrong environment; always hit the URL that `wrangler deploy` just updated, which is usually the Worker's production route.
- **Ignoring D1 write failures** — the audit trail should be best-effort but you still want visibility; log the failure as a warning rather than letting it swallow the real test failure.
- **Hardcoding expected response bodies** — response shape changes break tests for the wrong reason; validate structure with Zod rather than exact string equality.
- **Running all smoke tests serially** — adds unnecessary latency to the pipeline; use `Promise.all` so independent endpoint checks run in parallel.

---

## Gotchas

- `fetch` with `AbortController` in Node 20 honours the signal correctly, but in Node 18 there are edge cases around stream cleanup; use Node 20+ in CI.
- The D1 REST API accepts an array of statement objects for batch inserts; sending them one by one is slower and uses more API quota.
- `wrangler d1 migrations apply` requires a local `migrations/` directory with sequentially numbered SQL files; out-of-order files cause the command to error.
- Zod `z.string().datetime({ offset: true })` accepts ISO-8601 strings with a timezone offset; a bare `2026-08-24T12:00:00` (no `Z` or `+00:00`) fails validation — ensure the Worker includes the offset.
- If the Worker takes more than 10 seconds to respond (the `timeoutMs` default), `AbortController` throws `DOMException: The operation was aborted` — surface this clearly in the error column rather than letting the stack trace fill CI logs.

---

## Verification

```bash
# Apply D1 migration locally
wrangler d1 migrations apply deployment-audits --local

# Run smoke tests against local dev server
npx wrangler dev &
DEV_PID=$!
sleep 3
npx tsx scripts/smoke-test.ts http://localhost:8787 local-$(date +%s)
kill $DEV_PID

# Run against production
npx tsx scripts/smoke-test.ts https://api.example.com prod-$(git rev-parse --short HEAD)

# Query D1 audit trail for the last 10 runs
wrangler d1 execute deployment-audits --remote \
  --command "SELECT run_id, endpoint, passed, latency_ms, checked_at \
             FROM deployment_checks ORDER BY id DESC LIMIT 30"

# Count failures by run
wrangler d1 execute deployment-audits --remote \
  --command "SELECT run_id, COUNT(*) AS total, SUM(1-passed) AS failures \
             FROM deployment_checks GROUP BY run_id ORDER BY run_id DESC LIMIT 10"
```

---

## Related

- `workers-rollback-wrangler-versions.md`
- `workers-blue-green-deployment-kv-feature-flags.md`
- `wrangler-deploy-canary-percentage-routing.md`

---

## Sources

- Cloudflare D1 REST API — https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/
- Zod schema validation — https://zod.dev/
- Cloudflare Workers runtime fetch — https://developers.cloudflare.com/workers/runtime-apis/fetch/
- Wrangler D1 migrations — https://developers.cloudflare.com/d1/reference/migrations/
