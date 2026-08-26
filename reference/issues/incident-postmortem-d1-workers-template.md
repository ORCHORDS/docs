# Storing and Querying Incident Post-mortems in D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your on-call team needs a single source of truth for incident post-mortems that is queryable, auditable, and can export structured Markdown. You want a Worker-backed CRUD API over a D1 `incidents` table, the ability to append timeline entries without overwriting the whole JSON column, and an endpoint that renders any incident row as a formatted post-mortem document.

---

## Context
D1 supports JSON columns via SQLite's JSON functions (`json_patch`, `json_array`, `json_each`), making it straightforward to store a structured timeline alongside scalar fields like severity and status. A thin Cloudflare Worker handles REST routing so the API is globally available with zero infrastructure. The timeline-append endpoint uses `json_patch` to merge a new entry into the existing JSON array without a full read-modify-write cycle. The Markdown-export endpoint reconstructs a human-readable post-mortem document from the D1 row, suitable for pasting into a wiki or Slack.

---

## Section 1 — D1 Schema

```sql
CREATE TABLE IF NOT EXISTS incidents (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  slug         TEXT    NOT NULL UNIQUE,        -- e.g. INC-2026-001
  title        TEXT    NOT NULL,
  severity     TEXT    NOT NULL,               -- P1 | P2 | P3 | P4
  status       TEXT    NOT NULL DEFAULT 'open',-- open | investigating | resolved | closed
  owner        TEXT,
  started_at   TEXT    NOT NULL,               -- ISO-8601
  resolved_at  TEXT,
  summary      TEXT,
  timeline     TEXT    NOT NULL DEFAULT '[]',  -- JSON array of {ts, author, note}
  action_items TEXT    NOT NULL DEFAULT '[]',  -- JSON array of {task, owner, due}
  created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_incidents_status   ON incidents (status);
CREATE INDEX IF NOT EXISTS idx_incidents_severity ON incidents (severity);
```

---

## Section 2 — Worker CRUD API

```typescript
// src/index.ts
export interface Env {
  DB: D1Database;
  API_SECRET: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Simple bearer-token auth
    const auth = request.headers.get('Authorization') ?? '';
    if (auth !== `Bearer ${env.API_SECRET}`) {
      return json({ error: 'Unauthorized' }, 401);
    }

    const url = new URL(request.url);
    const [, , resource, id, action] = url.pathname.split('/');
    // Paths: /api/incidents, /api/incidents/:id, /api/incidents/:id/timeline, /api/incidents/:id/export

    if (resource !== 'incidents') return json({ error: 'Not found' }, 404);

    switch (request.method) {
      case 'GET':
        if (action === 'export') return exportMarkdown(env, id);
        if (id) return getIncident(env, id);
        return listIncidents(env, url.searchParams);

      case 'POST':
        if (action === 'timeline') return appendTimeline(request, env, id);
        return createIncident(request, env);

      case 'PATCH':
        return updateIncident(request, env, id);

      case 'DELETE':
        return deleteIncident(env, id);

      default:
        return json({ error: 'Method not allowed' }, 405);
    }
  },
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function listIncidents(env: Env, params: URLSearchParams): Promise<Response> {
  const status = params.get('status');
  const severity = params.get('severity');
  let query = 'SELECT id, slug, title, severity, status, owner, started_at, resolved_at FROM incidents WHERE 1=1';
  const bindings: string[] = [];
  if (status) { query += ' AND status = ?'; bindings.push(status); }
  if (severity) { query += ' AND severity = ?'; bindings.push(severity); }
  query += ' ORDER BY started_at DESC LIMIT 50';
  const stmt = env.DB.prepare(query);
  const result = await (bindings.length ? stmt.bind(...bindings) : stmt).all();
  return json(result.results);
}

async function getIncident(env: Env, id: string): Promise<Response> {
  const row = await env.DB.prepare('SELECT * FROM incidents WHERE slug = ? OR CAST(id AS TEXT) = ?')
    .bind(id, id)
    .first();
  if (!row) return json({ error: 'Not found' }, 404);
  return json({ ...row, timeline: JSON.parse(row.timeline as string), action_items: JSON.parse(row.action_items as string) });
}

async function createIncident(request: Request, env: Env): Promise<Response> {
  const body = await request.json() as any;
  const { slug, title, severity, owner, started_at, summary } = body;
  if (!slug || !title || !severity || !started_at) {
    return json({ error: 'slug, title, severity, started_at required' }, 400);
  }
  const result = await env.DB.prepare(
    `INSERT INTO incidents (slug, title, severity, owner, started_at, summary)
     VALUES (?, ?, ?, ?, ?, ?)`
  ).bind(slug, title, severity, owner ?? null, started_at, summary ?? null).run();
  return json({ id: result.meta.last_row_id, slug }, 201);
}

async function updateIncident(request: Request, env: Env, id: string): Promise<Response> {
  const body = await request.json() as Record<string, unknown>;
  const allowed = ['title', 'severity', 'status', 'owner', 'resolved_at', 'summary', 'action_items'];
  const updates: string[] = [];
  const vals: unknown[] = [];
  for (const key of allowed) {
    if (key in body) {
      updates.push(`${key} = ?`);
      vals.push(key === 'action_items' ? JSON.stringify(body[key]) : body[key]);
    }
  }
  if (!updates.length) return json({ error: 'Nothing to update' }, 400);
  updates.push("updated_at = datetime('now')");
  vals.push(id, id);
  await env.DB.prepare(
    `UPDATE incidents SET ${updates.join(', ')} WHERE slug = ? OR CAST(id AS TEXT) = ?`
  ).bind(...vals).run();
  return json({ ok: true });
}

async function deleteIncident(env: Env, id: string): Promise<Response> {
  await env.DB.prepare('DELETE FROM incidents WHERE slug = ? OR CAST(id AS TEXT) = ?').bind(id, id).run();
  return json({ ok: true });
}
```

