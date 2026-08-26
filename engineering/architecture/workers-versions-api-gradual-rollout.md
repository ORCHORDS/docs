# Cloudflare Workers Versions API: Gradual Rollout and Traffic Splitting

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

You need to ship a breaking change to a high-traffic Cloudflare Worker — a new request parsing algorithm, a changed response schema, or a migrated dependency — but you cannot afford a hard cut-over. A full blue-green swap means 100% of traffic switches at once, which collapses your error budget if the new version has a latency regression or bug. You need the ability to send 1% of production traffic to the new version, watch metrics for 10 minutes, then increment to 10% → 50% → 100%, with instant rollback to the stable version if error rates spike.

Cloudflare's **Workers Versions API** (and its companion **Worker Deployments API**) provides exactly this mechanism: deploy an immutable Worker version, then control the traffic percentage routed to it independently of the deploy.

---

## Context

Prior to the Versions API, every `wrangler deploy` replaced the active Worker script atomically. There was no API to say "run version A for 90% of requests and version B for 10%." The Versions API decouples two concerns:

- **Version**: an immutable, uploadable snapshot of a Worker's code and bindings (identified by a `version_id` UUID).
- **Deployment**: a traffic-split rule applied to a Worker's route, referencing one or more versions with percentage weights.

A Worker can have at most two versions active in a single deployment (A + B). Splitting is stable per-request (not per-session), using a consistent hash of the request, so a given visitor does not flip between versions mid-session.

Key API surface:
- `PUT /accounts/{account_id}/workers/scripts/{script_name}/versions` — upload a new version
- `GET /accounts/{account_id}/workers/scripts/{script_name}/versions` — list versions
- `POST /accounts/{account_id}/workers/scripts/{script_name}/deployments` — create or update a deployment (traffic split)
- `GET /accounts/{account_id}/workers/scripts/{script_name}/deployments` — list active deployment

---

## Section 1: Uploading a New Version Without Deploying It

A version upload does NOT affect live traffic. It is purely a staging operation.

```typescript
// upload-version.ts — run from CI after build
async function uploadWorkerVersion(
  accountId: string,
  scriptName: string,
  workerBundle: Blob,       // compiled .js or module bundle
  bindings: WorkerBinding[],
  apiToken: string
): Promise<{ versionId: string }> {
  const formData = new FormData();

  formData.append('worker.js', workerBundle, 'worker.js');
  formData.append(
    'metadata',
    JSON.stringify({
      main_module: 'worker.js',
      bindings,
      compatibility_date: '2026-08-01',
    }),
    'metadata.json'
  );

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/workers/scripts/${scriptName}/versions`,
    {
      method:  'PUT',
      headers: { Authorization: `Bearer ${apiToken}` },
      body:    formData,
    }
  );

  if (!resp.ok) throw new Error(`Upload failed: ${await resp.text()}`);
  const { result } = await resp.json<{ result: { id: string } }>();
  return { versionId: result.id };
}
```

The returned `versionId` is a UUID. Store it in CI artifact metadata so the deployment step can reference it.

---

## Section 2: Creating a Traffic-Split Deployment

Once the new version is uploaded and smoke-tested (e.g., by invoking it directly via its version URL), create a deployment that assigns a small percentage to it:

```typescript
// create-deployment.ts
interface VersionWeight {
  version_id: string;
  percentage: number;
}

async function setDeployment(
  accountId: string,
  scriptName: string,
  versions: VersionWeight[],
  apiToken: string
): Promise<void> {
  // Weights must sum to 100
  const total = versions.reduce((sum, v) => sum + v.percentage, 0);
  if (total !== 100) throw new Error(`Weights must sum to 100, got ${total}`);

  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/workers/scripts/${scriptName}/deployments`,
    {
      method:  'POST',
      headers: {
        Authorization: `Bearer ${apiToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        strategy: 'percentage',
        versions,
      }),
    }
  );

  if (!resp.ok) throw new Error(`Deployment failed: ${await resp.text()}`);
}

// Usage: start with 1% canary
await setDeployment(accountId, 'my-api', [
  { version_id: STABLE_VERSION_ID,  percentage: 99 },
  { version_id: CANARY_VERSION_ID,  percentage: 1  },
], apiToken);
```

---

## Section 3: Progressive Promotion Script

Automate the promotion ladder with health checks between each step:

```typescript
// progressive-rollout.ts
const PROMOTION_LADDER = [1, 5, 10, 25, 50, 100]; // percentages

