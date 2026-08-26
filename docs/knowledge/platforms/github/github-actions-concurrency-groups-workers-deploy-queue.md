# GitHub Actions – Concurrency Groups as a Workers Deploy Queue

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Multiple pushes to `main` in quick succession result in concurrent Workers deployments
that race on Durable Object migrations, D1 schema migrations, or KV configuration writes.
A deployment started from an older commit can overtake and overwrite one from a newer
commit if the build time varies. You need a mechanism that (1) ensures only one deploy
runs at a time per environment, (2) always lets the newest queued job win, and (3) does
not permanently block the queue if a deploy job fails — without introducing an external
queue service.

## Context

GitHub Actions `concurrency.group` serializes workflow runs that share a group key. When
`cancel-in-progress: false`, a second run waits in queue behind the running one; when
`cancel-in-progress: true`, the running job is cancelled and the newest takes its place.
For deployments, the correct behaviour is `cancel-in-progress: false` on the queue wait
itself but `cancel-in-progress: true` for pre-deploy jobs (build, test) to avoid wasting
runner minutes. This article shows a two-stage pattern: an outer concurrency group for
the queue and an inner cancel policy for the build phase, combined with a Cloudflare
Worker that tracks deploy ordering to detect and alert on out-of-order completions.

## 1. Two-Stage Concurrency Policy

```yaml
# .github/workflows/workers-deploy.yml
name: Workers Deploy

on:
  push:
    branches: [main]

jobs:
  # Stage 1: Build — cancel superseded build jobs immediately
  build:
    runs-on: ubuntu-latest
    concurrency:
      group: workers-build-${{ github.ref }}
      cancel-in-progress: true
    outputs:
      sha: ${{ github.sha }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
      - run: npm ci
      - run: npm test
      - run: npm run build
      - uses: actions/upload-artifact@v4
        with:
          name: worker-dist-${{ github.sha }}
          path: dist/
          retention-days: 1

  # Stage 2: Deploy — queue, never cancel; newest commit deploys in order
  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment: production
    concurrency:
      group: workers-deploy-production
      cancel-in-progress: false
    steps:
      - uses: actions/checkout@v4

      - uses: actions/download-artifact@v4
        with:
          name: worker-dist-${{ github.sha }}
          path: dist/

      - name: Register deploy start with ordering Worker
        id: register
        run: |
          RESPONSE=$(curl -s -X POST "${{ vars.DEPLOY_TRACKER_URL }}/register" \
            -H "Authorization: Bearer ${{ secrets.DEPLOY_TRACKER_TOKEN }}" \
            -H "Content-Type: application/json" \
            -d "{
              \"sha\": \"${{ github.sha }}\",
              \"run_id\": \"${{ github.run_id }}\",
              \"run_number\": ${{ github.run_number }},
              \"environment\": \"production\"
            }")
          echo "sequence=$(echo $RESPONSE | jq -r .sequence)" >> "$GITHUB_OUTPUT"

      - name: Deploy Worker
        run: |
          npx wrangler@3 deploy dist/index.js \
            --name my-worker \
            --compatibility-date 2026-06-01
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_DEPLOY_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ vars.CF_ACCOUNT_ID }}

      - name: Mark deploy complete
        if: always()
        run: |
          STATUS="${{ job.status }}"
          curl -s -X POST "${{ vars.DEPLOY_TRACKER_URL }}/complete" \
            -H "Authorization: Bearer ${{ secrets.DEPLOY_TRACKER_TOKEN }}" \
            -H "Content-Type: application/json" \
            -d "{
              \"sha\": \"${{ github.sha }}\",
              \"run_id\": \"${{ github.run_id }}\",
              \"sequence\": ${{ steps.register.outputs.sequence }},
              \"status\": \"$STATUS\"
            }"
```

## 2. Deploy Ordering Tracker – Durable Object

```typescript
// src/deploy-tracker/tracker.ts
import { DurableObject } from "cloudflare:workers";

interface DeployRecord {
  sha: string;
  runId: string;
  runNumber: number;
  sequence: number;
  startedAt: number;
  completedAt?: number;
  status?: "success" | "failure" | "cancelled";
}

export class DeployTracker extends DurableObject {
  private sequence: number = 0;
  private records: Map<string, DeployRecord> = new Map();

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "POST" && url.pathname === "/register") {
      return this.handleRegister(request);
    }
    if (request.method === "POST" && url.pathname === "/complete") {
      return this.handleComplete(request);
    }
    if (request.method === "GET" && url.pathname === "/history") {
      return this.handleHistory();
    }

    return new Response("Not Found", { status: 404 });
  }

  private async handleRegister(request: Request): Promise<Response> {
    const body = await request.json<{
      sha: string;
      runId: string;
      runNumber: number;
      environment: string;
    }>();

    this.sequence += 1;
    const record: DeployRecord = {
      sha: body.sha,
      runId: body.runId,
      runNumber: body.runNumber,
      sequence: this.sequence,
      startedAt: Date.now(),
    };
    this.records.set(body.runId, record);

    // Persist state across requests
    await this.ctx.storage.put("sequence", this.sequence);
    await this.ctx.storage.put(`record:${body.runId}`, record);

    return Response.json({ sequence: this.sequence, registered: true });
  }

  private async handleComplete(request: Request): Promise<Response> {
    const body = await request.json<{
      sha: string;
      runId: string;
      sequence: number;
      status: string;
    }>();

    const record = this.records.get(body.runId)
      ?? await this.ctx.storage.get<DeployRecord>(`record:${body.runId}`);

    if (!record) {
      return new Response("Deploy record not found", { status: 404 });
    }

    record.completedAt = Date.now();
    record.status = body.status as DeployRecord["status"];
    await this.ctx.storage.put(`record:${body.runId}`, record);
    this.records.set(body.runId, record);

    // Detect out-of-order: a lower sequence number completing after a higher one
    const outOfOrder = await this.detectOutOfOrder(record);

    return Response.json({ ok: true, outOfOrder });
  }

  private async detectOutOfOrder(completed: DeployRecord): Promise<boolean> {
    // Find the highest sequence that completed successfully before this one
    const allKeys = await this.ctx.storage.list<DeployRecord>({
      prefix: "record:",
    });
    let maxCompletedSequence = 0;
    for (const [, rec] of allKeys) {
      if (
        rec.status === "success" &&
        rec.completedAt &&
        rec.completedAt < (completed.completedAt ?? 0)
      ) {
        maxCompletedSequence = Math.max(maxCompletedSequence, rec.sequence);
      }
    }
    return completed.sequence < maxCompletedSequence;
  }

  private async handleHistory(): Promise<Response> {
    const allRecords = await this.ctx.storage.list<DeployRecord>({
      prefix: "record:",
    });
    const records = Array.from(allRecords.values()).sort(
      (a, b) => b.sequence - a.sequence
    );
    return Response.json({ records: records.slice(0, 20) });
  }
}
```

