# Email Template Versioning System in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your marketing and transactional emails are stored as inline HTML strings scattered across multiple Workers. There is no version history, no way to preview a template before sending, and rolling back a broken template requires a code deployment. You need a structured versioning system that stores templates externally, supports variable interpolation, enables A/B testing, and provides an approval workflow before any template goes live.

---

## Context

Cloudflare R2 is an ideal backing store for HTML email templates — it offers zero-egress reads, strong consistency within a region, and a simple key-value API. D1 acts as the metadata and workflow database, tracking version numbers, approval status, and A/B variant weights. The Worker exposes a small internal API for template management and delegates sending to MailChannels or any SMTP relay.

Prerequisites:
- R2 bucket bound as `EMAIL_TEMPLATES`
- D1 database bound as `DB`
- Workers environment with `wrangler.toml` bindings configured

---

## Solution

```typescript
// wrangler.toml bindings (excerpt)
// [[r2_buckets]]
// binding = "EMAIL_TEMPLATES"
// bucket_name = "email-templates-prod"
//
// [[d1_databases]]
// binding = "DB"
// database_name = "email-db"
// database_id = "<your-d1-id>"

export interface Env {
  EMAIL_TEMPLATES: R2Bucket;
  DB: D1Database;
}

// ── D1 schema (run once via wrangler d1 execute) ──────────────────────────────
// CREATE TABLE IF NOT EXISTS template_versions (
//   id          TEXT PRIMARY KEY,          -- uuid
//   name        TEXT NOT NULL,             -- logical template name, e.g. "welcome"
//   version     INTEGER NOT NULL,
//   variant     TEXT NOT NULL DEFAULT 'A', -- A/B variant label
//   r2_key      TEXT NOT NULL,             -- R2 object key
//   status      TEXT NOT NULL DEFAULT 'draft', -- draft | pending | approved | archived
//   weight      REAL NOT NULL DEFAULT 1.0, -- A/B send weight 0‥1
//   created_at  TEXT NOT NULL,
//   approved_at TEXT,
//   approved_by TEXT
// );
// CREATE INDEX IF NOT EXISTS idx_tv_name_version ON template_versions(name, version);
// CREATE INDEX IF NOT EXISTS idx_tv_status ON template_versions(status);

import { randomUUID } from 'node:crypto';

type Status = 'draft' | 'pending' | 'approved' | 'archived';

interface TemplateVersion {
  id: string;
  name: string;
  version: number;
  variant: string;
  r2_key: string;
  status: Status;
  weight: number;
  created_at: string;
  approved_at: string | null;
  approved_by: string | null;
}

// ── Interpolation engine ──────────────────────────────────────────────────────
// Replaces {{variable}} placeholders; throws on missing required variables.
function interpolate(
  template: string,
  vars: Record<string, string>,
  strict = true
): string {
  return template.replace(/\{\{\s*([\w.]+)\s*\}\}/g, (match, key) => {
    if (Object.prototype.hasOwnProperty.call(vars, key)) {
      return vars[key];
    }
    if (strict) {
      throw new Error(`Template variable '${key}' is required but was not provided`);
    }
    return match; // leave placeholder intact in non-strict mode
  });
}

// ── R2 helpers ────────────────────────────────────────────────────────────────
async function storeTemplate(
  bucket: R2Bucket,
  key: string,
  html: string
): Promise<void> {
  await bucket.put(key, html, {
    httpMetadata: { contentType: 'text/html; charset=utf-8' },
  });
}

async function fetchTemplate(bucket: R2Bucket, key: string): Promise<string> {
  const obj = await bucket.get(key);
  if (!obj) throw new Error(`Template not found in R2: ${key}`);
  return obj.text();
}

// ── D1 helpers ────────────────────────────────────────────────────────────────
async function getLatestApprovedVersion(
  db: D1Database,
  name: string
): Promise<TemplateVersion | null> {
  // When multiple approved variants exist, pick by weight-based random selection.
  const { results } = await db
    .prepare(
      `SELECT * FROM template_versions
       WHERE name = ? AND status = 'approved'
       ORDER BY version DESC, variant ASC`
    )
    .bind(name)
    .all<TemplateVersion>();

  if (!results.length) return null;

  // Weight-based A/B selection
  const totalWeight = results.reduce((s, r) => s + r.weight, 0);
  let roll = Math.random() * totalWeight;
  for (const row of results) {
    roll -= row.weight;
    if (roll <= 0) return row;
  }
  return results[results.length - 1];
}

async function getVersionById(
  db: D1Database,
  id: string
): Promise<TemplateVersion | null> {
  const { results } = await db
    .prepare('SELECT * FROM template_versions WHERE id = ?')
    .bind(id)
    .all<TemplateVersion>();
  return results[0] ?? null;
}

// ── Core API handlers ─────────────────────────────────────────────────────────

/** POST /templates — create a new version (draft) */
async function handleCreate(request: Request, env: Env): Promise<Response> {
  const body = await request.json<{
    name: string;
    html: string;
    variant?: string;
  }>();

  const { name, html, variant = 'A' } = body;
  if (!name || !html) {
    return new Response('name and html are required', { status: 400 });
  }

  // Determine next version number
  const { results } = await env.DB
    .prepare('SELECT MAX(version) AS max_v FROM template_versions WHERE name = ?')
    .bind(name)
    .all<{ max_v: number | null }>();
  const nextVersion = (results[0]?.max_v ?? 0) + 1;

  const id = randomUUID();
  const r2Key = `templates/${name}/v${nextVersion}/${variant}.html`;

  await storeTemplate(env.EMAIL_TEMPLATES, r2Key, html);

  await env.DB
    .prepare(
      `INSERT INTO template_versions
         (id, name, version, variant, r2_key, status, weight, created_at)
       VALUES (?, ?, ?, ?, ?, 'draft', 1.0, ?)`
    )
    .bind(id, name, nextVersion, variant, r2Key, new Date().toISOString())
    .run();

  return Response.json({ id, name, version: nextVersion, variant, status: 'draft' }, { status: 201 });
}

/** POST /templates/:id/approve — move status draft→pending→approved */
async function handleApprove(
  id: string,
  approver: string,
  env: Env
): Promise<Response> {
  const row = await getVersionById(env.DB, id);
  if (!row) return new Response('Not found', { status: 404 });
  if (row.status !== 'draft' && row.status !== 'pending') {
    return new Response(`Cannot approve a template in status '${row.status}'`, { status: 409 });
  }

  await env.DB
    .prepare(
      `UPDATE template_versions
       SET status = 'approved', approved_at = ?, approved_by = ?
       WHERE id = ?`
    )
    .bind(new Date().toISOString(), approver, id)
    .run();

  return Response.json({ id, status: 'approved', approved_by: approver });
}

/** POST /templates/:id/rollback — clone a previous version as a new draft */
async function handleRollback(id: string, env: Env): Promise<Response> {
  const row = await getVersionById(env.DB, id);
  if (!row) return new Response('Not found', { status: 404 });

  const html = await fetchTemplate(env.EMAIL_TEMPLATES, row.r2_key);

  // Delegate to create path by re-posting the old HTML
  const syntheticRequest = new Request('http://internal/templates', {
    method: 'POST',
    body: JSON.stringify({ name: row.name, html, variant: row.variant }),
    headers: { 'content-type': 'application/json' },
  });
  return handleCreate(syntheticRequest, env);
}

/** GET /templates/:name/preview?vars=... — render with sample data */
async function handlePreview(
  name: string,
  searchParams: URLSearchParams,
  env: Env
): Promise<Response> {
  const row = await getLatestApprovedVersion(env.DB, name);
  if (!row) return new Response('No approved template found', { status: 404 });

  const html = await fetchTemplate(env.EMAIL_TEMPLATES, row.r2_key);

  // Caller passes vars as a JSON-encoded query param: ?vars={"first_name":"Alex"}
  const rawVars = searchParams.get('vars');
  const vars: Record<string, string> = rawVars ? JSON.parse(rawVars) : {};

  const rendered = interpolate(html, vars, false /* non-strict preview */);

  return new Response(rendered, {
    headers: { 'Content-Type': 'text/html; charset=utf-8' },
  });
}

/** GET /templates/:name — render approved template with strict vars (for sending) */
export async function resolveTemplate(
  name: string,
  vars: Record<string, string>,
  env: Env
): Promise<{ html: string; variantId: string }> {
  const row = await getLatestApprovedVersion(env.DB, name);
  if (!row) throw new Error(`No approved template named '${name}'`);
  const raw = await fetchTemplate(env.EMAIL_TEMPLATES, row.r2_key);
  const html = interpolate(raw, vars);
  return { html, variantId: row.id };
}

// ── Worker fetch handler ──────────────────────────────────────────────────────
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const [, , segment, idOrName, action] = url.pathname.split('/');
    // /api/templates            POST → create
    // /api/templates/:id/approve POST → approve
    // /api/templates/:id/rollback POST → rollback
    // /api/templates/:name/preview GET → preview

    if (segment !== 'templates') {
      return new Response('Not found', { status: 404 });
    }

    if (request.method === 'POST' && !idOrName) {
      return handleCreate(request, env);
    }
    if (request.method === 'POST' && action === 'approve') {
      const approver = request.headers.get('x-approver') ?? 'unknown';
      return handleApprove(idOrName, approver, env);
    }
    if (request.method === 'POST' && action === 'rollback') {
      return handleRollback(idOrName, env);
    }
    if (request.method === 'GET' && action === 'preview') {
      return handlePreview(idOrName, url.searchParams, env);
    }

    return new Response('Method not allowed', { status: 405 });
  },
};
```