interface HealthCheck {
  errorRate: number;    // fraction, 0–1
  p95LatencyMs: number;
}

async function fetchHealthMetrics(workerName: string): Promise<HealthCheck> {
  // Query Cloudflare Workers Analytics via GraphQL
  const query = `
    {
      viewer {
        accounts(filter: { accountTag: "${ACCOUNT_TAG}" }) {
          workersInvocationsAdaptive(
            limit: 10000
            filter: { scriptName: "${workerName}", datetimeHour_geq: "${new Date(Date.now() - 300_000).toISOString()}" }
            orderBy: [datetimeHour_ASC]
          ) {
            sum { errors requests }
            quantiles { requestsDurationMillisecondsP95 }
          }
        }
      }
    }
  `;
  // ... execute query and parse
  return { errorRate: 0, p95LatencyMs: 0 }; // placeholder
}

async function progressiveRollout(
  accountId: string,
  scriptName: string,
  stableVersionId: string,
  canaryVersionId: string,
  apiToken: string
): Promise<'promoted' | 'rolled-back'> {
  for (const pct of PROMOTION_LADDER) {
    console.log(`Setting canary to ${pct}%`);
    await setDeployment(accountId, scriptName, [
      { version_id: stableVersionId, percentage: 100 - pct },
      { version_id: canaryVersionId, percentage: pct },
    ], apiToken);

    if (pct === 100) break;

    // Wait for metrics to stabilise — 5 minutes per step
    await new Promise(r => setTimeout(r, 5 * 60 * 1000));

    const health = await fetchHealthMetrics(scriptName);
    if (health.errorRate > 0.01 || health.p95LatencyMs > 500) {
      console.error(`Health check failed at ${pct}% — rolling back`);
      await setDeployment(accountId, scriptName, [
        { version_id: stableVersionId, percentage: 100 },
      ], apiToken);
      return 'rolled-back';
    }
  }

  return 'promoted';
}
```

---

## Section 4: Instant Rollback

Rollback is a deployment update setting the stable version to 100%. Because both versions are already uploaded and cached at the edge, this takes effect within seconds — no code upload required:

```typescript
async function rollback(
  accountId: string,
  scriptName: string,
  stableVersionId: string,
  apiToken: string
): Promise<void> {
  await setDeployment(accountId, scriptName, [
    { version_id: stableVersionId, percentage: 100 },
  ], apiToken);
  console.log(`Rolled back ${scriptName} to version ${stableVersionId}`);
}
```

Wire this to an on-call alert handler: when PagerDuty or Grafana fires a `high_error_rate` alert, the SRE (or an automated runbook) calls `rollback()` before opening the postmortem.

---

## Section 5: Version Pinning for Durable Objects

Durable Objects add a complication: the DO class is bound to a specific Worker version. A traffic split can result in a DO being called by both versions simultaneously if a WebSocket or long-lived connection bridges a deploy boundary. Strategies:

```typescript
// versioned-do-migration.ts
// Option A: New DO class per major version (class rename)
// wrangler.toml:
// [[durable_objects.bindings]]
// name       = "ORDER_DO_V2"          ← new binding name for new class
// class_name = "OrderDO_V2"
//
// [[migrations]]
// tag = "v2"
// renamed_classes = [{ from = "OrderDO", to = "OrderDO_V2" }]

// Option B: Schema version field in DO storage
export class OrderDO extends DurableObject {
  async fetch(request: Request): Promise<Response> {
    const schemaVersion = await this.ctx.storage.get<number>('__schemaVersion') ?? 1;

    if (schemaVersion < 2) {
      await this.migrate_v1_to_v2();
      await this.ctx.storage.put('__schemaVersion', 2);
    }
    // ... handle request
  }

