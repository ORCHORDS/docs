# Code Review Statistics Dashboard Data from Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want real-time code review analytics — reviewer throughput, time-to-review, lines reviewed per team — without running a separate data pipeline. A Cloudflare Worker ingests `pull_request_review` and `pull_request` GitHub webhooks, stores structured data in D1, computes aggregates (cycle time, review throughput, per-team metrics), and exposes a JSON API consumed by an analytics dashboard.

## Context

Code review health is a proxy for team velocity. Key metrics:

- **Time-to-first-review** — minutes between PR opened and first review submitted.
- **Review throughput** — reviews submitted per reviewer per week.
- **Lines reviewed** — additions + deletions of PRs a reviewer approved.
- **Cycle time** — PR open → merge, broken down by review wait vs. author revision time.

GitHub sends `pull_request_review` events (submitted, dismissed, edited) and `pull_request` events (opened, closed, merged). The Worker stores minimal normalized data in D1 and computes rolling aggregates on read via SQL window functions.

## Solution

```typescript
// src/index.ts
import { Hono } from 'hono';
import { cors } from 'hono/cors';

export interface Env {
  GITHUB_WEBHOOK_SECRET: string;
  DB: D1Database;
  GITHUB_ORG: string;
  API_TOKEN: string; // Bearer token for dashboard API access
}

interface PROpenedPayload {
  action: 'opened' | 'closed' | 'merged';
  pull_request: {
    id: number;
    number: number;
    title: string;
    user: { login: string };
    base: { repo: { name: string; owner: { login: string } } };
    additions: number;
    deletions: number;
    merged_at: string | null;
    closed_at: string | null;
    created_at: string;
    requested_teams: Array<{ name: string; slug: string }>;
  };
}

interface ReviewPayload {
  action: 'submitted' | 'dismissed' | 'edited';
  review: {
    id: number;
    user: { login: string };
    state: 'approved' | 'changes_requested' | 'commented';
    submitted_at: string;
    body: string | null;
  };
  pull_request: {
    id: number;
    number: number;
    additions: number;
    deletions: number;
    created_at: string;
    base: { repo: { name: string; owner: { login: string } } };
    requested_teams: Array<{ name: string; slug: string }>;
  };
}

// --- HMAC verification ---
async function verifySignature(secret: string, sig: string, body: ArrayBuffer): Promise<void> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const mac = await crypto.subtle.sign('HMAC', key, body);
  const expected =
    'sha256=' +
    Array.from(new Uint8Array(mac))
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');
  if (expected !== sig) throw new Error('Signature mismatch');
}

// --- D1 write helpers ---
async function upsertPR(
  db: D1Database,
  pr: PROpenedPayload['pull_request'],
  repoOwner: string,
  repoName: string,
): Promise<void> {
  const teamSlug = pr.requested_teams?.[0]?.slug ?? 'unknown';
  await db
    .prepare(
      `INSERT INTO pull_requests
         (github_id, number, owner, repo, author, title, team_slug,
          additions, deletions, opened_at, merged_at, closed_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(github_id) DO UPDATE SET
         merged_at  = excluded.merged_at,
         closed_at  = excluded.closed_at,
         additions  = excluded.additions,
         deletions  = excluded.deletions`,
    )
    .bind(
      pr.id,
      pr.number,
      repoOwner,
      repoName,
      pr.user.login,
      pr.title,
      teamSlug,
      pr.additions,
      pr.deletions,
      pr.created_at,
      pr.merged_at ?? null,
      pr.closed_at ?? null,
    )
    .run();
}

async function insertReview(
  db: D1Database,
  review: ReviewPayload['review'],
  pr: ReviewPayload['pull_request'],
  repoOwner: string,
  repoName: string,
): Promise<void> {
  // Calculate time-to-first-review in minutes
  const prOpenedAt = new Date(pr.created_at).getTime();
  const reviewedAt = new Date(review.submitted_at).getTime();
  const minutesToFirstReview = Math.round((reviewedAt - prOpenedAt) / 60_000);
  const teamSlug = pr.requested_teams?.[0]?.slug ?? 'unknown';

  await db
    .prepare(
      `INSERT OR IGNORE INTO reviews
         (github_id, pr_github_id, owner, repo, reviewer, team_slug,
          state, lines_reviewed, minutes_to_review, submitted_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      review.id,
      pr.id,
      repoOwner,
      repoName,
      review.user.login,
      teamSlug,
      review.state,
      pr.additions + pr.deletions,
      minutesToFirstReview,
      review.submitted_at,
    )
    .run();
}

