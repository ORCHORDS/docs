# Using Workers Versions API Annotations for Deployment Traceability

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

After an error-rate spike you need to quickly determine which deployment introduced the regression. You want every `wrangler deploy` to carry a version tag, be queryable by that tag, and have its version ID written back to the GitHub commit so engineers can correlate Analytics Engine errors with a specific deploy without leaving the dashboard.

## Context

Cloudflare Workers Versions API records a new version entry for every deployment. You can attach human-readable annotations — `workers/message`, `workers/tag`, and custom keys — at deploy time using `--annotation`. After deployment, the REST API lets you list versions filtered by tag. A post-deploy script reads the latest version ID and posts it as a GitHub commit status, creating a bidirectional link between source control and the Workers version history.

Components:
- `wrangler deploy --annotation` for attaching metadata at deploy time
- REST API queries for version history by tag
- Post-deploy GitHub commit annotation script
- Analytics Engine correlation query linking error spikes to version IDs

## wrangler deploy with annotations and post-deploy script

```typescript
// scripts/deploy-annotated.ts
// Usage: npx tsx scripts/deploy-annotated.ts --tag v1.2.3 --env production
import { execSync } from 'node:child_process';

const ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID!;
const API_TOKEN = process.env.CLOUDFLARE_API_TOKEN!;
const GITHUB_TOKEN = process.env.GITHUB_TOKEN!;
const WORKER_NAME = process.env.WORKER_NAME ?? 'my-api-production';
const REPO = process.env.GITHUB_REPOSITORY!; // 'owner/repo'
const SHA = process.env.GITHUB_SHA!;

function parseArgs(): { tag: string; env: string } {
  const args = process.argv.slice(2);
  const tag = args[args.indexOf('--tag') + 1];
  const env = args[args.indexOf('--env') + 1] ?? 'production';
  if (!tag) throw new Error('--tag is required');
  return { tag, env };
}

async function wranglerDeploy(tag: string, env: string): Promise<void> {
  const message = `Deploy ${tag} to ${env} on ${new Date().toISOString()}`;
  execSync(
    [
      'npx wrangler deploy',
      `--env ${env}`,
      `--annotation "workers/tag=${tag}"`,
      `--annotation "workers/message=${message}"`,
      `--annotation "workers/env=${env}"`,
      `--annotation "git/sha=${SHA}"`,
      `--annotation "git/repo=${REPO}"`,
    ].join(' '),
    { stdio: 'inherit' }
  );
}

async function getLatestVersionId(): Promise<string> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/scripts/${WORKER_NAME}/versions?limit=1`,
    { headers: { Authorization: `Bearer ${API_TOKEN}` } }
  );
  const data = await res.json() as { result: { id: string }[] };
  const versionId = data.result[0]?.id;
  if (!versionId) throw new Error('No version found after deploy');
  return versionId;
}

async function annotateGitHubCommit(versionId: string, tag: string): Promise<void> {
  const [owner, repo] = REPO.split('/');
  // Create a GitHub commit status linking to the Cloudflare dashboard
  const res = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/statuses/${SHA}`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${GITHUB_TOKEN}`,
        'Content-Type': 'application/json',
        Accept: 'application/vnd.github+json',
      },
      body: JSON.stringify({
        state: 'success',
        target_url: `https://dash.cloudflare.com/${ACCOUNT_ID}/workers/scripts/${WORKER_NAME}/deployments`,
        description: `Workers version ${versionId} | tag: ${tag}`,
        context: 'cloudflare/workers-deploy',
      }),
    }
  );
  if (!res.ok) throw new Error(`GitHub status POST failed: ${await res.text()}`);
  console.log(`GitHub commit ${SHA} annotated with version ${versionId}`);
}

(async () => {
  const { tag, env } = parseArgs();
  console.log(`Deploying with tag=${tag} env=${env}`);
  await wranglerDeploy(tag, env);
  const versionId = await getLatestVersionId();
  console.log(`Deployed version: ${versionId}`);
  await annotateGitHubCommit(versionId, tag);
})().catch(err => { console.error(err); process.exit(1); });
```

## GitHub Actions integration

```yaml
# .github/workflows/deploy-tagged.yml
name: Annotated Deploy

