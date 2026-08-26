# GitHub Issue Auto-Triage Bot via Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

New GitHub issues pile up unlabelled and unassigned. Junior contributors do not know where to route reports. Stale issues linger for months without follow-up. You need a bot that receives GitHub webhooks, classifies issues by keyword, auto-assigns them to the right team, detects duplicates, closes stale issues on a schedule, and tracks response-time SLA in Analytics Engine.

## Context

A Cloudflare Worker acts as the GitHub webhook endpoint. Label-to-team mappings live in KV for fast, zero-latency lookups without a database round-trip. Duplicate detection uses a simple Jaccard similarity check against the titles of recently opened issues fetched from the GitHub API. Stale issue closing runs as a Cron Trigger. Response-time SLA events (first human comment latency) are written to Analytics Engine for Grafana dashboards.

## Solution

```typescript
// workers-triage-bot/src/index.ts
export interface Env {
  TRIAGE_KV: KVNamespace;
  GITHUB_WEBHOOK_SECRET: string;
  GITHUB_TOKEN: string;
  REPO_OWNER: string;
  REPO_NAME: string;
  ANALYTICS: AnalyticsEngineDataset;
}

// ---------------------------------------------------------------------------
// Webhook signature verification
// ---------------------------------------------------------------------------
async function verifySignature(req: Request, secret: string): Promise<boolean> {
  const sig = req.headers.get('X-Hub-Signature-256');
  if (!sig) return false;
  const body = await req.clone().arrayBuffer();
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const mac = await crypto.subtle.sign('HMAC', key, body);
  const hex = 'sha256=' + Array.from(new Uint8Array(mac))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
  return hex === sig;
}

// ---------------------------------------------------------------------------
// Label classification via keyword matching
// ---------------------------------------------------------------------------
const KEYWORD_LABEL_MAP: Array<{ pattern: RegExp; label: string }> = [
  { pattern: /crash|panic|fatal|segfault/i, label: 'type:crash' },
  { pattern: /performance|slow|latency|timeout/i, label: 'type:performance' },
  { pattern: /security|xss|injection|cve|vuln/i, label: 'type:security' },
  { pattern: /typo|doc|readme|changelog/i, label: 'type:docs' },
  { pattern: /feature|request|enhancement|rfe/i, label: 'type:feature' },
  { pattern: /regression|broke|worked before/i, label: 'type:regression' },
];

function classifyIssue(title: string, body: string): string[] {
  const text = `${title} ${body}`;
  const labels: string[] = [];
  for (const { pattern, label } of KEYWORD_LABEL_MAP) {
    if (pattern.test(text)) labels.push(label);
  }
  return labels.length ? labels : ['type:needs-triage'];
}

// ---------------------------------------------------------------------------
// Team assignment from KV
// ---------------------------------------------------------------------------
async function resolveAssignees(env: Env, labels: string[]): Promise<string[]> {
  const assignees = new Set<string>();
  for (const label of labels) {
    const team = await env.TRIAGE_KV.get(`label-team:${label}`);
    if (team) {
      // KV value is a comma-separated list of GitHub usernames
      team.split(',').map(u => u.trim()).forEach(u => assignees.add(u));
    }
  }
  return [...assignees].slice(0, 10); // GitHub max 10 assignees
}

// ---------------------------------------------------------------------------
// Duplicate detection via Jaccard similarity on title tokens
// ---------------------------------------------------------------------------
function tokenise(text: string): Set<string> {
  return new Set(text.toLowerCase().replace(/[^a-z0-9 ]/g, ' ').split(/\s+/).filter(Boolean));
}

function jaccard(a: Set<string>, b: Set<string>): number {
  const intersection = [...a].filter(x => b.has(x)).length;
  const union = new Set([...a, ...b]).size;
  return union === 0 ? 0 : intersection / union;
}

async function findDuplicate(
  env: Env,
  newTitle: string,
  newIssueNumber: number,
): Promise<number | null> {
  const res = await fetch(
    `https://api.github.com/repos/${env.REPO_OWNER}/${env.REPO_NAME}/issues?state=open&per_page=50`,
    { headers: { Authorization: `Bearer ${env.GITHUB_TOKEN}`, 'User-Agent': 'triage-bot/1.0' } },
  );
  const issues: Array<{ number: number; title: string }> = await res.json();
  const newTokens = tokenise(newTitle);

  for (const issue of issues) {
    if (issue.number === newIssueNumber) continue;
    const sim = jaccard(newTokens, tokenise(issue.title));
    if (sim >= 0.6) return issue.number;
  }
  return null;
}

