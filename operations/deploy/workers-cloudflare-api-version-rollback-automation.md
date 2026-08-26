# Workers Deployment Version Rollback Automation with Cloudflare REST API

- **Date:** 2026-08-24
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Your error-rate alerting fires three minutes after a production deployment. You need to roll back the Worker to the previous known-good version using a scripted, machine-executable action — without requiring an engineer to run `wrangler` commands manually, without re-running the CI build pipeline, and without access to the original `wrangler.toml` or source repository. The rollback must complete within 30 seconds of the trigger.

---

## Context

The Cloudflare Workers REST API exposes two separate resources that together enable zero-rebuild rollback: the **Versions API** (`/accounts/{account_id}/workers/scripts/{script_name}/versions`) stores every uploaded script immutably, and the **Deployments API** (`/accounts/{account_id}/workers/scripts/{script_name}/deployments`) controls which version ID receives what percentage of traffic. By calling the Deployments API to set the previous version ID to 100% of traffic, traffic is shifted within seconds — no artifact rebuild, no `wrangler` CLI, no source checkout required.

This article covers REST API-only rollback: direct `fetch` calls against the Cloudflare API, suitable for embedding in monitoring automation, incident runbooks, and PagerDuty webhooks. For wrangler CLI-based rollback, see `wrangler-versions-api-rollback-automation.md`.

---

## 1. API Client Primitives

```typescript
// src/cf-api-client.ts
const BASE = "https://api.cloudflare.com/client/v4";

export interface CfApiOptions {
  accountId: string;
  apiToken: string;
}

export interface WorkerVersion {
  id: string;
  number: number;
  metadata: {
    created_on: string;
    author_email: string;
    source: string;
    annotations?: {
      "workers/message"?: string;
      "workers/tag"?: string;
    };
  };
}

export interface WorkerDeployment {
  id: string;
  source: string;
  strategy: string;
  author_email: string;
  created_on: string;
  versions: Array<{
    version_id: string;
    percentage: number;
  }>;
}

export async function listVersions(
  opts: CfApiOptions,
  scriptName: string
): Promise<WorkerVersion[]> {
  const res = await cfFetch(
    `${BASE}/accounts/${opts.accountId}/workers/scripts/${scriptName}/versions?order=desc&per_page=10`,
    opts.apiToken
  );
  return res.result as WorkerVersion[];
}

export async function listDeployments(
  opts: CfApiOptions,
  scriptName: string
): Promise<WorkerDeployment[]> {
  const res = await cfFetch(
    `${BASE}/accounts/${opts.accountId}/workers/scripts/${scriptName}/deployments`,
    opts.apiToken
  );
  return res.result as WorkerDeployment[];
}

export async function createDeployment(
  opts: CfApiOptions,
  scriptName: string,
  versionId: string,
  message: string
): Promise<WorkerDeployment> {
  const res = await cfFetch(
    `${BASE}/accounts/${opts.accountId}/workers/scripts/${scriptName}/deployments`,
    opts.apiToken,
    {
      method: "POST",
      body: JSON.stringify({
        versions: [{ version_id: versionId, percentage: 100 }],
        strategy: "percentage",
        annotations: {
          "workers/message": message,
        },
      }),
    }
  );
  return res.result as WorkerDeployment;
}

async function cfFetch(
  url: string,
  token: string,
  init: RequestInit = {}
): Promise<{ result: unknown; success: boolean; errors: unknown[] }> {
  const res = await fetch(url, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...((init.headers as Record<string, string>) ?? {}),
    },
  });

  const json = (await res.json()) as {
    result: unknown;
    success: boolean;
    errors: Array<{ code: number; message: string }>;
  };

  if (!json.success) {
    const errs = json.errors.map((e) => `${e.code}: ${e.message}`).join("; ");
    throw new Error(`Cloudflare API error: ${errs}`);
  }

  return json;
}
```

---

## 2. Core Rollback Logic