---

## Section 3 — Timeline-append and Markdown-export endpoints

```typescript
async function appendTimeline(request: Request, env: Env, id: string): Promise<Response> {
  const { author, note } = await request.json() as { author: string; note: string };
  if (!author || !note) return json({ error: 'author and note required' }, 400);

  const entry = JSON.stringify({ ts: new Date().toISOString(), author, note });

  // Use SQLite json_patch to append to the JSON array atomically
  // json_array appends a new JSON object; we rebuild using json_patch trick:
  // timeline = json_patch(timeline, json_object(...)) is not correct for arrays;
  // instead use: timeline = json(timeline || ... ) via json_insert
  await env.DB.prepare(
    `UPDATE incidents
     SET timeline   = json_insert(timeline, '$[#]', json(?)),
         updated_at = datetime('now')
     WHERE slug = ? OR CAST(id AS TEXT) = ?`
  ).bind(entry, id, id).run();

  return json({ ok: true });
}

async function exportMarkdown(env: Env, id: string): Promise<Response> {
  const row = await env.DB.prepare('SELECT * FROM incidents WHERE slug = ? OR CAST(id AS TEXT) = ?')
    .bind(id, id)
    .first();
  if (!row) return json({ error: 'Not found' }, 404);

  const timeline: Array<{ ts: string; author: string; note: string }> =
    JSON.parse(row.timeline as string);
  const actionItems: Array<{ task: string; owner: string; due: string }> =
    JSON.parse(row.action_items as string);

  const timelineLines = timeline
    .map((e) => `| ${e.ts} | ${e.author} | ${e.note} |`)
    .join('\n');

  const actionLines = actionItems
    .map((a, i) => `${i + 1}. **${a.task}** — owner: ${a.owner}, due: ${a.due}`)
    .join('\n');

  const md = [
    `# Post-mortem: ${row.slug} — ${row.title}`,
    ``,
    `**Severity:** ${row.severity}  **Status:** ${row.status}  **Owner:** ${row.owner ?? 'TBD'}`,
    `**Started:** ${row.started_at}  **Resolved:** ${row.resolved_at ?? 'N/A'}`,
    ``,
    `## Summary`,
    row.summary ?? '_No summary provided._',
    ``,
    `## Timeline`,
    `| Timestamp | Author | Note |`,
    `|-----------|--------|------|`,
    timelineLines || '_No entries._',
    ``,
    `## Action Items`,
    actionLines || '_None recorded._',
  ].join('\n');

  return new Response(md, {
    headers: { 'Content-Type': 'text/markdown; charset=utf-8' },
  });
}
```

---

## Anti-patterns
- **Storing timeline as a flat TEXT blob** — makes appends a full read-modify-write; use SQLite's `json_insert` with `$[#]` path.
- **No auth on the CRUD API** — always gate behind at minimum a secret bearer token stored in a Worker secret.
- **Mutating severity after resolution** — keep severity immutable post-creation; create a new column `escalated_severity` if needed.
- **Exporting raw D1 row JSON to clients** — parse JSON columns server-side before responding so clients see typed data.

---

## Gotchas
- SQLite `json_insert(col, '$[#]', json(?))` — the `'$[#]'` path syntax appends to a JSON array; it requires SQLite ≥ 3.38.
- D1 runs SQLite 3.46+ as of 2024; `json_insert` with array-append path is supported.
- `JSON.parse` on a D1 TEXT column that was never set will throw — always DEFAULT the column to `'[]'`.
- The Markdown export endpoint returns `text/markdown`; some HTTP clients need `Accept: text/markdown` set explicitly.

---

## Verification
```bash
# Create an incident
curl -X POST https://<worker>.workers.dev/api/incidents \
  -H 'Authorization: Bearer <secret>' \
  -H 'Content-Type: application/json' \
  -d '{"slug":"INC-2026-001","title":"DB latency spike","severity":"P1","started_at":"2026-08-24T10:00:00Z"}'

# Append a timeline entry
curl -X POST https://<worker>.workers.dev/api/incidents/INC-2026-001/timeline \
  -H 'Authorization: Bearer <secret>' \
  -H 'Content-Type: application/json' \
  -d '{"author":"alice","note":"Identified slow query on incidents table"}'

# Export as Markdown
curl https://<worker>.workers.dev/api/incidents/INC-2026-001/export \
  -H 'Authorization: Bearer <secret>'

# Query D1 directly
npx wrangler d1 execute <db-name> \
  --command "SELECT slug, severity, status, json_array_length(timeline) AS timeline_entries FROM incidents;"
```

---

## Related
- `workers-error-budget-tracking-analytics-engine.md`
- `on-call-rotation-workers-pagerduty-slack.md`

---

## Sources
- Cloudflare D1 JSON functions — https://developers.cloudflare.com/d1/sql-api/sql-statements/
- SQLite JSON functions reference — https://www.sqlite.org/json1.html
- Cloudflare Workers secrets — https://developers.cloudflare.com/workers/configuration/secrets/