// ---------------------------------------------------------------------------
// GitHub API helpers
// ---------------------------------------------------------------------------
async function githubPatch(env: Env, path: string, body: unknown) {
  return fetch(`https://api.github.com/repos/${env.REPO_OWNER}/${env.REPO_NAME}${path}`, {
    method: 'PATCH',
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      'Content-Type': 'application/json',
      'User-Agent': 'triage-bot/1.0',
    },
    body: JSON.stringify(body),
  });
}

async function addLabels(env: Env, issueNumber: number, labels: string[]) {
  await fetch(
    `https://api.github.com/repos/${env.REPO_OWNER}/${env.REPO_NAME}/issues/${issueNumber}/labels`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        'Content-Type': 'application/json',
        'User-Agent': 'triage-bot/1.0',
      },
      body: JSON.stringify({ labels }),
    },
  );
}

async function addAssignees(env: Env, issueNumber: number, assignees: string[]) {
  if (!assignees.length) return;
  await fetch(
    `https://api.github.com/repos/${env.REPO_OWNER}/${env.REPO_NAME}/issues/${issueNumber}/assignees`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        'Content-Type': 'application/json',
        'User-Agent': 'triage-bot/1.0',
      },
      body: JSON.stringify({ assignees }),
    },
  );
}

async function addComment(env: Env, issueNumber: number, body: string) {
  await fetch(
    `https://api.github.com/repos/${env.REPO_OWNER}/${env.REPO_NAME}/issues/${issueNumber}/comments`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        'Content-Type': 'application/json',
        'User-Agent': 'triage-bot/1.0',
      },
      body: JSON.stringify({ body }),
    },
  );
}

// ---------------------------------------------------------------------------
// Analytics Engine: SLA write
// ---------------------------------------------------------------------------
function recordSlaEvent(
  env: Env,
  issueNumber: number,
  event: 'opened' | 'first_response',
  elapsedMs?: number,
) {
  env.ANALYTICS.writeDataPoint({
    indexes: [String(issueNumber)],
    blobs: [event],
    doubles: [elapsedMs ?? 0],
  });
}

// ---------------------------------------------------------------------------
// Webhook handler
// ---------------------------------------------------------------------------
async function handleWebhook(req: Request, env: Env): Promise<Response> {
  const valid = await verifySignature(req, env.GITHUB_WEBHOOK_SECRET);
  if (!valid) return new Response('Forbidden', { status: 403 });

  const event = req.headers.get('X-GitHub-Event');
  const payload = await req.json<any>();

  if (event === 'issues' && payload.action === 'opened') {
    const issue = payload.issue;
    const { number, title, body } = issue;

    // Classify and label
    const labels = classifyIssue(title, body ?? '');
    await addLabels(env, number, labels);

    // Assign
    const assignees = await resolveAssignees(env, labels);
    await addAssignees(env, number, assignees);

    // Duplicate detection
    const dupNumber = await findDuplicate(env, title, number);
    if (dupNumber) {
      await addComment(
        env,
        number,
        `This issue appears to be a duplicate of #${dupNumber}. Closing as duplicate.`,
      );
      await githubPatch(env, `/issues/${number}`, { state: 'closed', state_reason: 'duplicate' });
      await addLabels(env, number, ['duplicate']);
    }

    // Record SLA start in KV
    await env.TRIAGE_KV.put(`sla:opened:${number}`, String(Date.now()), { expirationTtl: 86400 * 30 });
    recordSlaEvent(env, number, 'opened');
  }

  if (event === 'issue_comment' && payload.action === 'created') {
    const issue = payload.issue;
    const commenter: string = payload.comment.user.login;
    // Only count non-bot, non-author comments as first response
    if (!commenter.includes('[bot]') && commenter !== issue.user.login) {
      const openedAt = await env.TRIAGE_KV.get(`sla:opened:${issue.number}`);
      if (openedAt && !(await env.TRIAGE_KV.get(`sla:responded:${issue.number}`))) {
        const elapsedMs = Date.now() - Number(openedAt);
        recordSlaEvent(env, issue.number, 'first_response', elapsedMs);
        await env.TRIAGE_KV.put(`sla:responded:${issue.number}`, '1', { expirationTtl: 86400 * 30 });
      }
    }
  }

  return new Response('OK');
}

