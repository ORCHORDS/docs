# Workers Version Rollback Automation via Health Check

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Workers deploy passes CI but starts returning elevated error rates or latency spikes within
minutes of going live. On-call engineers must manually identify the bad deploy, look up the
previous `version_id`, run `wrangler versions deploy`, and verify recovery — all while the
incident is active. You need an automated rollback gate that monitors a health endpoint after
each deploy and triggers a version revert without human intervention if thresholds are breached.

---

## Context

Cloudflare Workers' Gradual Deployments (`wrangler versions upload` / `wrangler versions deploy`)
separate bundle upload from traffic assignment. This creates a natural automation hook: after
setting a new version to 100% traffic, a monitoring job can poll a health endpoint and roll
back to the previous version if the new one fails health criteria. The previous `version_id` is
known at deploy time and can be stored as a CI artifact or environment variable for immediate
use by the rollback script.

Complementary tools:
- Cloudflare Workers Analytics Engine — query error rates per `version_id` via GraphQL.
- Cloudflare Tail Workers — real-time log stream for error detection.
- Workers `version_metadata` binding — lets the Worker expose its own `version_id` in health
  responses, making the check self-describing.

---

## 1. Expose version metadata from the Worker health endpoint

```typescript
// src/index.ts  (inside the deployed Worker)
export interface Env {
  VERSION_METADATA: WorkerVersionMetadata;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/_health") {
      const id = env.VERSION_METADATA?.id ?? "unknown";
      const tag = env.VERSION_METADATA?.tag ?? "unknown";

      // Run any internal checks here (DB reachability, KV latency, etc.)
      const healthy = await runInternalChecks(env);

      return Response.json(
        { ok: healthy, version: id, tag },
        { status: healthy ? 200 : 503 }
      );
    }

    return new Response("OK");
  },
} satisfies ExportedHandler<Env>;

async function runInternalChecks(_env: Env): Promise<boolean> {
  // Example: confirm the Worker can reach its D1 binding.
  return true;
}
```

```toml
# wrangler.toml
[version_metadata]
binding = "VERSION_METADATA"
```

---

## 2. Deploy script that captures the previous version ID

```typescript
// scripts/deploy-and-watch.ts
import { execSync } from "node:child_process";

interface VersionListResult {
  result: Array<{ id: string; number: number; percentage: number }>;
}

async function getLiveVersionId(workerName: string): Promise<string | null> {
  const accountId = process.env.CF_ACCOUNT_ID!;
  const token = process.env.CF_API_TOKEN!;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}` +
      `/workers/scripts/${workerName}/versions?per_page=10`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  const body: VersionListResult = await res.json() as VersionListResult;
  return body.result.find((v) => v.percentage === 100)?.id ?? null;
}

async function main(): Promise<void> {
  const workerName = process.env.WORKER_NAME!;

  // 1. Record the current live version before deploying.
  const previousVersionId = await getLiveVersionId(workerName);
  console.log(`Current live version (rollback target): ${previousVersionId}`);

  // 2. Upload the new bundle.
  const uploadRaw = execSync("pnpm wrangler versions upload --json", {
    env: { ...process.env, CLOUDFLARE_API_TOKEN: process.env.CF_API_TOKEN! },
    encoding: "utf-8",
  });
  const { id: newVersionId } = JSON.parse(
    uploadRaw.split("\n").find((l) => l.startsWith("{")) ?? "{}"
  ) as { id: string };
  console.log(`Uploaded new version: ${newVersionId}`);

  // 3. Promote to 100%.
  execSync(
    `pnpm wrangler versions deploy --version-id ${newVersionId} --percentage 100 --yes`,
    { env: { ...process.env, CLOUDFLARE_API_TOKEN: process.env.CF_API_TOKEN! }, stdio: "inherit" }
  );

  // 4. Hand off version IDs to the health-check watcher.
  process.env.NEW_VERSION_ID = newVersionId;
  process.env.PREV_VERSION_ID = previousVersionId ?? "";
}

await main();
```

---

## 3. Health-check polling with automatic rollback

```typescript
// scripts/health-watch-rollback.ts
interface HealthResponse {
  ok: boolean;
  version: string;
  tag: string;
}

interface RollbackConfig {
  healthUrl: string;
  expectedVersionId: string;
  previousVersionId: string | null;
  workerName: string;
  /** How long to monitor after deploy (ms). */
  watchDurationMs: number;
  /** Interval between health polls (ms). */
  pollIntervalMs: number;
  /** Number of consecutive failures before rollback triggers. */
  failureThreshold: number;
}

async function pollHealth(url: string): Promise<HealthResponse> {
  const res = await fetch(url, { signal: AbortSignal.timeout(5_000) });
  if (!res.ok && res.status !== 503) {
    throw new Error(`Health endpoint returned HTTP ${res.status}`);
  }
  return res.json() as Promise<HealthResponse>;
}

async function rollback(cfg: RollbackConfig): Promise<void> {
  if (!cfg.previousVersionId) {
    console.error("No previous version available — cannot auto-rollback.");
    process.exit(1);
  }

  console.warn(`Rolling back to ${cfg.previousVersionId}…`);
  const { execSync } = await import("node:child_process");
  execSync(
    `pnpm wrangler versions deploy --version-id ${cfg.previousVersionId} --percentage 100 --yes`,
    {
      env: { ...process.env, CLOUDFLARE_API_TOKEN: process.env.CF_API_TOKEN! },
      stdio: "inherit",
    }
  );
  console.log("Rollback complete.");
}

