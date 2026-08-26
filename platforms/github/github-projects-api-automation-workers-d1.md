# GitHub Projects v2 API Automation with Workers and D1

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

GitHub Projects v2 lacks a native persistence layer for computed metrics, cross-project
rollups, or custom automation rules that go beyond built-in workflows. Teams need to
sync project item state to an external store to power dashboards, enforce SLA policies
(e.g. "move all items in 'In Progress' > 5 days to 'At Risk'"), or trigger downstream
actions. Cloudflare Workers + D1 provide a serverless, always-on automation layer that
responds to webhook events and can be scheduled for periodic reconciliation.

---

## Context

GitHub Projects v2 is GraphQL-only; there is no REST equivalent for reading or mutating
project items. Automation requires:

1. A **webhook** (organisation-level, event type `projects_v2_item`) or a **scheduled
   poll** that queries the GraphQL API.
2. A **GitHub App** with `project` scope (`read:project` to read, `project` to write)
   and an installation token for the target org.
3. A **D1 database** to persist item snapshots and compute deltas.

Relevant GraphQL operations: `projectV2Items`, `updateProjectV2ItemFieldValue`,
`addProjectV2ItemById`, `deleteProjectV2Item`.

---

## 1. D1 Schema

```sql
-- migrations/0001_projects_schema.sql
CREATE TABLE IF NOT EXISTS project_items (
  item_id       TEXT PRIMARY KEY,
  project_id    TEXT NOT NULL,
  content_type  TEXT,           -- 'Issue' | 'PullRequest' | 'DraftIssue'
  content_number INTEGER,
  title         TEXT,
  status        TEXT,
  assignees     TEXT,           -- JSON array
  created_at    TEXT,
  updated_at    TEXT,
  synced_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_project_items_status ON project_items(project_id, status);
CREATE INDEX IF NOT EXISTS idx_project_items_updated ON project_items(project_id, updated_at);
```

Apply with: `npx wrangler d1 migrations apply projects-db`.

---

## 2. GitHub App Token Helper

```typescript
// workers/projects-automation/src/github-auth.ts
export async function getInstallationToken(env: {
  GITHUB_APP_ID: string;
  GITHUB_PRIVATE_KEY: string;
  GITHUB_INSTALLATION_ID: string;
}): Promise<string> {
  // Build JWT (App token) – simplified; use webcrypto RS256 signing
  const now = Math.floor(Date.now() / 1000);
  const payload = { iat: now - 60, exp: now + 600, iss: env.GITHUB_APP_ID };

  // Sign with RS256 using the App's private key (PEM stored in Workers Secret)
  const privateKey = await importPKCS8(env.GITHUB_PRIVATE_KEY);
  const jwt = await signJWT(payload, privateKey);

  // Exchange for installation token
  const res = await fetch(
    `https://api.github.com/app/installations/${env.GITHUB_INSTALLATION_ID}/access_tokens`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${jwt}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
    }
  );

  const data = await res.json<{ token: string }>();
  return data.token;
}

// Stub – implement with workers-jwt or native WebCrypto
async function importPKCS8(_pem: string): Promise<CryptoKey> { throw new Error("implement"); }
async function signJWT(_payload: object, _key: CryptoKey): Promise<string> { throw new Error("implement"); }
```

---

## 3. GraphQL Query – Fetch Project Items

```typescript
// workers/projects-automation/src/fetch-items.ts
export interface ProjectItem {
  id: string;
  type: string;
  content?: { number?: number; title?: string; __typename?: string };
  fieldValues: { nodes: Array<{ name?: string; field?: { name: string } }> };
  updatedAt: string;
  createdAt: string;
}

