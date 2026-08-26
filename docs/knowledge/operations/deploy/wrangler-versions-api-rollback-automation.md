# Deploy Rollback Automation via Wrangler Versions API

- Date: 2026-08-23
- Author: example.com
- Status: production

## Symptom / Use-case

A bad deployment reaches production. Your SLO alert fires within minutes. The on-call engineer needs to roll back to the last known-good Worker version in under two minutes, without re-running the CI pipeline and without touching the source branch.

## Context

Cloudflare Workers' **Versions API** (`/accounts/:id/workers/scripts/:name/versions`) stores every uploaded script version indefinitely, independent of deployments. A separate **Deployments API** controls what percentage of traffic each version receives. Together they enable sub-second programmatic rollback without a rebuild. This article covers the automation layer: a CI job that publishes a "rollback envelope" artifact after every deploy, and a rollback script that re-promotes the previous version via the REST API.

---

## 1. Versioned Deploy Flow Overview

Every `wrangler deploy` implicitly creates a new version. With `--experimental-versions`, versions and deployments are decoupled:

```bash
# Upload a new version WITHOUT routing traffic to it
wrangler versions upload \
  --name my-worker \
  --message "v$(git rev-parse --short HEAD) feat: new checkout flow"

# Deploy the version to 100 % of traffic
wrangler versions deploy \
  --name my-worker \
  --version-id "$UPLOAD_VERSION_ID" \
  --percentage 100
```

---

## 2. Capturing the Rollback Envelope in CI

After each successful deploy, write the active version ID to an artifact store (KV, R2, or your CD system's artifact store) so rollback scripts can find it without hitting the list API:

```typescript
// scripts/publish-rollback-envelope.ts
import { execSync } from "node:child_process";

const ACCOUNT_ID  = process.env.CF_ACCOUNT_ID!;
const API_TOKEN   = process.env.CF_API_TOKEN!;
const WORKER_NAME = process.env.WORKER_NAME!;
const KV_NS_ID    = process.env.ROLLBACK_KV_NS_ID!;

async function getCurrentDeployment(): Promise<{ versionId: string; deploymentId: string }> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/scripts/${WORKER_NAME}/deployments`,
    { headers: { Authorization: `Bearer ${API_TOKEN}` } }
  );
  const data = await res.json() as any;
  const latest = data.result.items[0];
  return {
    versionId:    latest.versions[0].version_id,
    deploymentId: latest.id,
  };
}

async function main() {
  const { versionId, deploymentId } = await getCurrentDeployment();
  const envelope = JSON.stringify({
    versionId,
    deploymentId,
    gitSha:    process.env.GITHUB_SHA ?? "unknown",
    timestamp: new Date().toISOString(),
  });

  // Store as "previous" before rotating — shift the window
  const previous = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/storage/kv/namespaces/${KV_NS_ID}/values/rollback:current`,
    { headers: { Authorization: `Bearer ${API_TOKEN}` } }
  ).then(r => r.text()).catch(() => null);

  if (previous) {
    await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/storage/kv/namespaces/${KV_NS_ID}/values/rollback:previous`,
      {
        method:  "PUT",
        headers: { Authorization: `Bearer ${API_TOKEN}`, "Content-Type": "text/plain" },
        body:    previous,
      }
    );
  }

  await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/storage/kv/namespaces/${KV_NS_ID}/values/rollback:current`,
    {
      method:  "PUT",
      headers: { Authorization: `Bearer ${API_TOKEN}`, "Content-Type": "text/plain" },
      body:    envelope,
    }
  );

  console.log("Rollback envelope stored:", envelope);
}

main().catch(err => { console.error(err); process.exit(1); });
```

---

## 3. Automated Rollback Script

```typescript
// scripts/rollback.ts
const ACCOUNT_ID  = process.env.CF_ACCOUNT_ID!;
const API_TOKEN   = process.env.CF_API_TOKEN!;
const WORKER_NAME = process.env.WORKER_NAME!;
const KV_NS_ID    = process.env.ROLLBACK_KV_NS_ID!;

async function kv(key: string) {
  const r = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/storage/kv/namespaces/${KV_NS_ID}/values/${key}`,
    { headers: { Authorization: `Bearer ${API_TOKEN}` } }
  );
  if (!r.ok) throw new Error(`KV read failed: ${r.status}`);
  return JSON.parse(await r.text());
}

async function deployVersion(versionId: string) {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/scripts/${WORKER_NAME}/deployments`,
    {
      method:  "POST",
      headers: {
        Authorization:  `Bearer ${API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        versions: [{ version_id: versionId, percentage: 100 }],
        annotations: { "workers/message": "automated rollback" },
      }),
    }
  );
  const data = await res.json() as any;
  if (!data.success) throw new Error(JSON.stringify(data.errors));
  return data.result;
}

