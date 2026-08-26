# Post-Deployment Smoke Tests for Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A Worker deploys successfully — wrangler exits 0 — but the Worker immediately panics on every request due to a missing binding or a startup error. The deploy is technically live but completely broken. You need a post-deploy smoke test suite that catches this class of failure within seconds and triggers an automatic rollback before users notice.

## Context

Cloudflare Workers support a `/cdn-cgi/` health check namespace only for Pages. For Workers, you must implement your own health endpoint. The smoke test suite is a small HTTP test script run as a GitHub Actions step immediately after `wrangler deploy`. If any smoke test fails, the workflow calls `wrangler rollback` to restore the previous version, then notifies the team.

Workers Gradual Deployments (the `wrangler versions` API) let you roll back to a specific deployment version by ID, making rollback deterministic.

## Solution

### Health check endpoint pattern

```typescript
// src/routes/health.ts
export interface HealthStatus {
  status: "ok" | "degraded" | "error";
  version: string;
  checks: Record<string, boolean>;
  latency_ms: Record<string, number>;
  timestamp: string;
}

export async function handleHealth(request: Request, env: Env): Promise<Response> {
  const start = Date.now();
  const checks: Record<string, boolean> = {};
  const latency: Record<string, number> = {};

  // Check KV connectivity
  try {
    const t0 = Date.now();
    await env.CACHE.get("__health_probe");
    latency["kv"] = Date.now() - t0;
    checks["kv"] = true;
  } catch {
    checks["kv"] = false;
    latency["kv"] = -1;
  }

  // Check D1 connectivity
  try {
    const t0 = Date.now();
    await env.DB.prepare("SELECT 1").run();
    latency["d1"] = Date.now() - t0;
    checks["d1"] = true;
  } catch {
    checks["d1"] = false;
    latency["d1"] = -1;
  }

  // Check a required secret is present (value, not content)
  checks["secrets"] = Boolean(env.API_SECRET && env.API_SECRET.length > 0);

  const allOk = Object.values(checks).every(Boolean);
  const status: HealthStatus = {
    status: allOk ? "ok" : "error",
    version: env.APP_VERSION ?? "unknown",
    checks,
    latency_ms: latency,
    timestamp: new Date().toISOString(),
  };

  return new Response(JSON.stringify(status, null, 2), {
    status: allOk ? 200 : 503,
    headers: { "Content-Type": "application/json" },
  });
}
```

```typescript
// src/index.ts — wire into the router
import { handleHealth } from "./routes/health";

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/healthz") {
      return handleHealth(request, env);
    }

    // ... rest of routing ...
    return new Response("Not Found", { status: 404 });
  },
};
```

### Critical-path smoke test suite

```typescript
// tests/smoke/suite.ts
interface SmokeTest {
  name: string;
  run: (baseUrl: string) => Promise<void>;
}

const tests: SmokeTest[] = [
  {
    name: "health endpoint returns 200",
    async run(base) {
      const res = await fetch(`${base}/healthz`);
      if (res.status !== 200) throw new Error(`Expected 200, got ${res.status}`);
      const body = (await res.json()) as { status: string };
      if (body.status !== "ok") throw new Error(`Health status: ${body.status}`);
    },
  },
  {
    name: "auth rejects missing token",
    async run(base) {
      const res = await fetch(`${base}/api/v1/products`);
      if (res.status !== 401) throw new Error(`Expected 401, got ${res.status}`);
    },
  },
  {
    name: "products list returns array",
    async run(base) {
      const res = await fetch(`${base}/api/v1/products`, {
        headers: { Authorization: `Bearer ${process.env.SMOKE_TEST_TOKEN}` },
      });
      if (res.status !== 200) throw new Error(`Expected 200, got ${res.status}`);
      const body = (await res.json()) as unknown;
      if (!Array.isArray(body)) throw new Error("Expected array response");
    },
  },
  {
    name: "404 for unknown route",
    async run(base) {
      const res = await fetch(`${base}/does-not-exist-${Date.now()}`);
      if (res.status !== 404) throw new Error(`Expected 404, got ${res.status}`);
    },
  },
  {
    name: "response time under 500ms",
    async run(base) {
      const t0 = Date.now();
      await fetch(`${base}/healthz`);
      const elapsed = Date.now() - t0;
      if (elapsed > 500) throw new Error(`Response took ${elapsed}ms, expected <500ms`);
    },
  },
];

export async function runSmokeSuite(baseUrl: string): Promise<void> {
  const results: { name: string; passed: boolean; error?: string }[] = [];

  for (const test of tests) {
    try {
      await test.run(baseUrl);
      results.push({ name: test.name, passed: true });
      console.log(`  PASS  ${test.name}`);
    } catch (err) {
      const error = err instanceof Error ? err.message : String(err);
      results.push({ name: test.name, passed: false, error });
      console.error(`  FAIL  ${test.name}: ${error}`);
    }
  }

  const failures = results.filter((r) => !r.passed);
  if (failures.length > 0) {
    throw new Error(`${failures.length} smoke test(s) failed`);
  }

  console.log(`\nAll ${tests.length} smoke tests passed.`);
}
```

### Rollback on smoke failure

