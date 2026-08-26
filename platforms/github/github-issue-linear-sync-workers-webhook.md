# GitHub Issues → Linear Sync via Workers Webhook

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

The engineering team uses Linear for sprint planning but stakeholders file bugs in GitHub Issues. The two systems drift out of sync. You need to automatically create a corresponding Linear issue whenever a GitHub Issue is opened, and update it when the GitHub Issue is edited or closed — with idempotency so re-delivered webhooks do not create duplicate Linear issues.

## Context

A Cloudflare Worker acts as the webhook receiver. It validates the GitHub `X-Hub-Signature-256` header, reads the event payload, calls the Linear GraphQL API to create or update issues, and records the `github_issue_id ↔ linear_issue_id` mapping in a D1 table for idempotency. The Worker is stateless; all state lives in D1.

---

## Section 1: D1 Schema

```sql
-- migrations/0001_github_linear_mapping.sql
CREATE TABLE IF NOT EXISTS github_linear_mapping (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  github_issue_id INTEGER NOT NULL UNIQUE,
  linear_issue_id TEXT    NOT NULL,
  github_repo     TEXT    NOT NULL,
  synced_at       TEXT    NOT NULL DEFAULT (datetime('now')),
  created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_github_issue_id
  ON github_linear_mapping(github_issue_id);
```

## Section 2: Worker — Webhook Handler (TypeScript)

```typescript
// src/index.ts
import { verifyGitHubSignature } from './github';
import { syncIssueToLinear } from './linear';
import { Env } from './types';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const url = new URL(request.url);
    if (url.pathname !== '/webhook/github') {
      return new Response('Not Found', { status: 404 });
    }

    const body = await request.text();

    // 1. Validate GitHub signature
    const signature = request.headers.get('X-Hub-Signature-256') ?? '';
    const valid = await verifyGitHubSignature(body, signature, env.GITHUB_WEBHOOK_SECRET);
    if (!valid) {
      return new Response('Unauthorized', { status: 401 });
    }

    // 2. Parse payload
    const event = request.headers.get('X-GitHub-Event') ?? '';
    if (event !== 'issues') {
      return new Response('Ignored', { status: 200 });
    }

    const payload = JSON.parse(body) as GitHubIssuesPayload;
    const action = payload.action;

    if (!['opened', 'edited', 'closed', 'reopened'].includes(action)) {
      return new Response('Ignored', { status: 200 });
    }

    // 3. Sync to Linear (non-blocking — respond fast to GitHub)
    const ctx = { waitUntil: (p: Promise<unknown>) => p }; // simplified
    await syncIssueToLinear(payload, env);

    return new Response('OK', { status: 200 });
  },
};

export interface GitHubIssuesPayload {
  action: 'opened' | 'edited' | 'closed' | 'reopened';
  issue: {
    id: number;
    number: number;
    title: string;
    body: string | null;
    html_url: string;
    state: 'open' | 'closed';
    labels: Array<{ name: string }>;
  };
  repository: {
    full_name: string;
  };
}
```

## Section 3: GitHub Signature Verification

```typescript
// src/github.ts
export async function verifyGitHubSignature(
  body: string,
  signature: string,
  secret: string
): Promise<boolean> {
  if (!signature.startsWith('sha256=')) return false;

  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    'raw',
    encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );

  const signed = await crypto.subtle.sign('HMAC', key, encoder.encode(body));
  const expected = 'sha256=' + Array.from(new Uint8Array(signed))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');

  // Constant-time comparison
  if (expected.length !== signature.length) return false;
  let mismatch = 0;
  for (let i = 0; i < expected.length; i++) {
    mismatch |= expected.charCodeAt(i) ^ signature.charCodeAt(i);
  }
  return mismatch === 0;
}
```

## Section 4: Linear GraphQL Sync