```typescript
// src/rollback.ts
import {
  listVersions,
  listDeployments,
  createDeployment,
  type CfApiOptions,
} from "./cf-api-client";

export interface RollbackResult {
  rolledBackFrom: string;      // version ID that was active
  rolledBackTo: string;        // version ID now active
  deploymentId: string;
  durationMs: number;
}

/**
 * Roll back a Worker to the version immediately preceding the current deployment.
 * If targetVersionId is provided, rolls back to that specific version instead.
 */
export async function rollbackWorker(
  opts: CfApiOptions,
  scriptName: string,
  options: {
    targetVersionId?: string;
    message?: string;
  } = {}
): Promise<RollbackResult> {
  const start = Date.now();

  // 1. Get current deployment to identify the active version
  const deployments = await listDeployments(opts, scriptName);
  if (deployments.length === 0) {
    throw new Error(`No deployments found for script '${scriptName}'`);
  }

  const currentDeployment = deployments[0]; // Most recent deployment
  const activeVersions = currentDeployment.versions.filter(
    (v) => v.percentage > 0
  );

  if (activeVersions.length !== 1 || activeVersions[0].percentage !== 100) {
    throw new Error(
      `Current deployment is a split-traffic configuration: ${JSON.stringify(activeVersions)}. ` +
        `Resolve to 100% before automated rollback.`
    );
  }

  const currentVersionId = activeVersions[0].version_id;

  // 2. Determine rollback target
  let rollbackVersionId: string;

  if (options.targetVersionId) {
    rollbackVersionId = options.targetVersionId;
  } else {
    // Find the version immediately before the current one
    const versions = await listVersions(opts, scriptName);
    const currentIndex = versions.findIndex((v) => v.id === currentVersionId);

    if (currentIndex === -1) {
      throw new Error(
        `Current version '${currentVersionId}' not found in versions list`
      );
    }

    if (currentIndex === versions.length - 1) {
      throw new Error(
        `Current version is the oldest stored version. Cannot roll back further.`
      );
    }

    rollbackVersionId = versions[currentIndex + 1].id;
  }

  if (rollbackVersionId === currentVersionId) {
    throw new Error("Rollback target is the same as the current version.");
  }

  // 3. Create new deployment pointing 100% traffic to rollback version
  const message =
    options.message ??
    `Automated rollback from ${currentVersionId.slice(0, 8)} to ${rollbackVersionId.slice(0, 8)}`;

  const newDeployment = await createDeployment(
    opts,
    scriptName,
    rollbackVersionId,
    message
  );

  return {
    rolledBackFrom: currentVersionId,
    rolledBackTo: rollbackVersionId,
    deploymentId: newDeployment.id,
    durationMs: Date.now() - start,
  };
}
```

---

## 3. Monitoring-Triggered Rollback Worker

```typescript
// src/rollback-trigger.ts
// A Worker that receives PagerDuty / Alertmanager webhook events
// and triggers rollback automatically when error rate exceeds threshold.

import { rollbackWorker } from "./rollback";

export interface Env {
  CF_ACCOUNT_ID: string;
  CF_ROLLBACK_TOKEN: string;   // token with workers_scripts:edit scope
  WEBHOOK_SECRET: string;
  SLACK_WEBHOOK_URL: string;
}

interface AlertPayload {
  alert_name: string;
  worker_script: string;
  severity: "critical" | "warning";
  fingerprint: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    // Validate shared secret header
    const secret = <redacted-secret>"X-Webhook-Secret");
    if (secret !== env.WEBHOOK_SECRET) {
      return new Response("Unauthorized", { status: 401 });
    }

    const payload: AlertPayload = await request.json();

    // Only auto-rollback on critical alerts
    if (payload.severity !== "critical") {
      return new Response("Non-critical alert: skipping auto-rollback", { status: 200 });
    }

    const opts = {
      accountId: env.CF_ACCOUNT_ID,
      apiToken: env.CF_ROLLBACK_TOKEN,
    };

    let result: Awaited<ReturnType<typeof rollbackWorker>>;
    try {
      result = await rollbackWorker(opts, payload.worker_script, {
        message: `Auto-rollback triggered by alert: ${payload.alert_name} (${payload.fingerprint})`,
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      await notifySlack(env.SLACK_WEBHOOK_URL, `Rollback FAILED for ${payload.worker_script}: ${msg}`, "danger");
      return new Response(`Rollback failed: ${msg}`, { status: 500 });
    }

    await notifySlack(
      env.SLACK_WEBHOOK_URL,
      `Rollback SUCCESS for \`${payload.worker_script}\`:\n` +
        `• From: \`${result.rolledBackFrom.slice(0, 8)}\`\n` +
        `• To: \`${result.rolledBackTo.slice(0, 8)}\`\n` +
        `• Deployment: \`${result.deploymentId}\`\n` +
        `• Duration: ${result.durationMs}ms`,
      "good"
    );

    return Response.json({ ok: true, ...result });
  },
} satisfies ExportedHandler<Env>;