async function main() {
  const target = process.argv[2] === "--two-back"
    ? await kv("rollback:previous")
    : await kv("rollback:previous"); // default: one version back

  console.log(`Rolling back to version ${target.versionId} (git: ${target.gitSha})`);
  const deployment = await deployVersion(target.versionId);
  console.log("Rollback deployment ID:", deployment.id);
}

main().catch(err => { console.error(err); process.exit(1); });
```

---

## 4. GitHub Actions Integration

```yaml
# .github/workflows/deploy.yml
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - run: npx wrangler versions upload --name "$WORKER_NAME"
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
      - run: npx wrangler versions deploy --name "$WORKER_NAME" --percentage 100
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
      - name: Store rollback envelope
        run: npx tsx scripts/publish-rollback-envelope.ts
        env:
          CF_ACCOUNT_ID:      ${{ secrets.CF_ACCOUNT_ID }}
          CF_API_TOKEN:       ${{ secrets.CF_API_TOKEN }}
          WORKER_NAME:        ${{ vars.WORKER_NAME }}
          ROLLBACK_KV_NS_ID:  ${{ secrets.ROLLBACK_KV_NS_ID }}

  rollback:
    if: ${{ github.event_name == 'workflow_dispatch' && github.event.inputs.action == 'rollback' }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - run: npx tsx scripts/rollback.ts
        env:
          CF_ACCOUNT_ID:      ${{ secrets.CF_ACCOUNT_ID }}
          CF_API_TOKEN:       ${{ secrets.CF_API_TOKEN }}
          WORKER_NAME:        ${{ vars.WORKER_NAME }}
          ROLLBACK_KV_NS_ID:  ${{ secrets.ROLLBACK_KV_NS_ID }}
```

---

## 5. Gradual Rollback with Traffic Splitting

When you suspect — but haven't confirmed — that the current version is bad, shift traffic gradually before committing to a full rollback:

```bash
# Reduce current version to 10 %, let previous absorb 90 %
CURRENT_VID="<current-version-id>"
PREVIOUS_VID="<previous-version-id>"

curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/$WORKER_NAME/deployments" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "versions": [
      { "version_id": "'$PREVIOUS_VID'", "percentage": 90 },
      { "version_id": "'$CURRENT_VID'",  "percentage": 10 }
    ]
  }'
```

Observe error rates for 5 min, then flip to 100 % previous if confirmed bad.

---

## Anti-patterns

- **Re-running CI to rollback** — a pipeline rebuild takes 5–15 min and may fail if the repo state has diverged; always use the version promotion API directly.
- **Relying on `wrangler rollback` without a pinned version** — `wrangler rollback` promotes the previous *deployment* but that deployment may itself have been a partial rollback; use explicit version IDs.
- **Storing the rollback envelope only in the pipeline artifact store** — pipeline artifacts are ephemeral; persist the envelope in KV or R2 for reliability.
- **Not testing the rollback script in staging** — rollback code paths are often untested; run the rollback workflow monthly as a drill.

## Gotchas

- **Version retention** — Cloudflare retains up to the 10 most recent Worker versions by default (as of 2026); for longer history, integrate with R2 or your own artifact store.
- **Bindings compatibility** — rolling back to a version that was bound to an older D1 schema or KV key shape may cause runtime errors even after the code rollback. Always confirm binding compatibility before finalizing rollback.
- **`--experimental-versions` flag** — the decoupled versions/deployments API requires this Wrangler flag while it remains in beta; check the Wrangler changelog before removing it.
- **Audit trail** — tag rollback deployments with the `workers/message` annotation so they appear distinctly in the Cloudflare dashboard deployment history.

## Verification

```bash
# Confirm active deployment version
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/$WORKER_NAME/deployments" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  | jq '.result.items[0].versions[0]'

# Smoke test the live Worker
curl -sf https://myapp.com/health | jq '.version'

# Tail logs to confirm error rate dropping
wrangler tail "$WORKER_NAME" --format pretty | grep -i error
```

## Related

- `worker-versioning-gradual-rollout.md`
- `rollback-strategies-workers-pages.md`
- `wrangler-version-upload-metadata.md`
- `deployment-health-gates-automated-rollback.md`

## Sources

- Workers Versions API: https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
- Wrangler versions commands: https://developers.cloudflare.com/workers/wrangler/commands/#versions
- Cloudflare Deployments API reference: https://developers.cloudflare.com/api/resources/workers/subresources/deployments/
