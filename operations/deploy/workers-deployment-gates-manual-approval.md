# Manual Approval Gate Before Production Deploy

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want human sign-off before a Cloudflare Worker reaches production. Specifically:
- A staging deploy runs automatically on merge to `main`.
- A production deploy requires a named reviewer to click "Approve" in the GitHub UI.
- Every approval (or rejection) is recorded in a D1 audit-log table.

## Context

- GitHub Actions **Environments** with `required_reviewers` enforce the gate.
- A second job (`deploy-prod`) references the `production` environment and only starts
  after the gate is cleared.
- A `workflow_dispatch` input lets you promote any staging build to production on-demand.
- D1 audit logging is written by a small Cloudflare Worker that the workflow calls via
  its API.

---

## Section 1 — GitHub Environment and reviewer configuration

Create the `production` environment via the GitHub UI or API:

```bash
# GitHub CLI — requires the `environments` scope
gh api \
  --method PUT \
  repos/{owner}/{repo}/environments/production \
  --field "required_reviewers[][type]=User" \
  --field "required_reviewers[][id]=<github_user_id>" \
  --field "wait_timer=0"
```

Or via `repos/{owner}/{repo}/environments/production` REST body:

```json
{
  "reviewers": [
    { "type": "User", "id": 12345678 },
    { "type": "Team", "id": 9999 }
  ],
  "deployment_branch_policy": {
    "protected_branches": true,
    "custom_branch_policies": false
  }
}
```

---

## Section 2 — Workflow with staging + gated production jobs

```yaml
# .github/workflows/deploy.yml
name: Deploy Worker

on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      promote_run_id:
        description: 'Run ID of the staging build to promote to production'
        required: true
        type: string

permissions:
  contents: read
  deployments: write
  id-token: write   # for OIDC if used

jobs:
  deploy-staging:
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
    environment: staging
    env:
      CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN_STAGING }}
      CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
    outputs:
      version_id: ${{ steps.deploy.outputs.version_id }}

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm ci

      - name: Deploy to staging
        id: deploy
        run: |
          OUTPUT=$(npx wrangler deploy --env staging 2>&1)
          echo "$OUTPUT"
          VERSION_ID=$(echo "$OUTPUT" | grep -oP '(?<=Version ID: )[\w-]+' | head -1)
          echo "version_id=${VERSION_ID}" >> "$GITHUB_OUTPUT"

      - name: Log to audit D1
        env:
          AUDIT_WORKER_URL: ${{ secrets.AUDIT_WORKER_URL }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          curl -fsSL -X POST "$AUDIT_WORKER_URL/log" \
            -H 'Content-Type: application/json' \
            -d "$(jq -n \
              --arg env staging \
              --arg actor "$GITHUB_ACTOR" \
              --arg sha "$GITHUB_SHA" \
              --arg version_id "${{ steps.deploy.outputs.version_id }}" \
              --arg action deployed \
              '{env:$env,actor:$actor,sha:$sha,version_id:$version_id,action:$action}')"

  deploy-prod:
    needs: [deploy-staging]
    if: |
      github.event_name == 'push' ||
      github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    environment: production   # <-- blocks here for reviewer approval
    env:
      CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN_PROD }}
      CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm ci

      - name: Deploy to production
        id: deploy
        run: |
          OUTPUT=$(npx wrangler deploy --env production 2>&1)
          echo "$OUTPUT"
          VERSION_ID=$(echo "$OUTPUT" | grep -oP '(?<=Version ID: )[\w-]+' | head -1)
          DEPLOY_URL=$(echo "$OUTPUT" | grep -oP 'https://[^\s]+\.workers\.dev[^\s]*' | head -1)
          echo "version_id=${VERSION_ID}" >> "$GITHUB_OUTPUT"
          echo "deploy_url=${DEPLOY_URL}" >> "$GITHUB_OUTPUT"

      - name: Log approval + deploy to audit D1
        env:
          AUDIT_WORKER_URL: ${{ secrets.AUDIT_WORKER_URL }}
        run: |
          curl -fsSL -X POST "$AUDIT_WORKER_URL/log" \
            -H 'Content-Type: application/json' \
            -d "$(jq -n \
              --arg env production \
              --arg actor "$GITHUB_ACTOR" \
              --arg sha "$GITHUB_SHA" \
              --arg version_id "${{ steps.deploy.outputs.version_id }}" \
              --arg url "${{ steps.deploy.outputs.deploy_url }}" \
              --arg action deployed \
              '{env:$env,actor:$actor,sha:$sha,version_id:$version_id,deploy_url:$url,action:$action}')"
```