async function watchAndRollback(cfg: RollbackConfig): Promise<void> {
  const deadline = Date.now() + cfg.watchDurationMs;
  let consecutiveFailures = 0;

  while (Date.now() < deadline) {
    try {
      const health = await pollHealth(cfg.healthUrl);

      if (health.version !== cfg.expectedVersionId) {
        // Health endpoint is still serving the old version — wait for propagation.
        console.log(`Waiting for version propagation (got ${health.version})…`);
      } else if (!health.ok) {
        consecutiveFailures += 1;
        console.warn(`Health check failed (${consecutiveFailures}/${cfg.failureThreshold}).`);

        if (consecutiveFailures >= cfg.failureThreshold) {
          await rollback(cfg);
          process.exit(1); // Signal failure to CI so the job is marked red.
        }
      } else {
        consecutiveFailures = 0;
        console.log(`Health OK — version ${health.version} serving correctly.`);
      }
    } catch (err) {
      consecutiveFailures += 1;
      console.error(`Poll error (${consecutiveFailures}/${cfg.failureThreshold}):`, err);
      if (consecutiveFailures >= cfg.failureThreshold) {
        await rollback(cfg);
        process.exit(1);
      }
    }

    await new Promise((r) => setTimeout(r, cfg.pollIntervalMs));
  }

  console.log("Watch period elapsed — deploy considered stable.");
}

await watchAndRollback({
  healthUrl:          process.env.HEALTH_URL!,
  expectedVersionId:  process.env.NEW_VERSION_ID!,
  previousVersionId:  process.env.PREV_VERSION_ID || null,
  workerName:         process.env.WORKER_NAME!,
  watchDurationMs:    5 * 60 * 1_000,   // 5 minutes
  pollIntervalMs:     15 * 1_000,        // every 15 s
  failureThreshold:   3,                 // 3 consecutive failures = rollback
});
```

---

## 4. GitHub Actions pipeline wiring

```yaml
jobs:
  deploy-and-watch:
    runs-on: ubuntu-latest
    env:
      CF_API_TOKEN:   ${{ secrets.CF_API_TOKEN }}
      CF_ACCOUNT_ID:  ${{ secrets.CF_ACCOUNT_ID }}
      WORKER_NAME:    my-api-worker
      HEALTH_URL:     https://api.example.com/_health

    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
      - run: pnpm install --frozen-lockfile

      - name: Deploy new version
        run: pnpm tsx scripts/deploy-and-watch.ts

      - name: Watch health & auto-rollback
        run: pnpm tsx scripts/health-watch-rollback.ts
```

---

## 5. Post-rollback Slack notification

```typescript
// scripts/notify-rollback.ts
async function notifySlack(webhookUrl: string, message: string): Promise<void> {
  await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: message,
      blocks: [
        {
          type: "section",
          text: { type: "mrkdwn", text: message },
        },
      ],
    }),
  });
}

const rolledBack = process.exitCode === 1;
if (rolledBack) {
  await notifySlack(
    process.env.SLACK_WEBHOOK_URL!,
    `:rotating_light: *Auto-rollback triggered* for \`${process.env.WORKER_NAME}\`.\n` +
      `New version \`${process.env.NEW_VERSION_ID}\` failed health checks.\n` +
      `Restored to \`${process.env.PREV_VERSION_ID}\`.\n` +
      `Run: ${process.env.GITHUB_SERVER_URL}/${process.env.GITHUB_REPOSITORY}/actions/runs/${process.env.GITHUB_RUN_ID}`
  );
}
```

---

## Anti-patterns

- **Polling from within the Worker itself**: the Worker cannot observe its own aggregate error
  rate. Use an external poller with access to the public health endpoint.
- **Using `wrangler tail` as the failure detector**: tail logs add latency and can miss fast
  error bursts. Dedicated health polling with a tight interval is more reliable.
- **Rolling back without marking the CI job as failed**: if the rollback succeeds but `exit 0`
  is returned, the pipeline shows green and no alert fires. Always `process.exit(1)` after a
  rollback.
- **Infinite watch period**: a 30-minute watch window blocks the pipeline slot and delays the
  next deploy. Five minutes captures most cold-start and cache-warm issues; rely on production
  monitoring for long-tail regressions.

---

## Gotchas

- Workers version propagation across Cloudflare's network can take 30–60 s. The health watcher
  must distinguish "old version still propagating" from "new version failing" by comparing the
  `version` field in the response.
- `AbortSignal.timeout()` requires Node 18+. On Node 16 use `Promise.race` with a manual
  `setTimeout` reject.
- If the Worker has no previous deployed version (first deploy), `previousVersionId` is `null`.
  The rollback script must handle this gracefully and fail the pipeline without attempting a
  revert.

---

## Verification

```bash
# Confirm the health endpoint returns the current version ID
curl https://api.example.com/_health | jq .
# => { "ok": true, "version": "<version_id>", "tag": "v1.2.3" }

# Confirm versions list shows the rollback target
pnpm wrangler versions list --name my-api-worker
```

---

## Related

- `worker-versioning-gradual-rollout.md`
- `wrangler-versions-api-rollback-automation.md`
- `rollback-decision-automation-slo-monitoring.md`
- `deployment-health-gates-automated-rollback.md`
- `workers-version-metadata-binding-deploy-tracking.md`

---

## Sources

- Workers Gradual Deployments: https://developers.cloudflare.com/workers/configuration/versions-and-deployments/gradual-deployments/
- Workers Version Metadata binding: https://developers.cloudflare.com/workers/runtime-apis/bindings/version-metadata/
- Cloudflare Versions API reference: https://developers.cloudflare.com/api/operations/worker-versions-list-versions
