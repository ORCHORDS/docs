# Cross-Repository Issue Linking Bot with Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Issues in one repository reference issues in another (`org/other-repo#42`) but GitHub only auto-links within the same repo. Teams lose track of cross-repo dependencies, cannot see bidirectional relationships, and have no way to detect broken references when a linked issue closes.

## Context

A Worker listens to `issues.opened`, `issues.edited`, and `issues.closed` webhooks. On open/edit it scans the body for `org/repo#number` patterns, posts a linking comment on both sides, and records the relationship in D1. On close it checks the D1 graph for outbound links and comments on any open issues that reference the now-closed issue.

## Solution

### wrangler.toml

```toml
name = "cross-repo-linker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding = "DB"
database_name = "cross-repo-linker"
database_id = "<your-d1-database-id>"

[vars]
GH_ORG = "orchords"
```

### D1 schema

```sql
-- migrations/0001_schema.sql
CREATE TABLE IF NOT EXISTS issue_links (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  source_repo    TEXT NOT NULL,
  source_number  INTEGER NOT NULL,
  target_repo    TEXT NOT NULL,
  target_number  INTEGER NOT NULL,
  detected_at    TEXT NOT NULL,
  UNIQUE(source_repo, source_number, target_repo, target_number)
);

CREATE INDEX IF NOT EXISTS idx_links_source ON issue_links(source_repo, source_number);
CREATE INDEX IF NOT EXISTS idx_links_target ON issue_links(target_repo, target_number);
```

### Types

```typescript
export interface Env {
  DB: D1Database;
  GH_TOKEN: string;
  GH_WEBHOOK_SECRET: string;
  GH_ORG: string;
}

interface IssueEvent {
  action: "opened" | "edited" | "closed" | "reopened" | string;
  issue: {
    number: number;
    body: string | null;
    html_url: string;
    state: string;
  };
  repository: {
    full_name: string;
    owner: { login: string };
    name: string;
  };
}

interface ParsedLink {
  repo: string;   // full_name e.g. "example-org/example-repo"
  number: number;
}
```

### Cross-repo mention detection