```typescript
// src/linear.ts
import { GitHubIssuesPayload } from './index';
import { Env } from './types';

const LINEAR_API = 'https://api.linear.app/graphql';

async function linearRequest(query: string, variables: Record<string, unknown>, apiKey: string) {
  const res = await fetch(LINEAR_API, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: apiKey,
    },
    body: JSON.stringify({ query, variables }),
  });
  if (!res.ok) throw new Error(`Linear API error: ${res.status}`);
  const json = await res.json() as { data: unknown; errors?: unknown[] };
  if (json.errors?.length) throw new Error(`Linear GraphQL error: ${JSON.stringify(json.errors)}`);
  return json.data;
}

export async function syncIssueToLinear(
  payload: GitHubIssuesPayload,
  env: Env
): Promise<void> {
  const { issue, action, repository } = payload;

  // Idempotency: look up existing mapping
  const existing = await env.DB
    .prepare('SELECT linear_issue_id FROM github_linear_mapping WHERE github_issue_id = ?')
    .bind(issue.id)
    .first<{ linear_issue_id: string }>();

  if (action === 'opened' && !existing) {
    // Create new Linear issue
    const CREATE_ISSUE = `
      mutation CreateIssue($teamId: String!, <title>: String!, $description: String) {
        issueCreate(input: { teamId: $teamId, title: <title>, description: $description }) {
          issue { id identifier title }
        }
      }
    `;
    const description = [
      payload.issue.body ?? '',
      '',
      `---`,
      `GitHub Issue: ${issue.html_url}`,
      `Repo: ${repository.full_name}`,
    ].join('\n');

    const data = await linearRequest(CREATE_ISSUE, {
      teamId: env.LINEAR_TEAM_ID,
      title: `[GH#${issue.number}] ${issue.title}`,
      description,
    }, env.LINEAR_API_KEY) as { issueCreate: { issue: { id: string } } };

    const linearIssueId = data.issueCreate.issue.id;

    // Store mapping
    await env.DB
      .prepare(
        'INSERT INTO github_linear_mapping (github_issue_id, linear_issue_id, github_repo) VALUES (?, ?, ?)'
      )
      .bind(issue.id, linearIssueId, repository.full_name)
      .run();

    console.log(`Created Linear issue ${linearIssueId} for GH#${issue.number}`);
    return;
  }

  if (!existing) {
    console.warn(`No mapping for GitHub issue #${issue.number} — skipping ${action}`);
    return;
  }

  // Update existing Linear issue
  const linearIssueId = existing.linear_issue_id;

  if (action === 'edited') {
    const UPDATE_ISSUE = `
      mutation UpdateIssue($id: String!, <title>: String!, $description: String) {
        issueUpdate(id: $id, input: { title: <title>, description: $description }) {
          issue { id }
        }
      }
    `;
    await linearRequest(UPDATE_ISSUE, {
      id: linearIssueId,
      title: `[GH#${issue.number}] ${issue.title}`,
      description: issue.body ?? '',
    }, env.LINEAR_API_KEY);
  }

  if (action === 'closed') {
    const CANCEL_ISSUE = `
      mutation CancelIssue($id: String!, $stateId: String!) {
        issueUpdate(id: $id, input: { stateId: $stateId }) {
          issue { id }
        }
      }
    `;
    await linearRequest(CANCEL_ISSUE, {
      id: linearIssueId,
      stateId: env.LINEAR_CANCELLED_STATE_ID,
    }, env.LINEAR_API_KEY);
  }

  // Update synced_at
  await env.DB
    .prepare('UPDATE github_linear_mapping SET synced_at = datetime(\'now\') WHERE linear_issue_id = ?')
    .bind(linearIssueId)
    .run();
}
```

## Section 5: Wrangler Config and GitHub Webhook Setup

```toml
# wrangler.toml
name = "github-linear-sync"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[d1_databases]]
binding = "DB"
database_name = "github-linear-sync"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[vars]
LINEAR_TEAM_ID = "TEAM_ID_HERE"
LINEAR_CANCELLED_STATE_ID = "STATE_ID_HERE"

# Secrets (set via: wrangler secret put <NAME>)
# GITHUB_WEBHOOK_SECRET
# LINEAR_API_KEY
```

```bash
# Register the webhook in GitHub (one-time setup)
gh api repos/{owner}/{repo}/hooks \
  --method POST \
  --field name=web \
  --field active=true \
  --field 'events[]=issues' \
  --field 'config[url]=https://github-linear-sync.example.workers.dev/webhook/github' \
  --field 'config[content_type]=json' \
  --field 'config[secret]=YOUR_SECRET'
```

## Anti-patterns

- **Skipping signature verification**: Any party that discovers the endpoint URL can inject fake issues. Always validate `X-Hub-Signature-256`.
- **Synchronous Linear calls blocking the response**: GitHub expects a webhook response within 10 seconds. Use `ctx.waitUntil()` for non-blocking execution in production.
- **No idempotency check**: GitHub re-delivers webhooks on failures. Without the D1 mapping table, each re-delivery creates a duplicate Linear issue.
- **Storing secrets in `wrangler.toml`**: Use `wrangler secret put` for API keys and webhook secrets. Never commit them.

## Gotchas

- The Linear API key must have `Issues: Write` scope. Team-scoped keys are more secure than workspace keys.
- `LINEAR_CANCELLED_STATE_ID` must be looked up from Linear's API — it is a UUID, not a human-readable string. Query `workflowStates { nodes { id name } }` in the Linear GraphQL playground.
- GitHub issues created by bots (e.g., Dependabot) will also trigger the webhook. Filter by `payload.issue.user.type !== 'Bot'` to avoid noise.
- D1 `UNIQUE` constraint on `github_issue_id` provides a database-level idempotency guarantee as a safety net.

## Verification

```bash
# Replay a webhook payload locally with Miniflare
npx wrangler dev --local
curl -X POST http://localhost:8787/webhook/github \
  -H 'Content-Type: application/json' \
  -H 'X-GitHub-Event: issues' \
  -H 'X-Hub-Signature-256: sha256=<computed>' \
  -d @fixtures/github-issue-opened.json

# Verify mapping in local D1
npx wrangler d1 execute github-linear-sync --local \
  --command 'SELECT * FROM github_linear_mapping;'
```

## Related

- `documentation/categories/github/github-branch-protection-emergency-bypass-workers.md`
- `documentation/workers/workers-webhook-signature-validation.md`
- `documentation/d1/d1-idempotency-patterns.md`

## Sources

- https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries
- https://studio.apollographql.com/public/Linear-API/variant/current/home (Linear GraphQL schema)
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/runtime-apis/fetch-event/#waituntil