export async function fetchProjectItems(
  token: string,
  projectId: string,
  cursor?: string
): Promise<{ items: ProjectItem[]; nextCursor?: string }> {
  const query = `
    query($projectId: ID!, $after: String) {
      node(id: $projectId) {
        ... on ProjectV2 {
          items(first: 100, after: $after) {
            pageInfo { hasNextPage endCursor }
            nodes {
              id
              type
              updatedAt
              createdAt
              content {
                __typename
                ... on Issue { number title }
                ... on PullRequest { number title }
                ... on DraftIssue { title }
              }
              fieldValues(first: 20) {
                nodes {
                  ... on ProjectV2ItemFieldSingleSelectValue { name field { ... on ProjectV2FieldCommon { name } } }
                  ... on ProjectV2ItemFieldTextValue { text field { ... on ProjectV2FieldCommon { name } } }
                }
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
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query, variables: { projectId, after: cursor } }),
  });

  const { data } = await res.json<{ data: { node: { items: { pageInfo: { hasNextPage: boolean; endCursor: string }; nodes: ProjectItem[] } } } }>();
  const page = data.node.items;
  return {
    items: page.nodes,
    nextCursor: page.pageInfo.hasNextPage ? page.pageInfo.endCursor : undefined,
  };
}
```

---

## 4. Sync Worker (Scheduled + Webhook)

```typescript
// workers/projects-automation/src/index.ts
export interface Env {
  DB: D1Database;
  GITHUB_APP_ID: string;
  GITHUB_PRIVATE_KEY: string;
  GITHUB_INSTALLATION_ID: string;
  PROJECT_ID: string;
  WEBHOOK_SECRET: string;
}

import { getInstallationToken } from "./github-auth";
import { fetchProjectItems } from "./fetch-items";

async function syncProject(env: Env): Promise<void> {
  const token = await getInstallationToken(env);
  let cursor: string | undefined;

  do {
    const { items, nextCursor } = await fetchProjectItems(token, env.PROJECT_ID, cursor);
    cursor = nextCursor;

    const stmt = env.DB.prepare(`
      INSERT INTO project_items
        (item_id, project_id, content_type, content_number, title, status, updated_at, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(item_id) DO UPDATE SET
        status     = excluded.status,
        title      = excluded.title,
        updated_at = excluded.updated_at,
        synced_at  = datetime('now')
    `);

    for (const item of items) {
      const status = item.fieldValues.nodes
        .find((fv) => fv.field?.name === "Status")?.name ?? null;
      await stmt
        .bind(
          item.id,
          env.PROJECT_ID,
          item.content?.__typename ?? item.type,
          item.content?.number ?? null,
          item.content?.title ?? null,
          status,
          item.updatedAt,
          item.createdAt
        )
        .run();
    }
  } while (cursor);
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await syncProject(env);
  },

  async fetch(request: Request, env: Env): Promise<Response> {
    // Webhook handler for real-time updates
    const sig = request.headers.get("X-Hub-Signature-256") ?? "";
    const body = await request.text();

    const valid = await verifyWebhookSignature(body, sig, env.WEBHOOK_SECRET);
    if (!valid) return new Response("Unauthorized", { status: 401 });

    const event = JSON.parse(body);
    if (event.action && ["created", "edited", "deleted"].includes(event.action)) {
      await syncProject(env); // re-sync on any item mutation
    }

    return new Response("OK");
  },
} satisfies ExportedHandler<Env>;

async function verifyWebhookSignature(body: string, sig: string, secret: string): Promise<boolean> {
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const mac = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body));
  const expected = "sha256=" + Array.from(new Uint8Array(mac))
    .map((b) => b.toString(16).padStart(2, "0")).join("");
  return expected === sig;
}
```

---

## 5. SLA Enforcement – Move Stale Items to "At Risk"

```typescript
// workers/projects-automation/src/sla-enforcer.ts
export async function enforceInProgressSLA(
  db: D1Database,
  token: string,
  statusFieldId: string,
  atRiskOptionId: string,
  slaHours = 120
): Promise<void> {
  const cutoff = new Date(Date.now() - slaHours * 3_600_000).toISOString();

  const stale = await db
    .prepare(
      `SELECT item_id FROM project_items
       WHERE status = 'In Progress' AND updated_at < ?`
    )
    .bind(cutoff)
    .all<{ item_id: string }>();

  for (const { item_id } of stale.results) {
    await fetch("https://api.github.com/graphql", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        query: `mutation($itemId: ID!, $fieldId: ID!, $optionId: String!) {
          updateProjectV2ItemFieldValue(input: {
            projectId: "${process.env.PROJECT_ID}"
            itemId: $itemId
            fieldId: $fieldId
            value: { singleSelectOptionId: $optionId }
          }) { projectV2Item { id } }
        }`,
        variables: { itemId: item_id, fieldId: statusFieldId, optionId: atRiskOptionId },
      }),
    });
  }
}
```

---

## Anti-patterns

- **Using REST instead of GraphQL** – Projects v2 data is only available via the
  GraphQL API; REST endpoints return 404 for project item resources.
- **Polling every minute without cursor tracking** – full re-fetches of large projects
  are expensive; use `updatedAt` filters or webhook events for incremental updates.
- **Storing project IDs as numeric IDs** – Projects v2 uses opaque global node IDs
  (e.g. `PVT_kwDOA...`), not numeric project numbers.
- **Hard-coding field option IDs** – `singleSelectOptionId` values are opaque and
  environment-specific; query them dynamically from `projectV2.fields`.

---

## Gotchas

- The GitHub App requires the `project` OAuth scope (not a repository permission) –
  add it under "Permissions & Events" → "Projects" → "Read and write" in App settings.
- GraphQL errors are returned as HTTP 200 with an `errors` array; always check both
  `res.ok` and `data.errors`.
- D1 `INSERT OR REPLACE` deletes then re-inserts the row, resetting `synced_at`; use
  `INSERT ... ON CONFLICT ... DO UPDATE SET` for true upsert semantics.
- Installation tokens expire after 1 hour; cache them in KV with TTL 55 minutes to
  avoid redundant App JWT signing on every scheduled run.
- Projects v2 items have a maximum of 1,200 per project in the GraphQL response per
  page request; paginate with `endCursor` for large boards.

---

## Verification

```bash
# Query D1 to confirm items synced
npx wrangler d1 execute projects-db \
  --command "SELECT status, COUNT(*) FROM project_items GROUP BY status"

# Trigger manual sync
npx wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=*+*+*+*+*"

# Confirm SLA flagging
npx wrangler d1 execute projects-db \
  --command "SELECT item_id, status, updated_at FROM project_items WHERE status = 'At Risk'"
```

---

## Related

- `github-projects-v2-2026.md`
- `github-graphql-api-patterns.md`
- `github-apps-installation-tokens.md`
- `github-actions-cloudflare-d1-migration-pipeline.md`

---

## Sources

- GitHub Projects v2 GraphQL API: https://docs.github.com/en/graphql/reference/objects#projectv2
- Projects v2 webhooks: https://docs.github.com/en/webhooks/webhook-events-and-payloads#projects_v2_item
- Cloudflare D1 upsert pattern: https://developers.cloudflare.com/d1/sql-api/sql-statements/#insert-on-conflict
- GitHub App project permissions: https://docs.github.com/en/rest/overview/permissions-required-for-github-apps#permission-on-projects
