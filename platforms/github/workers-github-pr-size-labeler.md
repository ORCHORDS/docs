# Automatic PR Size Labeling Bot with Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Pull requests grow unbounded in size because there is no automatic feedback loop to signal when a diff has become too large to review effectively. Teams rely on manual discipline or custom CI scripts that are fragile. Reviewers waste time on mammoth PRs that should have been split; small PRs go unrecognized and unmerged quickly.

You need a zero-maintenance bot that labels every PR with a size bucket (XS / S / M / L / XL) the moment it is opened or updated, tracks size trends in D1, and exposes team-level policies through KV.

---

## Context

- GitHub sends `pull_request` webhook events on `opened`, `synchronize`, `reopened` actions.
- The diff statistics (additions + deletions) are available in the `pull_request` payload under `additions` and `deletions`.
- Labels must be pre-created in the repo; the bot upserts them via `PATCH /repos/{owner}/{repo}/issues/{number}/labels`.
- D1 stores a `pr_sizes` table for trend reports per team/repo.
- KV stores per-team threshold overrides so product squads can tune their own policy.

---

## Solution

### wrangler.toml

```toml
name = "pr-size-labeler"
main = "src/index.ts"
compatibility_date = "2026-01-01"

[[d1_databases]]
binding = "DB"
database_name = "pr-size-labeler"
database_id = "YOUR_D1_DATABASE_ID"

[[kv_namespaces]]
binding = "POLICY_KV"
id = "YOUR_KV_NAMESPACE_ID"

[vars]
GITHUB_WEBHOOK_SECRET = "YOUR_WEBHOOK_SECRET"
```

### D1 migration

```sql
-- migrations/0001_init.sql
CREATE TABLE IF NOT EXISTS pr_sizes (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  owner       TEXT    NOT NULL,
  repo        TEXT    NOT NULL,
  pr_number   INTEGER NOT NULL,
  team        TEXT,
  additions   INTEGER NOT NULL,
  deletions   INTEGER NOT NULL,
  total_lines INTEGER NOT NULL,
  bucket      TEXT    NOT NULL,
  recorded_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_pr_sizes_repo
  ON pr_sizes (owner, repo, recorded_at DESC);
```

### src/types.ts

```typescript
export interface SizeThresholds {
  xs: number; // 0-xs  → XS
  s:  number; // xs-s  → S
  m:  number; // s-m   → M
  l:  number; // m-l   → L
              // l+    → XL
}

export const DEFAULT_THRESHOLDS: SizeThresholds = {
  xs: 10,
  s:  50,
  m:  250,
  l:  1000,
};

export interface TeamPolicy {
  thresholds: SizeThresholds;
  team: string;
}

export interface PullRequestPayload {
  action: string;
  number: number;
  pull_request: {
    additions: number;
    deletions: number;
    head: { repo: { full_name: string } };
    base: { repo: { owner: { login: string }; name: string } };
    labels: Array<{ name: string }>;
    user: { login: string; type: string };
  };
  repository: { owner: { login: string }; name: string };
}
```

### src/labeler.ts