// ---------------------------------------------------------------------------
// Stale issue closer (cron)
// ---------------------------------------------------------------------------
async function closeStaleIssues(env: Env) {
  const staleDays = 60;
  const since = new Date(Date.now() - staleDays * 86400_000).toISOString();
  const res = await fetch(
    `https://api.github.com/repos/${env.REPO_OWNER}/${env.REPO_NAME}/issues` +
    `?state=open&sort=updated&direction=asc&per_page=30`,
    { headers: { Authorization: `Bearer ${env.GITHUB_TOKEN}`, 'User-Agent': 'triage-bot/1.0' } },
  );
  const issues: Array<{ number: number; updated_at: string; labels: Array<{ name: string }> }> =
    await res.json();

  for (const issue of issues) {
    if (new Date(issue.updated_at) < new Date(since)) {
      const hasExemption = issue.labels.some(l => l.name === 'no-stale');
      if (!hasExemption) {
        await addComment(
          env,
          issue.number,
          `This issue has been inactive for ${staleDays} days and is being closed as stale. ` +
          `Reopen if still relevant.`,
        );
        await githubPatch(env, `/issues/${issue.number}`, {
          state: 'closed',
          state_reason: 'not_planned',
        });
        await addLabels(env, issue.number, ['stale']);
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    if (req.method === 'POST' && url.pathname === '/webhook') {
      return handleWebhook(req, env);
    }
    return new Response('Not found', { status: 404 });
  },

  async scheduled(_event: ScheduledEvent, env: Env) {
    await closeStaleIssues(env);
  },
};
```

**KV seed values (label-to-team mapping):**

```bash
wrangler kv key put --binding TRIAGE_KV "label-team:type:crash"       "alice,bob"
wrangler kv key put --binding TRIAGE_KV "label-team:type:performance" "carol"
wrangler kv key put --binding TRIAGE_KV "label-team:type:security"    "dave,eve"
wrangler kv key put --binding TRIAGE_KV "label-team:type:docs"        "frank"
wrangler kv key put --binding TRIAGE_KV "label-team:type:feature"     "grace"
```

## Implementation Details

- Webhook signature uses `crypto.subtle` HMAC-SHA-256 so no external dependency is needed.
- `classifyIssue` is intentionally O(patterns × text-length) — acceptable for single-issue triage events.
- Jaccard similarity is computed at triage time against at most 50 open issues to avoid GitHub API pagination cost.
- The `sla:opened` KV key uses a 30-day TTL so closed and long-resolved issues do not accumulate.
- Analytics Engine `writeDataPoint` is non-blocking; the Worker does not await the write to avoid latency.
- The stale closer processes at most 30 issues per cron run to stay within GitHub's rate limits.

## Anti-patterns

- **Fetching all issues for duplicate detection.** Paginating hundreds of pages per webhook event will exhaust rate limits. Cap at 50 recent issues.
- **Assigning to teams rather than individuals.** GitHub's issue API accepts only user logins, not team slugs — store individual usernames in KV.
- **Closing stale issues without a warning comment.** Always leave a comment so reporters can reopen with context.
- **Trusting the webhook payload without signature verification.** Any actor can POST to your endpoint without the HMAC check.

## Gotchas

- GitHub may send duplicate `issues.opened` events during webhook retries. Guard re-classification by checking whether labels already exist before adding.
- `X-Hub-Signature-256` is absent on GitHub App installations using JWT auth — verify the installation token instead.
- `state_reason` is required when closing via the REST API as of GitHub API v3 2022-11 — omitting it returns a validation error.
- Analytics Engine data has a ~60-second ingestion latency; do not use it for real-time dashboards.

## Verification

1. POST a synthetic `issues.opened` webhook payload with `title: "app crashes on startup"` and assert the Worker adds `type:crash` and the correct assignee.
2. POST a second webhook with a near-identical title (Jaccard ≥ 0.6). Assert the Worker closes the new issue and labels it `duplicate`.
3. Check KV for `sla:opened:<number>` — should exist with a recent timestamp.
4. POST an `issue_comment.created` payload from a non-author. Assert `sla:responded:<number>` appears in KV and Analytics Engine receives a data point with `first_response` blob.
5. Run `wrangler dev --test-scheduled` to trigger `closeStaleIssues` against a local fixture and verify the stale comment and `PATCH` call are emitted.

## Related

- `workers-sla-breach-auto-escalation.md` — SLA enforcement for support tickets
- `workers-postmortem-generator.md` — generating postmortems from incident issues
- `workers-bug-reproduction-snapshot.md` — capturing bug reproduction context

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/kv/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://docs.github.com/en/developers/webhooks-and-events/webhooks/securing-your-webhooks
- https://docs.github.com/en/rest/issues/issues#update-an-issue