  private async migrate_v1_to_v2(): Promise<void> {
    const legacyField = await this.ctx.storage.get<string>('old_field');
    if (legacyField) {
      await this.ctx.storage.put('new_field', legacyField);
      await this.ctx.storage.delete('old_field');
    }
  }
}
```

Option B (in-place migration) is preferred for stateful DOs with existing instances; Option A is cleaner for entirely new domain logic.

---

## Section 6: Observability During Split Traffic

Use the `CF-Worker-Version` header to distinguish version traffic in logs:

```typescript
// Add version identification to all responses (set via environment variable at upload time)
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const response = await handleRequest(request, env);
    const clone    = new Response(response.body, response);
    clone.headers.set('X-Worker-Version', env.WORKER_VERSION ?? 'unknown');
    return clone;
  },
};
```

Bind `WORKER_VERSION` as a plain text binding at version upload time:

```typescript
const bindings: WorkerBinding[] = [
  { type: 'plain_text', name: 'WORKER_VERSION', text: canaryVersionId },
  // ... other bindings
];
```

Query Cloudflare Workers Analytics Engine filtered by `X-Worker-Version` header via Logpush to compare error rates and latency percentiles between the stable and canary version side-by-side.

---

## Anti-patterns

- **Deploying Durable Object class changes with a version split**: If the new Worker version references a DO class that the old version does not know about, the old version will throw on upgrade. Migrate DO classes in a separate, staged step before enabling traffic split.
- **Using `wrangler deploy` after a Versions API workflow**: `wrangler deploy` creates a new version AND immediately deploys it at 100%, collapsing your carefully managed split. In a Versions API pipeline, do not mix `wrangler deploy` and the Versions/Deployments API.
- **Not storing the stable version ID in CI state**: If an incident requires rollback but the stable version ID is not persisted, you must query the API to find the last known-good version. Always write `stableVersionId` to a durable artifact store (e.g., a KV namespace or GitHub release tag).
- **Long soak periods at 1%**: At 1% traffic, statistically significant error rate differences require many more requests to detect. On low-traffic Workers, start at 10% or use synthetic canary traffic.

---

## Gotchas

- **Maximum two versions per deployment**: The Versions API supports exactly two versions in a split. You cannot run a three-way A/B/C test; create two separate Worker scripts instead.
- **KV and R2 bindings are shared**: Both versions share the same KV namespace and R2 bucket. If the new version writes a new KV schema that the old version cannot parse, the rollback will fail. Maintain backward-compatible KV schemas during the split window.
- **Secrets are version-level**: Workers Secrets are attached at the Worker script level, not the version level. All versions of a script share the same secrets.
- **Free plan restriction**: Worker version splitting requires the Workers Paid plan. Free plan Workers use atomic `wrangler deploy` only.
- **Version expiry**: Versions not referenced by any deployment are not automatically deleted, but Cloudflare retains a rolling 30-day window. Reference old versions for rollback within that window.

---

## Verification

```bash
# List current versions
curl -s "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/scripts/my-api/versions" \
  -H "Authorization: Bearer ${API_TOKEN}" | jq '.result[] | {id, created_on}'

# Check active deployment and weights
curl -s "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/scripts/my-api/deployments" \
  -H "Authorization: Bearer ${API_TOKEN}" | jq '.result.versions'

# Verify response headers distinguish version in live traffic
for i in $(seq 1 20); do
  curl -s -I "https://my-api.example.com/health" | grep X-Worker-Version
done
# Should see mix of stable and canary version IDs proportional to split weights

# Force rollback
curl -X POST "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/scripts/my-api/deployments" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"strategy\":\"percentage\",\"versions\":[{\"version_id\":\"${STABLE_VERSION_ID}\",\"percentage\":100}]}"
```

---

## Related

- `blue-green-architecture.md` — general blue-green deployment concepts
- `canary-deployment-architecture.md` — canary patterns and health gates
- `durable-objects-workflow-state-machine.md` — DO migration patterns
- `zero-downtime-schema-migrations.md` — backward-compatible schema changes during splits
- `feature-flag-cloudflare-workers-kv.md` — feature flags as an alternative to traffic splits

---

## Sources

- Cloudflare Workers Versions API: https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
- Cloudflare Workers Deployments API: https://developers.cloudflare.com/workers/configuration/versions-and-deployments/gradual-deployments/
- Cloudflare Workers Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
- Durable Objects migration: https://developers.cloudflare.com/durable-objects/reference/durable-objects-migrations/
- Wrangler CLI reference: https://developers.cloudflare.com/workers/wrangler/