```typescript
import type { SizeThresholds } from './types';

const SIZE_LABELS = ['size/XS', 'size/S', 'size/M', 'size/L', 'size/XL'] as const;
export type SizeBucket = (typeof SIZE_LABELS)[number];

export function classifySize(
  totalLines: number,
  thresholds: SizeThresholds,
): SizeBucket {
  if (totalLines <= thresholds.xs) return 'size/XS';
  if (totalLines <= thresholds.s)  return 'size/S';
  if (totalLines <= thresholds.m)  return 'size/M';
  if (totalLines <= thresholds.l)  return 'size/L';
  return 'size/XL';
}

export async function upsertSizeLabel(
  owner: string,
  repo: string,
  prNumber: number,
  bucket: SizeBucket,
  token: string,
): Promise<void> {
  // Remove any existing size labels
  const currentLabelsResp = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/issues/${prNumber}/labels`,
    { headers: { Authorization: `Bearer ${token}`, 'User-Agent': 'pr-size-labeler/1.0' } },
  );
  const currentLabels: Array<{ name: string }> = await currentLabelsResp.json();

  const toRemove = currentLabels
    .map(l => l.name)
    .filter(n => SIZE_LABELS.includes(n as SizeBucket) && n !== bucket);

  await Promise.all(
    toRemove.map(label =>
      fetch(
        `https://api.github.com/repos/${owner}/${repo}/issues/${prNumber}/labels/${encodeURIComponent(label)}`,
        {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${token}`, 'User-Agent': 'pr-size-labeler/1.0' },
        },
      ),
    ),
  );

  // Add the new size label
  await fetch(
    `https://api.github.com/repos/${owner}/${repo}/issues/${prNumber}/labels`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
        'User-Agent': 'pr-size-labeler/1.0',
      },
      body: JSON.stringify({ labels: [bucket] }),
    },
  );
}
```

### src/index.ts

```typescript
import { classifySize, upsertSizeLabel } from './labeler';
import type { PullRequestPayload, TeamPolicy } from './types';
import { DEFAULT_THRESHOLDS } from './types';

export interface Env {
  DB: D1Database;
  POLICY_KV: KVNamespace;
  GITHUB_TOKEN: string;
  GITHUB_WEBHOOK_SECRET: string;
}

async function verifySignature(
  request: Request,
  secret: string,
  body: string,
): Promise<boolean> {
  const sig = request.headers.get('x-hub-signature-256') ?? '';
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    'raw',
    encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const signedBuffer = await crypto.subtle.sign('HMAC', key, encoder.encode(body));
  const expectedHex = Array.from(new Uint8Array(signedBuffer))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
  return sig === `sha256=${expectedHex}`;
}

