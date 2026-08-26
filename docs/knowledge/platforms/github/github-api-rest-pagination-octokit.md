# GitHub REST API Pagination with Octokit and Cloudflare D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A GitHub REST API endpoint returns the first 30 items (default page size) and a `Link`
header pointing to subsequent pages. Scripts that call the API once silently miss data.
This article covers how to paginate correctly using the `Link` header directly, via
`octokit.paginate`, and how to store paginated results in a Cloudflare D1 database for
offline analysis or caching.

## Context

All GitHub REST list endpoints support pagination via `?page=N&per_page=100` query
parameters (maximum 100 items per page). The response includes a `Link` header with `rel`
values of `next`, `prev`, `first`, and `last`. The GitHub Octokit SDK provides a
`paginate` helper that follows these links automatically. In Cloudflare Workers and in
GitHub Actions scripts, raw `fetch` must handle the `Link` header manually.

---

## Manual Link-Header Pagination (Raw Fetch)

```typescript
// lib/paginate.ts — generic Link-header paginator
export async function* paginateGitHub<T>(
  initialUrl: string,
  token: string
): AsyncGenerator<T[]> {
  let url: string | null = initialUrl;

  while (url) {
    const res = await fetch(url, {
      headers: {
        Accept:        "application/vnd.github+json",
        Authorization: `Bearer ${token}`,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent":  "orchords-paginator/1.0",
      },
    });

    if (!res.ok) {
      const body = await res.text();
      throw new Error(`GitHub API ${res.status}: ${body}`);
    }

    const items = (await res.json()) as T[];
    yield items;

    // Parse the Link header for the `next` URL
    url = parseNextLink(res.headers.get("link"));
  }
}

function parseNextLink(linkHeader: string | null): string | null {
  if (!linkHeader) return null;
  // Link: <https://api.github.com/...?page=2>; rel="next", ...
  for (const part of linkHeader.split(",")) {
    const [urlPart, relPart] = part.trim().split(";");
    if (relPart?.trim() === `rel="next"`) {
      return urlPart.trim().slice(1, -1); // strip < >
    }
  }
  return null;
}
```

```typescript
// Usage: collect all open issues across pages
const issues: GitHubIssue[] = [];
const url = "https://api.github.com/repos/example-org/example-repo

for await (const page of paginateGitHub<GitHubIssue>(url, env.GITHUB_TOKEN)) {
  issues.push(...page);
}
console.log(`Total issues: ${issues.length}`);
```

---

## Octokit paginate() in GitHub Actions (actions/github-script)

```yaml
- name: Collect all PR reviews
  id: all-reviews
  uses: actions/github-script@v7
  with:
    script: |
      const reviews = await github.paginate(
        github.rest.pulls.listReviews,
        {
          owner:       context.repo.owner,
          repo:        context.repo.repo,
          pull_number: context.issue.number,
          per_page:    100,
        }
      );

      const approved = reviews.filter(r => r.state === 'APPROVED').length;
      const changes  = reviews.filter(r => r.state === 'CHANGES_REQUESTED').length;

      core.setOutput('approved-count', approved);
      core.setOutput('changes-count',  changes);
      core.info(`Reviews: ${approved} approved, ${changes} changes requested`);
```

`github.paginate` returns a flat array of all items across all pages. It handles the `Link`
header internally and respects rate limits by honouring `Retry-After` headers.

---

## Octokit Lazy Pagination with paginate.iterator()

For large result sets, materialising all pages into memory at once can OOM. Use the iterator
to process one page at a time:

```typescript
// In a Cloudflare Worker or Node.js script
import { Octokit } from "@octokit/rest";

const octokit = new Octokit({ auth: token });

for await (const page of octokit.paginate.iterator(
  octokit.rest.repos.listForOrg,
  { org: "orchords", type: "all", per_page: 100 }
)) {
  // page.data is the array of repos for this page
  await processReposPage(page.data);
}
```

`paginate.iterator` is available from `@octokit/rest ≥ 18`. Each iteration yields the raw
Octokit response `{ data, headers, status, url }`.

---

## Storing Paginated Results in D1

