# Triggering Cloudflare Pages Deployments from External CI via Deploy Hooks

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your CI pipeline lives outside Cloudflare (GitHub Actions, Jenkins, CircleCI) and you need to trigger a Pages deployment after a successful build or test stage. Direct Git-push integration is unavailable or undesirable because the build artifact is produced by an external system that should own the release gate.

---

## Context

Cloudflare Pages Deploy Hooks are webhook URLs generated in the Pages dashboard that accept an unauthenticated HTTP POST to kick off a new deployment from the latest commit on a named branch. The hook returns a deployment ID immediately; you then poll the Cloudflare API with a bearer token to track completion. Because the hook itself carries no secrets beyond the URL, it should be stored as a CI secret. After a successful deployment the metadata (deployment ID, timestamp, environment) can be written to a D1 `deployments` table to power rollback tooling and audit trails. The polling loop is idempotent — re-running it after a transient failure simply re-reads state rather than triggering a second deploy.

---

## Section 1 — GitHub Actions Workflow

```yaml
# .github/workflows/deploy.yml
name: Deploy via Pages Hook

on:
  push:
    branches: [main]
  workflow_dispatch:

env:
  CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
  CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
  PAGES_PROJECT: my-pages-project
  PAGES_HOOK_URL: ${{ secrets.CF_PAGES_HOOK_URL }}

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: npm

      - name: Install & Build
        run: |
          npm ci
          npm run build

      - name: Trigger Pages Deploy Hook
        id: trigger
        run: |
          RESPONSE=$(curl -s -X POST "$PAGES_HOOK_URL")
          echo "response=$RESPONSE" >> $GITHUB_OUTPUT
          DEPLOY_ID=$(echo "$RESPONSE" | jq -r '.result.id')
          echo "deploy_id=$DEPLOY_ID" >> $GITHUB_OUTPUT

      - name: Poll deployment status
        id: poll
        run: |
          DEPLOY_ID="${{ steps.trigger.outputs.deploy_id }}"
          MAX_ATTEMPTS=30
          SLEEP_SECONDS=10
          for i in $(seq 1 $MAX_ATTEMPTS); do
            STATUS=$(curl -s \
              -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
              "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/pages/projects/$PAGES_PROJECT/deployments/$DEPLOY_ID" \
              | jq -r '.result.latest_stage.status')
            echo "Attempt $i: $STATUS"
            if [ "$STATUS" = "success" ]; then
              echo "status=success" >> $GITHUB_OUTPUT
              exit 0
            elif [ "$STATUS" = "failure" ]; then
              echo "Deployment failed"
              exit 1
            fi
            sleep $SLEEP_SECONDS
          done
          echo "Timed out waiting for deployment"
          exit 1

      - name: Write deploy metadata to D1
        if: steps.poll.outputs.status == 'success'
        run: |
          DEPLOY_ID="${{ steps.trigger.outputs.deploy_id }}"
          TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
          GIT_SHA="${{ github.sha }}"
          npx wrangler d1 execute my-d1-database \
            --command "INSERT INTO deployments (id, project, git_sha, deployed_at, environment) \
                       VALUES ('$DEPLOY_ID', '$PAGES_PROJECT', '$GIT_SHA', '$TIMESTAMP', 'production');" \
            --remote
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

---

## Section 2 — D1 Schema and Metadata Writer

```sql
-- migrations/0001_deployments.sql
CREATE TABLE IF NOT EXISTS deployments (
  id          TEXT PRIMARY KEY,
  project     TEXT NOT NULL,
  git_sha     TEXT NOT NULL,
  deployed_at TEXT NOT NULL,
  environment TEXT NOT NULL DEFAULT 'production',
  status      TEXT NOT NULL DEFAULT 'success',
  rolled_back INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_deployments_project ON deployments(project, deployed_at DESC);
```

```typescript
// scripts/write-deploy-meta.ts
import { execSync } from 'child_process';

const { CF_ACCOUNT_ID, CF_API_TOKEN, PAGES_PROJECT, D1_DATABASE } = process.env;

async function fetchDeployment(deployId: string) {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/pages/projects/${PAGES_PROJECT}/deployments/${deployId}`,
    { headers: { Authorization: `Bearer ${CF_API_TOKEN}` } }
  );
  const json = (await res.json()) as { result: { id: string; created_on: string; deployment_trigger: { metadata: { commit_hash: string } } } };
  return json.result;
}

async function main() {
  const deployId = process.argv[2];
  if (!deployId) throw new Error('Usage: write-deploy-meta.ts <deployId>');

  const deploy = await fetchDeployment(deployId);
  const sql = `
    INSERT INTO deployments (id, project, git_sha, deployed_at, environment)
    VALUES (
      '${deploy.id}',
      '${PAGES_PROJECT}',
      '${deploy.deployment_trigger.metadata.commit_hash}',
      '${deploy.created_on}',
      'production'
    ) ON CONFLICT(id) DO NOTHING;
  `;

  execSync(
    `npx wrangler d1 execute ${D1_DATABASE} --command "${sql.replace(/\n/g, ' ')}" --remote`,
    { stdio: 'inherit' }
  );
}

main().catch((err) => { console.error(err); process.exit(1); });
```

---

## Section 3 — Rollback via Pages API

```bash
#!/usr/bin/env bash
# scripts/rollback-pages.sh
# Usage: ./rollback-pages.sh <deployment-id-to-rollback-to>
set -euo pipefail

DEPLOY_ID="${1:-}"
[ -z "$DEPLOY_ID" ] && { echo "ERROR: provide a deployment ID to roll back to"; exit 1; }

echo "Rolling back $PAGES_PROJECT to deployment $DEPLOY_ID ..."
curl -s -X POST \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/pages/projects/$PAGES_PROJECT/deployments/$DEPLOY_ID/rollback" \
  | jq '.'

# Mark the original deployment rolled_back in D1
npx wrangler d1 execute "$D1_DATABASE" \
  --command "UPDATE deployments SET rolled_back = 1 WHERE id = '$DEPLOY_ID';" \
  --remote

echo "Rollback triggered. Monitor at https://dash.cloudflare.com/pages/projects/$PAGES_PROJECT"
```

---

## Anti-patterns
- **Polling without a timeout** — an infinite loop blocks the CI runner slot indefinitely; always set a `MAX_ATTEMPTS` guard.
- **Storing the hook URL in source code** — treat it like a secret; rotate immediately if leaked.
- **Triggering a hook before the build completes** — the hook deploys the latest *committed* code, not your local build output; ensure the commit is pushed before POSTing.
- **Skipping D1 writes on failure** — failed deployments should still be logged so rollback tooling has a complete history.

---

## Gotchas
- A Deploy Hook always deploys the latest commit on the branch it was created for — you cannot target an arbitrary commit via the hook alone.
- The hook response `result.id` is the deployment ID; the `latest_stage.status` field cycles through `queued → initializing → cloning_repo → building → deploying → success/failure`.
- Pages API rate limit is 1200 requests/5 min per token; at 10-second poll intervals you reach 30 checks in 5 minutes — stay well within limits.
- `wrangler d1 execute --remote` requires `CLOUDFLARE_API_TOKEN` with the `D1:Edit` permission scope.

---

## Verification

```bash
# Confirm hook fires and returns a deployment ID
curl -s -X POST "$CF_PAGES_HOOK_URL" | jq '.result.id'

# Check deployment status manually
curl -s \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/pages/projects/$PAGES_PROJECT/deployments" \
  | jq '[.result[] | {id, status: .latest_stage.status, created: .created_on}] | .[0:5]'

# Verify D1 record written
npx wrangler d1 execute my-d1-database \
  --command "SELECT * FROM deployments ORDER BY deployed_at DESC LIMIT 5;" \
  --remote
```

---

## Related
- `workers-version-metadata-binding-deploy.md`
- `cloudflare-pages-direct-upload-ci.md`

---

## Sources
- Cloudflare Pages Deploy Hooks — https://developers.cloudflare.com/pages/configuration/deploy-hooks/
- Cloudflare Pages REST API — https://developers.cloudflare.com/api/resources/pages/subresources/deployments/
- Cloudflare D1 Wrangler CLI — https://developers.cloudflare.com/d1/wrangler-commands/