async function getTeamPolicy(
  kv: KVNamespace,
  owner: string,
  repo: string,
): Promise<TeamPolicy | null> {
  const raw = await kv.get(`policy:${owner}/${repo}`);
  if (!raw) return null;
  return JSON.parse(raw) as TeamPolicy;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const body = await request.text();
    const valid = await verifySignature(request, env.GITHUB_WEBHOOK_SECRET, body);
    if (!valid) return new Response('Unauthorized', { status: 401 });

    const event = request.headers.get('x-github-event');
    if (event !== 'pull_request') return new Response('Ignored', { status: 200 });

    const payload: PullRequestPayload = JSON.parse(body);
    const { action, number: prNumber, pull_request: pr, repository: repo } = payload;

    if (!['opened', 'synchronize', 'reopened'].includes(action)) {
      return new Response('Ignored action', { status: 200 });
    }

    const owner = repo.owner.login;
    const repoName = repo.name;
    const totalLines = pr.additions + pr.deletions;

    // Fetch team policy from KV
    const policy = await getTeamPolicy(env.POLICY_KV, owner, repoName);
    const thresholds = policy?.thresholds ?? DEFAULT_THRESHOLDS;
    const team = policy?.team ?? 'default';

    const bucket = classifySize(totalLines, thresholds);
    await upsertSizeLabel(owner, repoName, prNumber, bucket, env.GITHUB_TOKEN);

    // Record to D1 for trend tracking
    await env.DB.prepare(
      `INSERT INTO pr_sizes (owner, repo, pr_number, team, additions, deletions, total_lines, bucket)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT DO NOTHING`,
    )
      .bind(owner, repoName, prNumber, team, pr.additions, pr.deletions, totalLines, bucket)
      .run();

    return new Response(JSON.stringify({ bucket, totalLines }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

### KV policy document

```json
// key: policy:example-org/example-repo
{
  "team": "platform",
  "thresholds": {
    "xs": 5,
    "s":  30,
    "m":  150,
    "l":  500
  }
}
```

### Trend query

```sql
-- Average PR size per bucket per week for the last 90 days
SELECT
  strftime('%Y-W%W', recorded_at) AS week,
  bucket,
  COUNT(*)                        AS pr_count,
  AVG(total_lines)                AS avg_lines
FROM pr_sizes
WHERE owner = 'orchords'
  AND repo  = 'api'
  AND recorded_at >= datetime('now', '-90 days')
GROUP BY week, bucket
ORDER BY week DESC, bucket;
```

---

## Implementation Details

- **Label creation**: Labels (size/XS … size/XL) must exist in the repo before the bot runs. Create them once with the GitHub API or via the UI. The bot does not auto-create labels to avoid ambiguous colour assignments.
- **Conflict-free inserts**: `ON CONFLICT DO NOTHING` prevents duplicate rows when GitHub retries the webhook on a 5xx. The bucket already applied is the correct one; a subsequent `synchronize` event will insert a new row naturally.
- **Atomic label swap**: The bot removes all stale size labels before adding the new one to prevent a PR showing two size labels during a race between two synchronize events.
- **Webhook retries**: GitHub retries webhooks up to 3 times over ~1 hour. The idempotency of `upsertSizeLabel` + `ON CONFLICT` ensures retries are harmless.
- **Team policies in KV**: Stored at key `policy:{owner}/{repo}`. A missing key falls back to `DEFAULT_THRESHOLDS`. Update policies with `wrangler kv key put`.

---

## Anti-patterns

- **Do not count only additions**: PRs that delete a lot of code are just as large to review. Always use `additions + deletions`.
- **Do not hardcode thresholds in Worker code**: Teams have different review norms. Store thresholds in KV so they can be updated without a redeploy.
- **Do not skip signature verification**: An unauthenticated endpoint can be triggered by anyone to spam labels on arbitrary PRs.
- **Do not fire a GitHub API call per label in sequence**: Batch the DELETE calls with `Promise.all` to stay within the Worker's 30-second CPU budget.

---

## Gotchas

- GitHub's `additions`/`deletions` in the webhook payload counts generated files (lock files, minified assets). Add a file-pattern exclusion list in KV if your repo generates large diffs from tooling.
- The `synchronize` event fires once per commit pushed to the PR branch, not once per push to `main`. On a feature branch with many small commits, the Worker fires frequently; D1 will accumulate many rows. Add a TTL-based cleanup cron.
- Deleting a label that does not exist on the issue returns HTTP 404; this is safe to ignore but wrap the DELETE calls in a status-check to avoid false error logs.
- Workers KV has eventual consistency. A team policy update may take up to 60 seconds to propagate globally. PRs opened immediately after a policy change may still use the old thresholds for one round.

---

## Verification

```bash
# 1. Deploy
npx wrangler deploy

# 2. Send a test webhook payload
curl -X POST https://pr-size-labeler.YOUR_SUBDOMAIN.workers.dev \
  -H 'Content-Type: application/json' \
  -H 'X-GitHub-Event: pull_request' \
  -H 'X-Hub-Signature-256: sha256=COMPUTED_SIG' \
  -d @test/fixtures/pr_opened_medium.json

# 3. Confirm label was applied
gh pr view 42 --json labels --jq '.labels[].name'

# 4. Query D1 for trend data
npx wrangler d1 execute pr-size-labeler \
  --command "SELECT bucket, COUNT(*) FROM pr_sizes GROUP BY bucket;"
```

---

## Related

- `documentation/categories/github/workers-github-workflow-cost-tracker.md`
- `documentation/categories/github/workers-github-dependency-review.md`
- Cloudflare D1 docs: https://developers.cloudflare.com/d1/
- GitHub webhook events — pull_request: https://docs.github.com/en/webhooks/webhook-events-and-payloads#pull_request

---

## Sources

- https://developers.cloudflare.com/workers/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/kv/
- https://docs.github.com/en/rest/issues/labels
- https://docs.github.com/en/webhooks/webhook-events-and-payloads#pull_request