## 3. Worker Router and Auth

```typescript
// src/deploy-tracker/index.ts
import { DeployTracker } from "./tracker.ts";
export { DeployTracker };

interface Env {
  DEPLOY_TRACKER: DurableObjectNamespace;
  DEPLOY_TRACKER_TOKEN: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Validate bearer token
    const auth = request.headers.get("Authorization");
    if (auth !== `Bearer ${env.DEPLOY_TRACKER_TOKEN}`) {
      return new Response("Unauthorized", { status: 401 });
    }

    const url = new URL(request.url);
    // Route all requests to a single named Durable Object per environment
    const environment = url.searchParams.get("environment") ?? "production";
    const id = env.DEPLOY_TRACKER.idFromName(`deploy-tracker-${environment}`);
    const stub = env.DEPLOY_TRACKER.get(id);

    return stub.fetch(request);
  },
};
```

```toml
# wrangler.toml for the tracker Worker
name = "deploy-tracker"
compatibility_date = "2026-06-01"

[[durable_objects.bindings]]
name = "DEPLOY_TRACKER"
class_name = "DeployTracker"

[[migrations]]
tag = "v1"
new_classes = ["DeployTracker"]
```

## 4. Handling Queue Drain After Failure

```yaml
# .github/workflows/workers-deploy.yml (continued)
      - name: Alert on deploy failure
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            // On failure, the concurrency group releases and the next queued run proceeds.
            // Create an issue to track the broken deploy for human review.
            await github.rest.issues.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              title: `Deploy failure on ${context.sha.slice(0, 7)} — queue may proceed to next commit`,
              body: [
                `**Run**: #${{ github.run_number }}`,
                `**SHA**: \`${{ github.sha }}\``,
                `**Time**: ${new Date().toISOString()}`,
                '',
                'The deploy queue will continue with the next queued commit. Verify production state before merging further changes.',
              ].join('\n'),
              labels: ['deploy-failure'],
            });
```

## Anti-patterns

- **Using `cancel-in-progress: true` on the deploy job.** A cancelled deploy can leave
  the Worker in a partially uploaded state. Only cancel the build stage; always let a
  started deploy finish (succeed or fail explicitly).
- **Sharing a concurrency group key between staging and production.** A production
  deploy blocks all staging deploys (and vice versa). Use separate group keys per
  environment: `workers-deploy-production`, `workers-deploy-staging`.
- **Not registering the deploy sequence before the deploy step.** If the deploy step
  succeeds but the registration call comes after, a failed registration silently drops
  the record and makes the history incomplete.
- **Using `github.run_number` as a global ordering mechanism.** Run numbers reset on
  workflow re-runs and are scoped to the workflow file, not globally across the repo.
  Use the Durable Object's auto-incremented sequence instead.

## Gotchas

- `cancel-in-progress: false` means a workflow run waits in the queue for up to 6 hours
  before timing out. If builds take 5 minutes and 100 pushes arrive, the 100th run
  waits up to 8+ hours. Add a `timeout-minutes` on the deploy job to bound queue depth.
- GitHub evaluates `concurrency.group` at workflow start, not at job start. Putting
  `concurrency` at job level vs workflow level has different queue semantics — job-level
  concurrency only blocks that specific job, not the whole run.
- Durable Objects require a paid Workers plan. For small teams, a simpler alternative is
  a KV key acting as a lock with TTL, but it lacks the ordering guarantees of a DO.

## Verification

```bash
# Check active and queued workflow runs
gh run list --workflow workers-deploy.yml --status in_progress
gh run list --workflow workers-deploy.yml --status queued

# Query deploy history from the tracker
curl -H "Authorization: Bearer $DEPLOY_TRACKER_TOKEN" \
  "https://deploy-tracker.your-domain.workers.dev/history?environment=production" \
  | jq '.records[:5]'
```

## Related

- `github-actions-concurrency-groups.md`
- `github-actions-concurrency.md`
- `github-actions-durable-objects-migration-gate.md`
- `github-actions-retry-failed-workers-deploy.md`
- `github-actions-deployment-gates.md`

## Sources

- GitHub Actions – Using concurrency: https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/control-the-concurrency-of-workflows-and-jobs
- Cloudflare Durable Objects – Storage API: https://developers.cloudflare.com/durable-objects/api/storage-api/
- Wrangler Durable Objects configuration: https://developers.cloudflare.com/durable-objects/get-started/