// --- Aggregation queries ---
async function getReviewerStats(
  db: D1Database,
  org: string,
  since: string,
  teamSlug?: string,
): Promise<unknown> {
  const teamFilter = teamSlug ? `AND team_slug = '${teamSlug}'` : '';
  const { results } = await db
    .prepare(
      `SELECT
         reviewer,
         team_slug,
         COUNT(*)                           AS review_count,
         ROUND(AVG(minutes_to_review), 1)   AS avg_minutes_to_review,
         ROUND(AVG(lines_reviewed), 0)      AS avg_lines_reviewed,
         SUM(lines_reviewed)               AS total_lines_reviewed,
         SUM(CASE WHEN state = 'approved' THEN 1 ELSE 0 END) AS approvals
       FROM reviews
       WHERE owner = ?
         AND submitted_at >= ?
         ${teamFilter}
       GROUP BY reviewer, team_slug
       ORDER BY review_count DESC`,
    )
    .bind(org, since)
    .all();
  return results;
}

async function getCycleTimeStats(
  db: D1Database,
  org: string,
  since: string,
): Promise<unknown> {
  const { results } = await db
    .prepare(
      `SELECT
         repo,
         team_slug,
         COUNT(*)                                              AS merged_prs,
         ROUND(AVG(
           (julianday(merged_at) - julianday(opened_at)) * 1440
         ), 0)                                                AS avg_cycle_time_minutes,
         ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP
           (ORDER BY (julianday(merged_at) - julianday(opened_at)) * 1440)
         , 0)                                                 AS p50_cycle_time_minutes,
         ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP
           (ORDER BY (julianday(merged_at) - julianday(opened_at)) * 1440)
         , 0)                                                 AS p95_cycle_time_minutes
       FROM pull_requests
       WHERE owner = ?
         AND merged_at IS NOT NULL
         AND opened_at >= ?
       GROUP BY repo, team_slug
       ORDER BY avg_cycle_time_minutes ASC`,
    )
    .bind(org, since)
    .all();
  return results;
}

async function getWeeklyThroughput(
  db: D1Database,
  org: string,
  weeks: number,
): Promise<unknown> {
  const since = new Date(
    Date.now() - weeks * 7 * 24 * 3600 * 1000,
  ).toISOString();
  const { results } = await db
    .prepare(
      `SELECT
         strftime('%Y-W%W', submitted_at)  AS week,
         reviewer,
         team_slug,
         COUNT(*)                          AS reviews_submitted
       FROM reviews
       WHERE owner = ? AND submitted_at >= ?
       GROUP BY week, reviewer, team_slug
       ORDER BY week DESC, reviews_submitted DESC`,
    )
    .bind(org, since)
    .all();
  return results;
}

// --- Hono app ---
const app = new Hono<{ Bindings: Env }>();

app.use('/api/*', cors({ origin: '*' }));

// Auth middleware for API routes
app.use('/api/*', async (c, next) => {
  const auth = c.req.header('Authorization') ?? '';
  if (auth !== `Bearer ${c.env.API_TOKEN}`) {
    return c.json({ error: 'Unauthorized' }, 401);
  }
  return next();
});

// Webhook ingestion
app.post('/webhook', async (c) => {
  const rawBody = await c.req.arrayBuffer();
  try {
    await verifySignature(
      c.env.GITHUB_WEBHOOK_SECRET,
      c.req.header('X-Hub-Signature-256') ?? '',
      rawBody,
    );
  } catch {
    return c.json({ error: 'Unauthorized' }, 401);
  }

  const ghEvent = c.req.header('X-GitHub-Event');
  const payload = JSON.parse(new TextDecoder().decode(rawBody));

  c.executionCtx.waitUntil(
    (async () => {
      if (ghEvent === 'pull_request') {
        const p = payload as PROpenedPayload;
        const repoOwner = p.pull_request.base.repo.owner.login;
        const repoName = p.pull_request.base.repo.name;
        if (['opened', 'closed', 'merged'].includes(p.action)) {
          await upsertPR(c.env.DB, p.pull_request, repoOwner, repoName);
        }
      } else if (ghEvent === 'pull_request_review') {
        const p = payload as ReviewPayload;
        const repoOwner = p.pull_request.base.repo.owner.login;
        const repoName = p.pull_request.base.repo.name;
        if (p.action === 'submitted') {
          await upsertPR(c.env.DB, p.pull_request as unknown as PROpenedPayload['pull_request'], repoOwner, repoName);
          await insertReview(c.env.DB, p.review, p.pull_request, repoOwner, repoName);
        }
      }
    })(),
  );

  return c.json({ ok: true });
});

// API: reviewer stats
app.get('/api/reviewers', async (c) => {
  const since = c.req.query('since') ?? new Date(Date.now() - 30 * 86400 * 1000).toISOString();
  const team = c.req.query('team');
  const data = await getReviewerStats(c.env.DB, c.env.GITHUB_ORG, since, team);
  return c.json({ data, since });
});

// API: cycle time
app.get('/api/cycle-time', async (c) => {
  const since = c.req.query('since') ?? new Date(Date.now() - 30 * 86400 * 1000).toISOString();
  const data = await getCycleTimeStats(c.env.DB, c.env.GITHUB_ORG, since);
  return c.json({ data, since });
});

