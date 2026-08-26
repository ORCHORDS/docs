# Workers Multi-Region Deployment Coordination with Durable Objects

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Two edge Workers running in different Cloudflare regions both attempt to
process the same job queue entry during a rolling deployment because one region
received the new Worker version while the other still runs the previous
version. The old version does not recognise the new job schema field, causing
partial processing and a corrupted record in D1. A Durable Object acting as a
deployment coordinator prevents concurrent processing across versions.

## Context

Cloudflare Workers run at the edge in 300+ PoPs worldwide. When a new version
is deployed with `wrangler versions deploy --percentage N`, different regions
may briefly run different versions simultaneously. For stateless HTTP handlers
this is acceptable, but for Workers that mutate shared D1 databases, process
queues, or coordinate real-time sessions the version skew window introduces
race conditions. Durable Objects provide a single-writer, location-pinned actor
that can enforce deployment fences: the DO holds the "current allowed version"
and refuses requests from Workers running an older version, effectively draining
the old version before proceeding.

## Deployment Fence Durable Object

```typescript
// src/deployment-fence.ts
export interface FenceState {
  currentVersion: string;
  lockedAt: string;
  drainDeadlineMs: number;
}

export class DeploymentFence implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "POST" && url.pathname === "/promote") {
      // Called by CI after wrangler versions deploy completes
      const body = await request.json<{ version: string; drainSeconds: number }>();
      const fence: FenceState = {
        currentVersion: body.version,
        lockedAt: new Date().toISOString(),
        drainDeadlineMs: Date.now() + body.drainSeconds * 1000,
      };
      await this.state.storage.put("fence", fence);
      return Response.json({ ok: true, fence });
    }

    if (request.method === "GET" && url.pathname === "/check") {
      const callerVersion = request.headers.get("X-Worker-Version") ?? "";
      const fence = await this.state.storage.get<FenceState>("fence");

      if (!fence) {
        // No fence set — allow all versions
        return Response.json({ allowed: true });
      }

      if (callerVersion !== fence.currentVersion) {
        const drainRemaining = fence.drainDeadlineMs - Date.now();
        if (drainRemaining > 0) {
          // Old version: drain window still open — reject with retry
          return Response.json(
            {
              allowed: false,
              reason: "version_skew",
              retryAfterMs: Math.min(drainRemaining, 5000),
            },
            { status: 409 }
          );
        }
        // Drain window expired — old version should not be running; log anomaly
        console.error(
          `Anomalous old version ${callerVersion} after drain deadline`
        );
      }

      return Response.json({ allowed: true });
    }

    return new Response("Not found", { status: 404 });
  }
}
```

## Worker Integration — Checking the Fence Before Mutations

```typescript
// src/index.ts
import { DeploymentFence } from "./deployment-fence";
export { DeploymentFence };

const WORKER_VERSION = "__WORKER_VERSION__"; // replaced at build time by wrangler

export default {
  async queue(
    batch: MessageBatch,
    env: Env,
    ctx: ExecutionContext
  ): Promise<void> {
    // Obtain the singleton deployment fence DO
    const fenceId = env.DEPLOYMENT_FENCE.idFromName("global");
    const fence = env.DEPLOYMENT_FENCE.get(fenceId);

    const check = await fence.fetch(
      new Request("https://fence/check", {
        method: "GET",
        headers: { "X-Worker-Version": WORKER_VERSION },
      })
    );

    if (!check.ok) {
      const body = await check.json<{ retryAfterMs: number }>();
      // Re-queue messages for retry after drain window passes
      batch.retryAll({ delaySeconds: Math.ceil(body.retryAfterMs / 1000) });
      return;
    }

    // Fence passed — process messages with current schema
    for (const message of batch.messages) {
      await processMessage(message.body as JobPayload, env);
      message.ack();
    }
  },
};

interface JobPayload {
  jobId: string;
  version: number;
  data: unknown;
}

async function processMessage(payload: JobPayload, env: Env) {
  await env.DB.prepare(
    "INSERT INTO job_results (job_id, result) VALUES (?, ?)"
  )
    .bind(payload.jobId, JSON.stringify(payload.data))
    .run();
}

interface Env {
  DB: D1Database;
  DEPLOYMENT_FENCE: DurableObjectNamespace;
}
```

## CI Pipeline — Promoting Version Through the Fence

```yaml
# .github/workflows/deploy-coordinated.yml
name: Coordinated Workers Deploy
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "22" }
      - run: npm ci

      - name: Inject version into build
        run: |
          VERSION="$(git rev-parse --short HEAD)"
          sed -i "s/__WORKER_VERSION__/$VERSION/" src/index.ts

      - name: Upload new version (no traffic)
        id: upload
        run: |
          VERSION_ID=$(npx wrangler versions upload --env production \
            --message "$(git rev-parse --short HEAD)" \
            | grep "Version ID" | awk '{print $NF}')
          echo "version_id=$VERSION_ID" >> "$GITHUB_OUTPUT"
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}

      - name: Promote fence to new version (90 s drain)
        run: |
          npx tsx scripts/promote-fence.ts \
            "${{ steps.upload.outputs.version_id }}" \
            90
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

      - name: Shift traffic to new version
        run: |
          npx wrangler versions deploy \
            --version-id "${{ steps.upload.outputs.version_id }}" \
            --percentage 100 \
            --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
```

```typescript
// scripts/promote-fence.ts  — called from CI
const [versionId, drainSecondsStr] = process.argv.slice(2);
const drainSeconds = parseInt(drainSecondsStr ?? "60", 10);

// Call the Durable Object via the Workers REST invocation endpoint
const workerUrl = `https://api-worker.orchords-production.workers.dev/fence/promote`;
const res = await fetch(workerUrl, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ version: versionId, drainSeconds }),
});
if (!res.ok) throw new Error(`Fence promote failed: ${await res.text()}`);
console.log("Fence promoted:", await res.json());
```

## Anti-patterns

- Pinning the Durable Object to a specific Cloudflare region using
  `locationHint` for deployment coordination; the hint is not guaranteed
  and the DO must be globally reachable in all cases.
- Using a KV key instead of a Durable Object for the fence; KV has
  eventual consistency with up to 60 s propagation delay, making it
  unsuitable as a strong coordination primitive.
- Setting a drain deadline shorter than the maximum in-flight request
  duration for the queue consumer; 90 seconds is a safe minimum for
  Workers queue consumers with 30 s visibility timeout.

## Gotchas

- Durable Object storage is strongly consistent within the DO but the
  fence check itself adds one round-trip to every queue message; cache
  the check result in the isolate's memory for 10 s to reduce latency.
- `wrangler versions deploy` does not wait for old isolates to terminate;
  some regions may continue serving the old version for up to 30 seconds
  after the traffic split changes. The drain deadline must account for this.

## Verification

```bash
# Check the current fence state
curl -s https://api-worker.orchords-production.workers.dev/fence/check \
  -H "X-Worker-Version: abc1234"

# List active Workers versions and their traffic percentages
curl -s -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/workers/deployments/by-script/api-worker" \
  | jq '.result.deployments[0].versions'
```

## Related

- `deploy/durable-objects-namespace-migration-zero-downtime.md`
- `deploy/canary-workers-gradual-traffic-split.md`
- `deploy/worker-versioning-gradual-rollout.md`
- `deploy/multi-region-deployment.md`

## Sources

- https://developers.cloudflare.com/durable-objects/best-practices/access-durable-objects-from-a-worker/
- https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
- https://developers.cloudflare.com/queues/reference/consumer-concurrency/