---

## Implementation Details

- **Storage layout in R2**: keys follow the pattern `templates/{name}/v{version}/{variant}.html`. This allows listing all variants of a specific version with a prefix query (`bucket.list({ prefix: 'templates/welcome/v3/' })`).
- **Interpolation engine**: uses a simple `{{variable}}` syntax compatible with Handlebars-style templates. In strict mode (production sends) it throws on any unresolved placeholder, catching missing data early. In non-strict mode (preview) it leaves unresolved placeholders in place so the designer can see which variables are expected.
- **A/B weight selection**: weights are stored as floating-point values and selected via a weighted random walk. Weights do not need to sum to 1 — they are normalised at selection time. Set both variants to `weight = 1.0` for a 50/50 split; set one to `0` to effectively disable it without archiving.
- **Approval workflow**: the status machine is `draft → pending → approved → archived`. The `pending` state is optional and can be used for a two-stage review (author submits for review, reviewer approves). Direct `draft → approved` transitions are allowed for single-reviewer teams.
- **D1 index strategy**: `(name, version)` covers the MAX(version) lookup on create and the ordered list on approval; `(status)` covers dashboard queries that list all drafts awaiting review.

---

## Anti-patterns

- **Storing templates as Worker source code** — changes require a deployment and there is no diff history separate from your code commits.
- **Single `latest` R2 key** — overwriting a single key on every save loses all rollback capability. Always write a new key per version.
- **Skipping strict interpolation on send** — if a required variable is missing, the email goes out with a raw `{{first_name}}` visible to the recipient. Always use strict mode on the send path.
- **Not archiving superseded approved versions** — multiple approved variants with the same name and version will all be served in rotation, which may not be intended after a fix.