---

## Section 3 — D1 audit log Worker

```typescript
// workers/audit-logger/src/index.ts
import { Env } from './types';

export interface AuditEntry {
  env: string;
  actor: string;
  sha: string;
  version_id: string;
  deploy_url?: string;
  action: 'deployed' | 'approved' | 'rejected' | 'rolled_back';
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST' || new URL(request.url).pathname !== '/log') {
      return new Response('Not found', { status: 404 });
    }

    // Authenticate — shared secret in header
    const secret = <redacted-secret>'x-audit-secret');
    if (secret !== env.AUDIT_SECRET) {
      return new Response('Unauthorized', { status: 401 });
    }

    let entry: AuditEntry;
    try {
      entry = await request.json<AuditEntry>();
    } catch {
      return new Response('Invalid JSON', { status: 400 });
    }

    await env.DB.prepare(
      `INSERT INTO deploy_audit_log
         (created_at, env, actor, sha, version_id, deploy_url, action)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
    ).bind(
      new Date().toISOString(),
      entry.env,
      entry.actor,
      entry.sha,
      entry.version_id,
      entry.deploy_url ?? null,
      entry.action,
    ).run();

    return new Response(JSON.stringify({ ok: true }), {
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

D1 schema bootstrap:

```sql
-- migrations/0001_deploy_audit_log.sql
CREATE TABLE IF NOT EXISTS deploy_audit_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at  TEXT    NOT NULL,
  env         TEXT    NOT NULL,
  actor       TEXT    NOT NULL,
  sha         TEXT    NOT NULL,
  version_id  TEXT    NOT NULL,
  deploy_url  TEXT,
  action      TEXT    NOT NULL CHECK(action IN ('deployed','approved','rejected','rolled_back'))
);

CREATE INDEX idx_dal_env_created ON deploy_audit_log(env, created_at DESC);
```

```bash
# Apply migration to the bound D1 database
npx wrangler d1 migrations apply audit-logger-db
```

---

## Anti-patterns

- **Single workflow job with a sleep-based gate** — GitHub Environment reviewers are
  purpose-built for this; a `sleep 3600` polling pattern has no audit trail and breaks
  on runner timeouts.
- **Sharing the same API token for staging and production** — use separate tokens so a
  staging credential leak cannot touch production.
- **Writing to D1 from the Actions runner directly** — go through a Worker so the D1
  binding is encapsulated and the runner never needs database credentials.

## Gotchas

- The `environment` key on a job blocks the entire job — subsequent steps only run after
  approval, so you cannot add a "waiting for approval" notification step inside the same
  job; use a separate preceding job.
- `workflow_dispatch` with `promote_run_id` requires the caller to find the correct run
  ID (e.g. from the staging job URL). The Actions API `GET /repos/{owner}/{repo}/actions/runs/{run_id}/artifacts`
  can retrieve build artifacts from that run.
- GitHub Environments are only available on public repos or GitHub Team/Enterprise plans.

## Related

- `workers-deployment-slack-webhook-notification.md`
- `workers-version-binding-traffic-migration.md`
- D1 documentation: https://developers.cloudflare.com/d1/

## Sources

- GitHub Environments: https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment
- GitHub REST API — environments: https://docs.github.com/en/rest/deployments/environments
- Wrangler deploy environments: https://developers.cloudflare.com/workers/wrangler/environments/