```typescript
function parseLinks(body: string, org: string): ParsedLink[] {
  // Matches: org/repo#42  or  org/repo #42  or  https://github.com/org/repo/issues/42
  const patterns = [
    // Short form: org/repo#number
    new RegExp(`(?<![/\\w])${escapeRegex(org)}/([\\w.-]+)#(\\d+)(?!\\w)`, "gi"),
    // GitHub URL form
    /https:\/\/github\.com\/([\w.-]+\/[\w.-]+)\/issues\/(\d+)/gi,
  ];

  const found = new Map<string, ParsedLink>();

  for (const pattern of patterns) {
    let m: RegExpExecArray | null;
    while ((m = pattern.exec(body)) !== null) {
      const repo = m[1].includes("/") ? m[1] : `${org}/${m[1]}`;
      const number = parseInt(m[2], 10);
      const key = `${repo}#${number}`;
      if (!found.has(key)) found.set(key, { repo, number });
    }
  }

  return Array.from(found.values());
}

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
```

### Comment injection helper

```typescript
async function postComment(
  repo: string,
  issueNumber: number,
  body: string,
  ghToken: string
): Promise<void> {
  const [owner, repoName] = repo.split("/");
  const res = await fetch(
    `https://api.github.com/repos/${owner}/${repoName}/issues/${issueNumber}/comments`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${ghToken}`,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ body }),
    }
  );
  if (!res.ok) console.error(`Comment failed on ${repo}#${issueNumber}: ${res.status}`);
}
```

### Link persistence and bidirectional comment

```typescript
async function processLinks(
  env: Env,
  sourceRepo: string,
  sourceNumber: number,
  sourceUrl: string,
  links: ParsedLink[]
): Promise<void> {
  for (const link of links) {
    if (link.repo === sourceRepo && link.number === sourceNumber) continue; // self-reference

    // Record A→B
    await env.DB
      .prepare(
        `INSERT OR IGNORE INTO issue_links
           (source_repo, source_number, target_repo, target_number, detected_at)
         VALUES (?, ?, ?, ?, ?)`
      )
      .bind(sourceRepo, sourceNumber, link.repo, link.number, new Date().toISOString())
      .run();

    // Record B→A for bidirectional graph
    await env.DB
      .prepare(
        `INSERT OR IGNORE INTO issue_links
           (source_repo, source_number, target_repo, target_number, detected_at)
         VALUES (?, ?, ?, ?, ?)`
      )
      .bind(link.repo, link.number, sourceRepo, sourceNumber, new Date().toISOString())
      .run();

    // Comment on the target issue pointing back
    await postComment(
      link.repo,
      link.number,
      `🔗 Cross-repo reference detected: ${sourceRepo}#${sourceNumber} mentions this issue.\n\n> View source issue`,
      env.GH_TOKEN
    );
  }
}
```

### Broken link detection on issue close

```typescript
async function handleClose(
  env: Env,
  closedRepo: string,
  closedNumber: number
): Promise<void> {
  // Find all issues that link TO this one
  const { results } = await env.DB
    .prepare(
      `SELECT source_repo, source_number FROM issue_links
       WHERE target_repo = ? AND target_number = ?`
    )
    .bind(closedRepo, closedNumber)
    .all<{ source_repo: string; source_number: number }>();

  for (const row of results) {
    // Check if the source issue is still open
    const [owner, repoName] = row.source_repo.split("/");
    const res = await fetch(
      `https://api.github.com/repos/${owner}/${repoName}/issues/${row.source_number}`,
      { headers: { Authorization: `Bearer ${env.GH_TOKEN}`, Accept: "application/vnd.github+json" } }
    );
    if (!res.ok) continue;
    const issue: any = await res.json();
    if (issue.state !== "open") continue;

    await postComment(
      row.source_repo,
      row.source_number,
      `⚠️ Linked issue **${closedRepo}#${closedNumber}** has been closed. Please review whether this issue is still valid or needs updating.`,
      env.GH_TOKEN
    );
  }
}
```

### Link graph endpoint

```typescript
async function handleGraph(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const repo = url.searchParams.get("repo");
  const number = parseInt(url.searchParams.get("number") ?? "", 10);
  if (!repo || !number) return new Response("Missing repo/number", { status: 400 });

  const { results } = await env.DB
    .prepare(
      `SELECT target_repo, target_number, detected_at FROM issue_links
       WHERE source_repo = ? AND source_number = ?
       ORDER BY detected_at ASC`
    )
    .bind(repo, number)
    .all<{ target_repo: string; target_number: number; detected_at: string }>();

  return Response.json({ source: `${repo}#${number}`, links: results });
}
```

### Worker entry point

```typescript
async function verifySignature(request: Request, secret: string): Promise<boolean> {
  const sig = request.headers.get("X-Hub-Signature-256") ?? "";
  const body = await request.clone().arrayBuffer();
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const mac = await crypto.subtle.sign("HMAC", key, body);
  const expected = "sha256=" + Array.from(new Uint8Array(mac))
    .map((b) => b.toString(16).padStart(2, "0")).join("");
  if (sig.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < sig.length; i++) diff |= sig.charCodeAt(i) ^ expected.charCodeAt(i);
  return diff === 0;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { pathname } = new URL(request.url);

    if (pathname === "/graph") return handleGraph(request, env);

    if (pathname === "/webhook" && request.method === "POST") {
      if (!(await verifySignature(request, env.GH_WEBHOOK_SECRET)))
        return new Response("Unauthorized", { status: 401 });

      const payload: IssueEvent = await request.json();
      const { action, issue, repository } = payload;
      const sourceRepo = repository.full_name;
      const sourceNumber = issue.number;

      if (action === "opened" || action === "edited") {
        const links = parseLinks(issue.body ?? "", env.GH_ORG);
        if (links.length > 0)
          await processLinks(env, sourceRepo, sourceNumber, issue.html_url, links);
      } else if (action === "closed") {
        await handleClose(env, sourceRepo, sourceNumber);
      }

      return Response.json({ ok: true });
    }

    return new Response("Not found", { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

## Implementation Details

- Both A→B and B→A rows are inserted so the graph endpoint can query from either side without a UNION.
- `INSERT OR IGNORE` prevents duplicate rows without needing a prior SELECT.
- The broken-link comment is only posted on open source issues to avoid noise on already-closed chains.
- The regex skips self-references (`link.repo === sourceRepo && link.number === sourceNumber`) to avoid the bot commenting on the issue that triggered it.

## Anti-patterns

- **Do not scan commit messages or PR bodies in this Worker.** Keep scope to issue bodies; add separate workers for other surfaces.
- **Do not post the backlink comment every time the issue is edited.** Track which links have already been commented on (store a `commented` flag in `issue_links`) to avoid duplicate comments.
- **Do not use string interpolation for D1 queries.** Always use `.bind()`.

## Gotchas

- GitHub markdown renders `org/repo#number` as a link only for the same org. The bot's comment is the only way to get a clickable backlink on the target side.
- If the target issue does not exist or is in a private repo the Worker cannot access, the comment POST returns 404. Log it and continue — do not throw.
- The `issues.edited` event fires on every edit including label changes. If `issue.body` is unchanged, the body diff is empty; check `payload.changes?.body` to skip unnecessary processing.

## Verification

```bash
# Apply schema
npx wrangler d1 migrations apply cross-repo-linker --local

# Inspect links for a given issue
npx wrangler d1 execute cross-repo-linker --local \
  --command "SELECT * FROM issue_links WHERE source_repo='example-org/example-repo' AND source_number=10"

# Link graph API
curl "http://localhost:8787/graph?repo=example-org/example-repo&number=10"
```

## Related

- workers-github-issue-webhook-router
- workers-issue-deduplication-embedding
- workers-issue-auto-assignment-d1

## Sources

- https://docs.github.com/en/webhooks/webhook-events-and-payloads#issues
- https://developers.cloudflare.com/d1/
- https://docs.github.com/en/rest/issues/comments
