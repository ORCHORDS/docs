# Automatic Issue Assignment Based on Expertise/Workload with Workers + D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

New issues go unassigned for days because no one claims ownership. The team wants issues routed automatically to the contributor best matched by area of expertise, with workload balancing so no single person is overwhelmed, and a round-robin fallback when no expert is found.

## Context

A GitHub webhook fires `issues.opened`. A Cloudflare Worker receives it, looks up the issue labels against a D1 contributor-expertise table, scores candidates by current open-issue count (workload), picks the best match, calls the GitHub API to assign, and writes an audit log row to D1.

D1 is Cloudflare's SQLite-compatible edge database. Queries run in the same PoP as the Worker, keeping latency low.

## Solution

### wrangler.toml

```toml
name = "issue-assigner"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding = "DB"
database_name = "issue-assigner"
database_id = "<your-d1-database-id>"
```

### D1 schema

```sql
-- migrations/0001_schema.sql
CREATE TABLE IF NOT EXISTS contributors (
  login       TEXT PRIMARY KEY,
  expertise   TEXT NOT NULL,  -- comma-separated label names
  active      INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS assignment_log (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  issue_number  INTEGER NOT NULL,
  repo          TEXT NOT NULL,
  assignee      TEXT NOT NULL,
  reason        TEXT NOT NULL,  -- 'expertise' | 'workload' | 'round-robin'
  assigned_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_log_assignee ON assignment_log(assignee);
CREATE INDEX IF NOT EXISTS idx_log_repo ON assignment_log(repo);
```

### Types

```typescript
export interface Env {
  DB: D1Database;
  GH_TOKEN: string;         // secret
  GH_WEBHOOK_SECRET: string; // secret
}

interface Contributor {
  login: string;
  expertise: string;   // comma-separated
  active: number;
}

interface IssuePayload {
  action: string;
  issue: {
    number: number;
    title: string;
    labels: { name: string }[];
    repository_url: string;
  };
  repository: {
    full_name: string;
    name: string;
    owner: { login: string };
  };
}
```

### Webhook signature verification

```typescript
async function verifySignature(request: Request, secret: string): Promise<boolean> {
  const sig = request.headers.get("X-Hub-Signature-256") ?? "";
  const body = await request.clone().arrayBuffer();
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const mac = await crypto.subtle.sign("HMAC", key, body);
  const expected =
    "sha256=" +
    Array.from(new Uint8Array(mac))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
  // Constant-time comparison
  if (sig.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < sig.length; i++) diff |= sig.charCodeAt(i) ^ expected.charCodeAt(i);
  return diff === 0;
}
```

### Expertise matching