```typescript
// scripts/sync-issues.ts — run from GitHub Actions or a Cloudflare scheduled Worker
interface Issue {
  id:         number;
  number:     number;
  title:      string;
  state:      string;
  created_at: string;
  updated_at: string;
  html_url:   string;
}

export async function syncIssuesToD1(
  db: D1Database,
  token: string,
  owner: string,
  repo:  string
): Promise<number> {
  let total = 0;
  const url = `https://api.github.com/repos/${owner}/${repo}/issues` +
              `?state=all&per_page=100&sort=updated&direction=desc`;

  for await (const page of paginateGitHub<Issue>(url, token)) {
    if (page.length === 0) break;

    // Batch upsert — D1 supports up to 1 000 bindings per statement
    const placeholders = page
      .map(() => "(?, ?, ?, ?, ?, ?, ?)")
      .join(", ");

    const values = page.flatMap(i => [
      i.id, i.number, i.title, i.state,
      i.created_at, i.updated_at, i.html_url,
    ]);

    await db
      .prepare(
        `INSERT INTO github_issues
           (github_id, number, title, state, created_at, updated_at, html_url)
         VALUES ${placeholders}
         ON CONFLICT(github_id) DO UPDATE SET
           title      = excluded.title,
           state      = excluded.state,
           updated_at = excluded.updated_at`
      )
      .bind(...values)
      .run();

    total += page.length;
  }

  return total;
}
```

```sql
-- D1 schema
CREATE TABLE IF NOT EXISTS github_issues (
  github_id  INTEGER PRIMARY KEY,
  number     INTEGER NOT NULL,
  title      TEXT    NOT NULL,
  state      TEXT    NOT NULL,   -- 'open' | 'closed'
  created_at TEXT    NOT NULL,
  updated_at TEXT    NOT NULL,
  html_url   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_issues_state ON github_issues(state);
CREATE INDEX IF NOT EXISTS idx_issues_updated ON github_issues(updated_at DESC);
```

---

## Incremental Sync with since Parameter

Full re-sync is slow. Most GitHub list endpoints accept `since` (ISO 8601) to return only
items updated after a timestamp stored from the last run:

```typescript
async function getLastSyncTime(db: D1Database): Promise<string> {
  const row = await db
    .prepare("SELECT MAX(updated_at) AS last FROM github_issues")
    .first<{ last: string | null }>();
  // Fall back to 30 days ago on first run
  return row?.last ?? new Date(Date.now() - 30 * 86_400_000).toISOString();
}

// Append to URL:
const since = await getLastSyncTime(db);
const url   = `https://api.github.com/repos/${owner}/${repo}/issues` +
              `?state=all&per_page=100&sort=updated&direction=asc&since=${encodeURIComponent(since)}`;
```

Using `sort=updated&direction=asc` with `since` processes changes in chronological order
so an interrupted sync can resume from the last stored `updated_at`.

---

## Anti-patterns

- **Calling `?page=1` without iterating `Link: next`** — you silently receive only the first
  page. Always check for the `next` link before stopping.
- **Setting `per_page` above 100** — the API clamps it to 100 silently; values above 100 do
  not reduce round trips.
- **Fetching all pages then filtering in memory** — add `state=`, `labels=`, `since=`, or
  `milestone=` query parameters to push filtering to the API.
- **Concatenating D1 `VALUES` clauses unbounded** — D1 has a 1 000 binding limit per
  prepared statement. Chunk batches at ~100 rows to stay well under this limit.
- **Using `since` with `sort=created`** — `since` filters on `updated_at`; pair it with
  `sort=updated` or results are inconsistent.

---

## Gotchas

- The `Link` header is absent on the last page (no `next` relation). A script that errors
  on a missing header will fail at the end of every collection.
- GitHub's REST API uses `issues` to return both issues and pull requests; filter on
  `pull_request` field absence to exclude PRs.
- Authenticated requests get 5 000 requests/hour; unauthenticated get 60. At 100 items/page,
  a 500 000-item collection requires 5 000 requests — exactly one hour's budget. Use GZIP
  (`Accept-Encoding: gzip`) and conditional requests (`If-Modified-Since` / `If-None-Match`)
  to stretch the budget.
- Octokit `paginate.iterator` in Workers: `@octokit/rest` bundles fine with `wrangler`, but
  confirm `nodejs_compat` flag is set in `wrangler.toml` if any Node built-ins are transitively
  used.

---

## Verification

```bash
# Inspect Link header directly
curl -sI \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/repos/example-org/example-repo \
  | grep -i link

# Count total pages from last rel
# Link: <https://...?page=42>; rel="last" → 42 pages

# Verify D1 row count after sync
wrangler d1 execute ISSUES_DB \
  --command "SELECT COUNT(*), MAX(updated_at) FROM github_issues"
```

---

## Related

- `github-api-rate-limits.md` — rate limit headers and back-off strategies
- `github-graphql-api-patterns.md` — GraphQL cursor-based pagination
- `github-actions-cloudflare-d1-migration-pipeline.md` — D1 schema management
- `github-actions-scheduled-cron-workers-maintenance.md` — scheduling sync jobs

---

## Sources

- https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api
- https://octokit.github.io/rest.js/v20#pagination
- https://github.com/octokit/plugin-paginate-rest.js
- https://developers.cloudflare.com/d1/