```typescript
// scripts/post-deploy.ts
import { execSync } from "child_process";
import { runSmokeSuite } from "../tests/smoke/suite";

const BASE_URL = process.env.DEPLOY_BASE_URL!;
const ENV = process.env.WRANGLER_ENV ?? "production";
const NOTIFY_WEBHOOK = process.env.NOTIFY_WEBHOOK_URL;

async function notify(message: string, success: boolean): Promise<void> {
  if (!NOTIFY_WEBHOOK) return;
  await fetch(NOTIFY_WEBHOOK, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: message,
      color: success ? "good" : "danger",
    }),
  });
}

async function main(): Promise<void> {
  console.log(`Running smoke tests against ${BASE_URL}...`);

  try {
    await runSmokeSuite(BASE_URL);
    await notify(`Deploy to ${ENV} succeeded. All smoke tests passed.`, true);
    console.log("Deploy verified.");
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error(`Smoke tests failed: ${message}`);
    console.log("Initiating rollback...");

    try {
      execSync(`npx wrangler rollback --env ${ENV} --message "Auto-rollback: smoke test failure"`, {
        stdio: "inherit",
        env: {
          ...process.env,
          CLOUDFLARE_API_TOKEN: process.env.CF_API_TOKEN,
          CLOUDFLARE_ACCOUNT_ID: process.env.CF_ACCOUNT_ID,
        },
      });
      await notify(
        `Deploy to ${ENV} FAILED smoke tests. Automatic rollback completed.\nError: ${message}`,
        false
      );
    } catch (rollbackErr) {
      await notify(
        `Deploy to ${ENV} FAILED smoke tests AND rollback failed. MANUAL INTERVENTION REQUIRED.\nSmoke error: ${message}`,
        false
      );
      throw rollbackErr;
    }

    process.exit(1);
  }
}

main();
```

### GitHub Actions integration

```yaml
# .github/workflows/deploy-and-verify.yml
name: Deploy and Verify

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    outputs:
      deploy_url: ${{ steps.deploy.outputs.url }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "22" }
      - run: npm ci

      - name: Deploy to production
        id: deploy
        run: |
          OUTPUT=$(npx wrangler deploy --env production 2>&1)
          echo "$OUTPUT"
          # Extract the deploy URL from wrangler output
          URL=$(echo "$OUTPUT" | grep -oE 'https://[a-zA-Z0-9._-]+\.workers\.dev')
          echo "url=${URL:-https://api.example.com}" >> $GITHUB_OUTPUT
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Run smoke tests and auto-rollback on failure
        run: npx ts-node scripts/post-deploy.ts
        env:
          DEPLOY_BASE_URL: ${{ steps.deploy.outputs.url }}
          WRANGLER_ENV: production
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          SMOKE_TEST_TOKEN: ${{ secrets.SMOKE_TEST_TOKEN }}
          NOTIFY_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
```

## Implementation Details

- The `SMOKE_TEST_TOKEN` is a long-lived, read-only API token seeded in each environment's secrets specifically for smoke tests. It never touches production write paths.
- `wrangler rollback` without `--deployment-id` rolls back to the immediately previous deployment. For deterministic rollback, capture the current deployment ID before deploying: `wrangler deployments list --env production --json | jq -r '.[0].id'`.
- The health endpoint's D1 `SELECT 1` probe adds a small D1 read unit cost. For cost-sensitive deployments, wrap the D1 check in a conditional that only runs when `request.headers.get('X-Health-Probe') === '1'`.
- Add a `Retry-After` header on 503 responses so load balancers and CDN edge probes back off cleanly during a degraded state.

## Anti-patterns

- **Smoke testing only the home page**: A 200 on `/` does not mean bindings are working. Always test an endpoint that exercises KV, D1, or R2.
- **Long smoke test suites**: A smoke suite should complete in under 30 seconds. Full integration tests belong in the pre-deploy gate, not post-deploy verification.
- **Silently swallowing rollback errors**: If `wrangler rollback` fails, the system is in an unknown state. Always surface this as a critical alert.
- **Not testing auth rejection**: A broken auth middleware that returns 200 for unauthenticated requests is a security regression. Include a 401 assertion.

## Gotchas

- `wrangler rollback` is only available for Workers deployed via `wrangler deploy` (not via the REST API directly). Verify your pipeline uses wrangler.
- A newly created Worker version takes 5–30 seconds to propagate globally. Add a 15-second wait after `wrangler deploy` before running smoke tests to avoid testing against the previous version.
- KV eventual consistency means a `GET` probe to KV immediately after a `PUT` by the health endpoint can return `null`. Do not write to KV in the health probe; only read a pre-seeded sentinel key.
- Workers that crash at startup (import-time errors, WASM init failures) return 1101 errors, not 500s. Your smoke test assertions should treat any non-2xx as a failure regardless of specific code.

## Verification

```bash
# Run smoke suite locally against the dev environment
DEPLOY_BASE_URL=https://dev-api.example.com \
SMOKE_TEST_TOKEN=<token> \
  npx ts-node tests/smoke/suite.ts

# List last 5 deployments to confirm rollback target
npx wrangler deployments list --env production

# Manually trigger a rollback to a specific version
npx wrangler rollback --deployment-id <id> --env production
```

## Related

- `workers-environment-promotion-pipeline.md`
- `workers-gradual-traffic-migration-routes.md`
- `workers-zero-downtime-d1-migration-deploy.md`

## Sources

- https://developers.cloudflare.com/workers/wrangler/commands/#rollback
- https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
- https://developers.cloudflare.com/d1/platform/client-api/
- https://developers.cloudflare.com/workers/observability/errors/