```typescript
async function pickAssignee(
  db: D1Database,
  repo: string,
  issueLabels: string[],
  ghToken: string,
  owner: string,
  repoName: string
): Promise<{ login: string; reason: string }> {
  // 1. Load active contributors
  const { results: contributors } = await db
    .prepare("SELECT login, expertise FROM contributors WHERE active = 1")
    .all<Contributor>();

  if (contributors.length === 0) throw new Error("No active contributors configured");

  // 2. Score by expertise overlap
  const scored = contributors.map((c) => {
    const expertiseTags = c.expertise.split(",").map((t) => t.trim().toLowerCase());
    const overlap = issueLabels.filter((l) => expertiseTags.includes(l.toLowerCase())).length;
    return { login: c.login, overlap };
  });

  const maxOverlap = Math.max(...scored.map((s) => s.overlap));

  // 3. If there are expertise matches, pick the one with the lowest workload
  if (maxOverlap > 0) {
    const experts = scored.filter((s) => s.overlap === maxOverlap).map((s) => s.login);
    const winner = await pickLowestWorkload(db, repo, experts, ghToken, owner, repoName);
    return { login: winner, reason: "expertise" };
  }

  // 4. Workload-based fallback — pick least-loaded overall
  const allLogins = contributors.map((c) => c.login);
  const winner = await pickLowestWorkload(db, repo, allLogins, ghToken, owner, repoName);
  return { login: winner, reason: "workload" };
}

async function pickLowestWorkload(
  db: D1Database,
  repo: string,
  logins: string[],
  ghToken: string,
  owner: string,
  repoName: string
): Promise<string> {
  // Fetch open issue counts from GitHub for each candidate
  const counts = await Promise.all(
    logins.map(async (login) => {
      const res = await fetch(
        `https://api.github.com/repos/${owner}/${repoName}/issues?assignee=${login}&state=open&per_page=1`,
        {
          headers: {
            Authorization: `Bearer ${ghToken}`,
            Accept: "application/vnd.github+json",
          },
        }
      );
      const link = res.headers.get("Link") ?? "";
      const m = link.match(/page=(\d+)>; rel="last"/);
      return { login, count: m ? parseInt(m[1], 10) : 0 };
    })
  );

  counts.sort((a, b) => a.count - b.count);
  return counts[0].login;
}
```

### Assignment via GitHub API

```typescript
async function assignIssue(
  owner: string,
  repo: string,
  issueNumber: number,
  login: string,
  ghToken: string
): Promise<void> {
  const res = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/issues/${issueNumber}`,
    {
      method: "PATCH",
      headers: {
        Authorization: `Bearer ${ghToken}`,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ assignees: [login] }),
    }
  );
  if (!res.ok) throw new Error(`GitHub assign failed: ${res.status} ${await res.text()}`);
}
```

### Audit log write

```typescript
async function logAssignment(
  db: D1Database,
  repo: string,
  issueNumber: number,
  assignee: string,
  reason: string
): Promise<void> {
  await db
    .prepare(
      "INSERT INTO assignment_log (issue_number, repo, assignee, reason, assigned_at) VALUES (?, ?, ?, ?, ?)"
    )
    .bind(issueNumber, repo, assignee, reason, new Date().toISOString())
    .run();
}
```

### Worker entry point

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });

    const valid = await verifySignature(request, env.GH_WEBHOOK_SECRET);
    if (!valid) return new Response("Unauthorized", { status: 401 });

    const payload: IssuePayload = await request.json();
    if (payload.action !== "opened") return new Response("ignored", { status: 200 });

    const { issue, repository } = payload;
    const issueLabels = issue.labels.map((l) => l.name);
    const owner = repository.owner.login;
    const repoName = repository.name;
    const repoFull = repository.full_name;

    try {
      const { login, reason } = await pickAssignee(
        env.DB,
        repoFull,
        issueLabels,
        env.GH_TOKEN,
        owner,
        repoName
      );
      await assignIssue(owner, repoName, issue.number, login, env.GH_TOKEN);
      await logAssignment(env.DB, repoFull, issue.number, login, reason);
      return Response.json({ assigned: login, reason });
    } catch (err) {
      console.error(err);
      return new Response("Internal error", { status: 500 });
    }
  },
} satisfies ExportedHandler<Env>;
```

## Implementation Details

- The round-robin fallback is implicit: when all logins have equal workload (e.g., all zero), `counts[0]` is the first alphabetically after the sort is stable — seed the `contributors` table in a deliberate order to control the round-robin sequence.
- The workload query hits GitHub API rather than D1 so it reflects issues opened via UI or other automations, not just the ones this Worker handled.
- D1 write latency is typically <10 ms within the same Cloudflare PoP. Use `ctx.waitUntil(logAssignment(...))` to avoid blocking the response if audit latency matters.

## Anti-patterns

- **Do not store workload counts in D1 as a cache.** They go stale. Always fetch live from GitHub.
- **Do not assign to a bot account.** Filter out accounts with `[bot]` suffix before passing to `pickAssignee`.
- **Do not skip webhook signature verification.** Anyone who can post to the Worker URL can trigger arbitrary assignments.

## Gotchas

- GitHub's `PATCH /issues/{number}` replaces the entire assignees list. If the issue was already assigned (e.g., by the author), the auto-assignment overwrites it. Add a guard: skip if `issue.assignees.length > 0`.
- D1 `INTEGER` columns in SQLite accept any value; TypeScript types are advisory only. Validate `active` before use.
- Running `wrangler d1 migrations apply` requires the `database_id` to be set in `wrangler.toml`.

## Verification

```bash
# Apply migrations
npx wrangler d1 migrations apply issue-assigner --local

# Seed a contributor
npx wrangler d1 execute issue-assigner --local \
  --command "INSERT INTO contributors (login, expertise) VALUES ('alice', 'bug,performance')"

# Simulate a webhook locally with curl
curl -X POST http://localhost:8787 \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: sha256=<computed>" \
  --data '{"action":"opened","issue":{"number":42,"title":"crash","labels":[{"name":"bug"}],"repository_url":""},"repository":{"full_name":"org/repo","name":"repo","owner":{"login":"org"}}}'

# Check audit log
npx wrangler d1 execute issue-assigner --local \
  --command "SELECT * FROM assignment_log ORDER BY id DESC LIMIT 5"
```

## Related

- workers-github-issue-webhook-router
- workers-issue-sla-tracker-d1
- workers-issue-metrics-analytics-engine

## Sources

- https://developers.cloudflare.com/d1/
- https://docs.github.com/en/rest/issues/issues#update-an-issue
- https://docs.github.com/en/webhooks/webhook-events-and-payloads#issues