on:
  push:
    tags: ['v*']

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'npm'

      - run: npm ci

      - name: Deploy with annotation
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          WORKER_NAME: my-api-production
          GITHUB_REPOSITORY: ${{ github.repository }}
          GITHUB_SHA: ${{ github.sha }}
        run: npx tsx scripts/deploy-annotated.ts --tag ${{ github.ref_name }} --env production
```

## Querying version history by tag via REST API

```typescript
// scripts/find-version-by-tag.ts
const ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID!;
const API_TOKEN = process.env.CLOUDFLARE_API_TOKEN!;
const WORKER_NAME = process.env.WORKER_NAME ?? 'my-api-production';
const targetTag = process.argv[2];

interface WorkerVersion {
  id: string;
  number: number;
  metadata: { created_on: string; source: string };
  annotations: Record<string, string>;
}

async function findVersionsByTag(tag: string): Promise<WorkerVersion[]> {
  let cursor: string | undefined;
  const matches: WorkerVersion[] = [];

  do {
    const params = new URLSearchParams({ limit: '100' });
    if (cursor) params.set('cursor', cursor);
    const res = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/scripts/${WORKER_NAME}/versions?${params}`,
      { headers: { Authorization: `Bearer ${API_TOKEN}` } }
    );
    const data = await res.json() as { result: WorkerVersion[]; result_info: { cursor?: string } };
    for (const v of data.result) {
      if (v.annotations?.['workers/tag'] === tag) matches.push(v);
    }
    cursor = data.result_info?.cursor;
  } while (cursor && matches.length === 0); // stop once found

  return matches;
}

(async () => {
  if (!targetTag) { console.error('Usage: find-version-by-tag.ts <tag>'); process.exit(1); }
  const versions = await findVersionsByTag(targetTag);
  console.log(JSON.stringify(versions, null, 2));
})().catch(err => { console.error(err); process.exit(1); });
```

## Correlating Analytics Engine errors with deploy events

```sql
-- Analytics Engine SQL — join error counts with deploy timestamps
-- Run in Workers Analytics Engine query API or wrangler analytics-engine query
SELECT
  toStartOfMinute(timestamp) AS minute,
  count() AS error_count
FROM workers_analytics
WHERE
  status_code >= 500
  AND timestamp >= toDateTime('2026-08-24 12:00:00')
  AND timestamp <= toDateTime('2026-08-24 14:00:00')
GROUP BY minute
ORDER BY minute
-- Overlay this with version created_on timestamps from the Versions API
-- to pinpoint which deploy correlated with the error spike
```

## Anti-patterns

- **Using only the Worker name to identify a deployment** — Worker names are mutable; version IDs and annotations are the stable audit trail.
- **Annotating after the fact via API edit** — annotations must be set at deploy time; the API does not support retroactive annotation updates on a version.
- **Not storing the version ID in CI artifacts** — if the deploy script is lost or the run expires, the version ID may be difficult to recover without querying the API.
- **Using annotation values that contain shell-special characters unescaped** — always quote annotation values in shell to avoid argument splitting.

## Gotchas

- The Workers Versions API is distinct from the Deployments API. Versions are created on each `wrangler deploy`; deployments represent which version is currently serving traffic. A version can exist without being the active deployment (e.g., after a rollback).
- `--annotation` keys must start with a namespace prefix followed by `/` (e.g., `workers/`, `git/`). Custom namespaces are allowed; bare keys without `/` are rejected.
- Version history pagination uses opaque cursors, not page numbers. Always follow the cursor until exhausted when scanning all versions.
- The GitHub commit status context (`cloudflare/workers-deploy`) must be unique per deployment target; using the same context for staging and production will overwrite each other on the same commit.

## Verification

```bash
# List the 5 most recent versions with their annotations
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/workers/scripts/my-api-production/versions?limit=5" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  | jq '.result[] | {id, annotations}'

# Find version by tag
npx tsx scripts/find-version-by-tag.ts v1.2.3

# Check GitHub commit status
gh api repos/example-org/example-repo/commits/$GITHUB_SHA/statuses \
  | jq '.[] | select(.context == "cloudflare/workers-deploy")'
```

## Related

- `workers-blue-green-deploy-traffic-split-kv.md`
- `wrangler-environments-staging-prod-promotion.md`
- `workers-gradual-rollout-percentage-kv-feature-flag.md`

## Sources

- Workers Versions API: https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/
- Wrangler deploy annotations: https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- GitHub Commit Statuses API: https://docs.github.com/en/rest/commits/statuses
- Analytics Engine SQL API: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