async function notifySlack(
  webhookUrl: string,
  text: string,
  color: "good" | "warning" | "danger"
): Promise<void> {
  await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      attachments: [{ color, text, mrkdwn_in: ["text"] }],
    }),
  });
}
```

---

## 4. CLI Rollback Script (Bash)

```bash
#!/usr/bin/env bash
# scripts/rollback.sh — call directly from an incident runbook
# Usage: CF_ACCOUNT_ID=xxx CF_API_TOKEN=xxx ./scripts/rollback.sh my-worker [version-id]
set -euo pipefail

SCRIPT_NAME="${1:?Usage: $0 <script-name> [target-version-id]}"
TARGET_VERSION_ID="${2:-}"

CF_API="https://api.cloudflare.com/client/v4"
AUTH="-H \"Authorization: Bearer ${CF_API_TOKEN}\""

# 1. Get current active deployment
DEPLOYMENTS=$(
  curl -s \
    "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/${SCRIPT_NAME}/deployments" \
    -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq -r '.result'
)

CURRENT_VERSION=$(echo "$DEPLOYMENTS" | jq -r '.[0].versions[] | select(.percentage == 100) | .version_id')
echo "Current active version: ${CURRENT_VERSION}"

# 2. Determine rollback target
if [ -z "${TARGET_VERSION_ID}" ]; then
  TARGET_VERSION_ID=$(
    curl -s \
      "${CF_API}/accounts/${CF_ACCOUNT_ID}/workers/scripts/${SCRIPT_NAME}/versions?order=desc&per_page=10" \
      -H "Authorization: Bearer ${CF_API_TOKEN}" \
    | jq -r --arg current "$CURRENT_VERSION" \
        '[.result[] | .id] | index($current) as $idx | .[$idx + 1]'
  )
  echo "Auto-selected previous version: ${TARGET_VERSION_ID}"
else
  echo "Target version specified: ${TARGET_VERSION_ID}"
fi

# 3. Post new deployment
DEPLOY_RESULT=$(
  curl -s -X POST \
    "${CF_API}/accounts/${CF_ACCOUNT_ID}/workers/scripts/${SCRIPT_NAME}/deployments" \
    -H "Authorization: Bearer ${CF_API_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{
      \"versions\": [{\"version_id\": \"${TARGET_VERSION_ID}\", \"percentage\": 100}],
      \"strategy\": \"percentage\",
      \"annotations\": {\"workers/message\": \"Manual rollback from ${CURRENT_VERSION:0:8} to ${TARGET_VERSION_ID:0:8}\"}
    }"
)

SUCCESS=$(echo "$DEPLOY_RESULT" | jq -r '.success')
if [ "$SUCCESS" != "true" ]; then
  echo "ERROR: Rollback failed"
  echo "$DEPLOY_RESULT" | jq '.errors'
  exit 1
fi