// API: weekly throughput
app.get('/api/throughput', async (c) => {
  const weeks = Number(c.req.query('weeks') ?? '12');
  const data = await getWeeklyThroughput(c.env.DB, c.env.GITHUB_ORG, weeks);
  return c.json({ data, weeks });
});

export default app;
```

## Implementation Details

**D1 schema**:

```sql
CREATE TABLE IF NOT EXISTS pull_requests (
  github_id  INTEGER PRIMARY KEY,
  number     INTEGER NOT NULL,
  owner      TEXT    NOT NULL,
  repo       TEXT    NOT NULL,
  author     TEXT    NOT NULL,
  title      TEXT    NOT NULL,
  team_slug  TEXT    NOT NULL DEFAULT 'unknown',
  additions  INTEGER NOT NULL DEFAULT 0,
  deletions  INTEGER NOT NULL DEFAULT 0,
  opened_at  TEXT    NOT NULL,
  merged_at  TEXT,
  closed_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_pr_owner_opened ON pull_requests(owner, opened_at);

CREATE TABLE IF NOT EXISTS reviews (
  github_id           INTEGER PRIMARY KEY,
  pr_github_id        INTEGER NOT NULL REFERENCES pull_requests(github_id),
  owner               TEXT    NOT NULL,
  repo                TEXT    NOT NULL,
  reviewer            TEXT    NOT NULL,
  team_slug           TEXT    NOT NULL DEFAULT 'unknown',
  state               TEXT    NOT NULL,
  lines_reviewed      INTEGER NOT NULL DEFAULT 0,
  minutes_to_review   INTEGER NOT NULL DEFAULT 0,
  submitted_at        TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_review_owner_submitted ON reviews(owner, submitted_at);
CREATE INDEX IF NOT EXISTS idx_review_reviewer ON reviews(reviewer);
```

**Team attribution** — GitHub's `requested_teams` array only appears on the PR at open time. If the team is unknown (direct push, solo repo), default to `'unknown'` and allow the dashboard to filter it out.

**PERCENTILE_CONT note** — D1 is SQLite-based and does not currently support `PERCENTILE_CONT`. Replace with a median approximation: `AVG(value) FILTER (WHERE rn BETWEEN total/2 AND total/2 + 1)` using a CTE with `ROW_NUMBER()`, or compute percentiles in the Worker after fetching raw data.

## Anti-patterns

- Do not compute aggregates synchronously on the webhook path — use `waitUntil` and return 200 immediately.
- Do not store `review.body` text in D1 — it can contain sensitive code comments and bloats the database; store only metadata.
- Do not issue one D1 write per webhook field; batch with `db.batch([...])` when inserting both the PR and review row.
- Do not expose the `/webhook` endpoint without HMAC verification — replaying fake review events would corrupt stats.

## Gotchas

- GitHub sends `pull_request_review` events even for `commented` state reviews, not just approvals — filter by `state` in queries or ingest all and filter at query time.
- `pull_request.additions` and `pull_request.deletions` are not available in the review webhook payload's abbreviated PR object; rely on the separate `pull_request` event to keep those fields up-to-date.
- D1's `INSERT OR IGNORE` silently drops duplicates — correct for reviews (idempotent webhook replays) but use `ON CONFLICT DO UPDATE` for PRs to capture the final `merged_at` / `closed_at` timestamps.
- The `julianday()` SQLite function returns a float; multiplying by 1440 converts to minutes.
- Hono's `cors` middleware must be registered before auth middleware for preflight `OPTIONS` requests to pass without authentication.

## Verification

```bash
# Send a fake pull_request_review event
curl -X POST https://cr-stats.orchords.workers.dev/webhook \
  -H 'Content-Type: application/json' \
  -H 'X-GitHub-Event: pull_request_review' \
  -H "X-Hub-Signature-256: $(echo -n '{...}' | openssl dgst -sha256 -hmac 'secret' | awk '{print "sha256="$2}')" \
  -d @test/fixtures/review_submitted.json

# Query reviewer stats
curl 'https://cr-stats.orchords.workers.dev/api/reviewers?since=2026-08-01T00:00:00Z' \
  -H 'Authorization: Bearer <api-token>'

# Inspect D1 directly
wrangler d1 execute cr-stats \
  --command "SELECT reviewer, COUNT(*) FROM reviews GROUP BY reviewer" \
  --remote
```

## Related

- `documentation/categories/github/workers-github-copilot-extension.md`
- `documentation/categories/cloudflare/workers-d1-migrations.md`
- `documentation/categories/cloudflare/workers-hono-routing.md`

## Sources

- https://docs.github.com/en/webhooks/webhook-events-and-payloads#pull_request_review
- https://docs.github.com/en/webhooks/webhook-events-and-payloads#pull_request
- https://developers.cloudflare.com/d1/
- https://hono.dev/docs/middleware/builtin/cors