---

## Gotchas

- R2 `put` is eventually consistent across regions. For preview immediately after upload add a short `waitUntil`-based delay or read back with a `HEAD` to confirm the object exists before returning the draft ID to the caller.
- D1 transactions (`db.batch([...])`) should wrap the R2 store + D1 insert so a failed D1 write does not leave an orphaned R2 object. R2 does not support transactions, so accept that an R2 orphan is possible on D1 failure and add a periodic R2 key reconciliation job.
- `randomUUID()` from `node:crypto` is available in Workers when the compatibility flag `nodejs_compat` is enabled. Alternatively use `crypto.randomUUID()` (Web Crypto, always available in Workers with no flag).
- Template names must be URL-safe if used as R2 key segments. Validate with `/^[a-z0-9-_]+$/` on create.

---

## Verification

```bash
# 1. Create a draft template
curl -X POST https://your-worker.dev/api/templates \
  -H 'Content-Type: application/json' \
  -d '{"name":"welcome","html":"<h1>Hello {{first_name}}</h1>","variant":"A"}'
# → {"id":"uuid","name":"welcome","version":1,"variant":"A","status":"draft"}

# 2. Approve it
curl -X POST https://your-worker.dev/api/templates/<id>/approve \
  -H 'x-approver: alice@example.com'

# 3. Preview rendered output
curl 'https://your-worker.dev/api/templates/welcome/preview?vars=%7B%22first_name%22%3A%22Alex%22%7D'
# → <h1>Hello Alex</h1>

# 4. Check D1 directly
wrangler d1 execute email-db --command \
  "SELECT name, version, variant, status, approved_by FROM template_versions;"
```

---

## Related

- `workers-transactional-email-queue.md` — consuming templates resolved here for actual sends
- `workers-email-open-tracking.md` — injecting tracking pixels into rendered HTML
- Cloudflare R2 docs: https://developers.cloudflare.com/r2/
- Cloudflare D1 docs: https://developers.cloudflare.com/d1/

---

## Sources

- https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
- https://developers.cloudflare.com/d1/worker-api/d1-client-api/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