DEPLOYMENT_ID=$(echo "$DEPLOY_RESULT" | jq -r '.result.id')
echo "Rollback complete."
echo "  From: ${CURRENT_VERSION}"
echo "  To:   ${TARGET_VERSION_ID}"
echo "  Deployment ID: ${DEPLOYMENT_ID}"
```

---

## 5. GitHub Actions: Manual Rollback Workflow

```yaml
# .github/workflows/worker-rollback.yml
name: Worker Rollback

on:
  workflow_dispatch:
    inputs:
      script_name:
        description: "Worker script name (e.g. my-worker)"
        required: true
      version_id:
        description: "Target version ID (leave blank for previous version)"
        required: false

jobs:
  rollback:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: "npm"
      - run: npm ci

      - name: Execute rollback
        env:
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          CF_ROLLBACK_TOKEN: ${{ secrets.CF_ROLLBACK_TOKEN }}
          SCRIPT_NAME: ${{ github.event.inputs.script_name }}
          TARGET_VERSION: ${{ github.event.inputs.version_id }}
        run: |
          npx tsx -e "
            import { rollbackWorker } from './src/rollback.js';
            const result = await rollbackWorker(
              { accountId: process.env.CF_ACCOUNT_ID, apiToken: process.env.CF_ROLLBACK_TOKEN },
              process.env.SCRIPT_NAME,
              { targetVersionId: process.env.TARGET_VERSION || undefined }
            );
            console.log(JSON.stringify(result, null, 2));
          "
```

---

## Anti-patterns

- **Rolling back to a version by index** (e.g., "the second-newest") instead of by ID — version list ordering can change if versions are explicitly deleted. Always use the immutable version ID.
- **Using `workers_scripts:edit` scope for the rollback token** when `workers_deployments:write` alone suffices — the deployment API only requires `workers_deployments:write`. Smaller scope reduces blast radius if the rollback token is leaked.
- **Storing the rollback token with the same credentials as the deploy token** — if a compromised deploy token triggers a bad deployment, the attacker can also prevent rollback. Keep rollback credentials separate.
- **Auto-rolling back during staged (split-traffic) deployments** — the logic above guards against this, but removing the guard and forcing 100% to a single version during a split can destroy the intentional canary state.

---

## Gotchas

- The Deployments API requires **Workers Versions** to be enabled for the script. Scripts deployed with standard `wrangler deploy` (no `--experimental-versions`) use a different API surface and cannot be rolled back this way without first enabling versioning.
- `created_on` timestamps in the Versions API are in UTC ISO 8601. When searching for "the version before X", sort by `number` (monotonically increasing integer) rather than `created_on` to avoid clock-skew edge cases.
- The rollback creates a **new deployment record** pointing to an old version ID. The version itself is unchanged; only the traffic routing record is new. This means `wrangler versions list` shows the rollback as a new deployment, which is auditable.
- API rate limits: the Deployments API allows 1 write per second per script. In automated systems, add a 2-second backoff between a failed rollback attempt and a retry.

---

## Verification

```bash
# 1. Confirm the new deployment's active version
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/my-worker/deployments" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '.result[0] | {id, versions}'

# 2. Confirm traffic is flowing and error rate is recovering
wrangler tail my-worker --format=json \
  | jq 'select(.outcome != "ok") | .outcome'

# 3. List last 5 deployments to see rollback in audit trail
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/scripts/my-worker/deployments" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  | jq '[.result[:5][] | {id, created_on, versions}]'
```

---

## Related

- `wrangler-versions-api-rollback-automation.md` — rollback via wrangler CLI commands with envelope artifacts
- `workers-version-rollback-automation-health-check.md` — health-check-triggered rollback with wrangler
- `rollback-decision-automation-slo-monitoring.md` — SLO-based automated rollback decision logic
- `deployment-health-gates-automated-rollback.md` — deployment health gates and automated rollback policies
- `live-revision-verification-and-rollback-evidence.md` — producing evidence for rollback events

---

## Sources

- Cloudflare API — Worker Versions: https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/
- Cloudflare API — Worker Deployments: https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/deployments/
- Cloudflare Docs — Versions and Deployments: https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
