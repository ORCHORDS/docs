# GitHub Projects Board Sync with Workers + D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

GitHub Projects (v2) is the source of truth for sprint work, but teams need offline-queryable snapshots: velocity calculations, sprint burndown charts, and status transition histories that the Projects GraphQL API does not expose directly. A Worker can mirror project item events into D1 and expose a reporting endpoint.

## Context

GitHub fires `projects_v2_item` webhook events whenever a project item is added, edited, or removed. Each event contains the item's content node ID, field values, and project metadata. A Cloudflare Worker ingests these events, maintains a D1 mirror, computes velocity metrics, and serves a burndown endpoint. The Projects API is GraphQL-only; pagination uses a `cursor` pattern.

## Solution

### wrangler.toml

```toml
name = "project-sync"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding = "DB"
database_name = "project-sync"
database_id = "<your-d1-database-id>"
```

### D1 schema

```sql
-- migrations/0001_schema.sql
CREATE TABLE IF NOT EXISTS project_items (
  node_id        TEXT PRIMARY KEY,
  project_number INTEGER NOT NULL,
  content_type   TEXT,
  content_number INTEGER,
  status         TEXT,
  sprint_title   TEXT,
  story_points   REAL,
  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL,
  archived       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS status_transitions (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  node_id     TEXT NOT NULL,
  from_status TEXT,
  to_status   TEXT NOT NULL,
  transitioned_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_items_sprint ON project_items(sprint_title);
CREATE INDEX IF NOT EXISTS idx_items_status ON project_items(status);
CREATE INDEX IF NOT EXISTS idx_transitions_node ON status_transitions(node_id);
```

### GraphQL query to resolve item details

```typescript
async function resolveItemDetails(
  nodeId: string,
  ghToken: string
): Promise<{ status: string | null; sprint: string | null; points: number | null; contentNumber: number | null }> {
  const query = `
    query GetItem($nodeId: ID!) {
      node(id: $nodeId) {
        ... on ProjectV2Item {
          content {
            ... on Issue { number }
            ... on PullRequest { number }
          }
          fieldValues(first: 20) {
            nodes {
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field { ... on ProjectV2FieldCommon { name } }
              }
              ... on ProjectV2ItemFieldIterationValue {
                title
                field { ... on ProjectV2FieldCommon { name } }
              }
              ... on ProjectV2ItemFieldNumberValue {
                number
                field { ... on ProjectV2FieldCommon { name } }
              }
            }
          }
        }
      }
    }
  `;

  const res = await fetch("https://api.github.com/graphql", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${ghToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query, variables: { nodeId } }),
  });

  const data: any = await res.json();
  const item = data?.data?.node;
  if (!item) return { status: null, sprint: null, points: null, contentNumber: null };

  let status: string | null = null;
  let sprint: string | null = null;
  let points: number | null = null;
  const contentNumber: number | null = item.content?.number ?? null;

  for (const fv of item.fieldValues?.nodes ?? []) {
    const fieldName: string = fv.field?.name ?? "";
    if (fieldName === "Status" && fv.name) status = fv.name;
    if (fieldName === "Sprint" && fv.title) sprint = fv.title;
    if (fieldName === "Story Points" && fv.number !== undefined) points = fv.number;
  }

  return { status, sprint, points, contentNumber };
}
```

### Upsert item and record status transition

```typescript
async function upsertItem(db: D1Database, event: any, details: any): Promise<void> {
  const { node_id, content_type, created_at, updated_at } = event.projects_v2_item;
  const archived = event.action === "archived" ? 1 : 0;

  const existing = await db
    .prepare("SELECT status FROM project_items WHERE node_id = ?")
    .bind(node_id)
    .first<{ status: string | null }>();

  await db
    .prepare(
      `INSERT INTO project_items
         (node_id, project_number, content_type, content_number, status, sprint_title, story_points, created_at, updated_at, archived)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(node_id) DO UPDATE SET
         status = excluded.status,
         sprint_title = excluded.sprint_title,
         story_points = excluded.story_points,
         updated_at = excluded.updated_at,
         archived = excluded.archived`
    )
    .bind(node_id, 0, content_type, details.contentNumber, details.status, details.sprint, details.points, created_at, updated_at, archived)
    .run();

  if (details.status && details.status !== existing?.status) {
    await db
      .prepare("INSERT INTO status_transitions (node_id, from_status, to_status, transitioned_at) VALUES (?, ?, ?, ?)")
      .bind(node_id, existing?.status ?? null, details.status, updated_at)
      .run();
  }
}
```

### Sprint burndown endpoint

```typescript
async function handleBurndown(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const sprint = url.searchParams.get("sprint");
  if (!sprint) return new Response("Missing sprint param", { status: 400 });

  const { results: items } = await env.DB
    .prepare("SELECT status, story_points FROM project_items WHERE sprint_title = ? AND archived = 0")
    .bind(sprint)
    .all<{ status: string; story_points: number | null }>();

  const totalPoints = items.reduce((s, i) => s + (i.story_points ?? 0), 0);
  const donePoints = items.filter((i) => i.status === "Done").reduce((s, i) => s + (i.story_points ?? 0), 0);

  const { results: transitions } = await env.DB
    .prepare(
      `SELECT st.transitioned_at, pi.story_points
       FROM status_transitions st
       JOIN project_items pi ON pi.node_id = st.node_id
       WHERE pi.sprint_title = ? AND st.to_status = 'Done'
       ORDER BY st.transitioned_at ASC`
    )
    .bind(sprint)
    .all<{ transitioned_at: string; story_points: number | null }>();

  let remaining = totalPoints;
  const burndown = transitions.map((t) => {
    remaining -= t.story_points ?? 0;
    return { at: t.transitioned_at, remaining };
  });

  return Response.json({ sprint, totalPoints, donePoints, remainingPoints: totalPoints - donePoints, burndown });
}
```

## Anti-patterns

- Do not use the REST `/projects` endpoint — it targets the legacy Projects v1 API.
- Do not cache GraphQL responses; project field values change frequently.
- Do not run GraphQL resolution inside a D1 transaction — fetch first, then write.

## Gotchas

- `projects_v2_item` webhooks only fire for organisation-level projects.
- The item `node_id` is the project item node ID, not the issue node ID.
- Use a tunnel (Cloudflare Tunnel or ngrok) to receive live webhooks during local dev.

## Verification

```bash
npx wrangler d1 migrations apply project-sync --local
npx wrangler d1 execute project-sync --local --command "SELECT COUNT(*) FROM project_items"
curl "http://localhost:8787/burndown?sprint=Sprint+5"
```

## Related

- workers-github-issue-webhook-router
- workers-issue-metrics-analytics-engine
- workers-issue-sla-tracker-d1

## Sources

- https://docs.github.com/en/webhooks/webhook-events-and-payloads#projects_v2_item
- https://docs.github.com/en/graphql/reference/objects#projectv2item
- https://developers.cloudflare.com/d1/
