# Email Templates Stored in R2 with Handlebars Rendering in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You manage multiple transactional email templates (welcome, password reset, invoice) and want to update them without redeploying the Worker. Storing `.hbs` Handlebars templates in an R2 bucket lets designers push template changes independently; the Worker fetches, compiles, and renders them on demand, caches the compiled output via the Cache API, then sends the resulting HTML through MailChannels. Every send is recorded in a D1 audit log.

---

## Context

Cloudflare R2 is an S3-compatible object store available to Workers via an R2 binding. Handlebars is a lightweight logic-less template engine that compiles to a reusable render function. Because `Handlebars.compile()` is CPU-intensive, the compiled template string is stored in the Cache API with a 1-hour TTL so subsequent requests skip recompilation. MailChannels accepts an HTML body via a JSON POST to `https://api.mailchannels.net/tx/v1/send`. D1 provides the audit log table that records every outbound send: recipient, template key, timestamp, and MailChannels response status. Template keys follow the convention `<name>/<locale>.hbs` (e.g. `welcome/en.hbs`).

---

## Section 1 — R2, D1, and Wrangler Config

```toml
# wrangler.toml
name = "email-template-sender"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[vars]
SENDING_DOMAIN = "example.com"
TEMPLATE_CACHE_TTL = "3600"

[[r2_buckets]]
binding     = "TEMPLATES"
bucket_name = "email-templates"

[[d1_databases]]
binding       = "DB"
database_name = "email-audit"
database_id   = "<YOUR_D1_DATABASE_ID>"
```

```sql
-- migrations/0001_audit.sql
CREATE TABLE IF NOT EXISTS email_audit (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  recipient   TEXT    NOT NULL,
  template_key TEXT   NOT NULL,
  status_code INTEGER,
  sent_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_recipient ON email_audit(recipient);
CREATE INDEX IF NOT EXISTS idx_sent_at   ON email_audit(sent_at);
```

```bash
# Create R2 bucket and D1 database
npx wrangler r2 bucket create email-templates
npx wrangler d1 create email-audit
npx wrangler d1 execute email-audit --file=migrations/0001_audit.sql

# Upload a sample Handlebars template
cat > /tmp/welcome_en.hbs <<'HBS'
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Welcome to {{appName}}</title></head>
<body>
  <h1>Hi {{firstName}},</h1>
  <p>Welcome to <strong>{{appName}}</strong>! Your account is ready.</p>
  <p><a >Get started</a></p>
</body>
</html>
HBS

npx wrangler r2 object put email-templates/welcome/en.hbs \
  --file=/tmp/welcome_en.hbs \
  --content-type="text/x-handlebars-template"
```

## Section 2 — Implementation

```typescript
// src/index.ts
import Handlebars from "handlebars";

export interface Env {
  TEMPLATES: R2Bucket;
  DB: D1Database;
  SENDING_DOMAIN: string;
  TEMPLATE_CACHE_TTL: string;
}

interface SendRequest {
  templateKey: string; // e.g. "welcome/en.hbs"
  to: string;
  subject: string;
  data: Record<string, unknown>;
}

// Fetch template string from R2 with Cache API wrapping
async function fetchTemplate(
  bucket: R2Bucket,
  key: string,
  cacheTtl: number
): Promise<string> {
  const cache = caches.default;
  const cacheKey = new Request(`https://r2-cache.internal/${key}`);

  // Attempt cache hit
  const cached = await cache.match(cacheKey);
  if (cached) {
    return cached.text();
  }

  // Cache miss — fetch from R2
  const obj = await bucket.get(key);
  if (!obj) {
    throw new Error(`Template not found in R2: ${key}`);
  }
  const templateStr = await obj.text();

  // Store in cache
  const cacheResponse = new Response(templateStr, {
    headers: {
      "Cache-Control": `public, max-age=${cacheTtl}`,
      "Content-Type": "text/plain",
    },
  });
  // waitUntil not available here; fire-and-forget is acceptable for cache population
  cache.put(cacheKey, cacheResponse);

  return templateStr;
}

// Render template with Handlebars
function renderTemplate(
  templateStr: string,
  data: Record<string, unknown>
): string {
  const compiled = Handlebars.compile(templateStr, { strict: true });
  return compiled(data);
}

// Send via MailChannels
async function sendViaMailChannels(
  from: string,
  to: string,
  subject: string,
  html: string
): Promise<number> {
  const payload = {
    personalizations: [{ to: [{ email: to }] }],
    from: { email: from, name: "Orchords" },
    subject,
    content: [{ type: "text/html", value: html }],
  };

  const res = await fetch("https://api.mailchannels.net/tx/v1/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  return res.status;
}

// Write audit record to D1
async function auditSend(
  db: D1Database,
  recipient: string,
  templateKey: string,
  statusCode: number
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO email_audit (recipient, template_key, status_code)
       VALUES (?1, ?2, ?3)`
    )
    .bind(recipient, templateKey, statusCode)
    .run();
}

// Main handler
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    let body: SendRequest;
    try {
      body = await request.json<SendRequest>();
    } catch {
      return new Response("Invalid JSON", { status: 400 });
    }

    const { templateKey, to, subject, data } = body;
    if (!templateKey || !to || !subject) {
      return new Response("Missing required fields", { status: 422 });
    }

    let html: string;
    try {
      const cacheTtl = parseInt(env.TEMPLATE_CACHE_TTL, 10);
      const templateStr = await fetchTemplate(env.TEMPLATES, templateKey, cacheTtl);
      html = renderTemplate(templateStr, data ?? {});
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      return new Response(`Template error: ${message}`, { status: 500 });
    }

    const from = `noreply@${env.SENDING_DOMAIN}`;
    const statusCode = await sendViaMailChannels(from, to, subject, html);

    ctx.waitUntil(auditSend(env.DB, to, templateKey, statusCode));

    if (statusCode >= 200 && statusCode < 300) {
      return new Response(JSON.stringify({ status: "sent", code: statusCode }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    return new Response(`Delivery error, status: ${statusCode}`, { status: 502 });
  },
};
```

## Section 3 — Local Dev & Testing

```bash
# Install Handlebars (and types)
npm install handlebars
npm install --save-dev @types/handlebars

# Type-check
npx tsc --noEmit

# Run locally with miniflare-backed R2/D1
npx wrangler dev --local

# Send a test request
curl -X POST http://localhost:8787 \
  -H 'Content-Type: application/json' \
  -d '{
    "templateKey": "welcome/en.hbs",
    "to": "user@example.com",
    "subject": "Welcome!",
    "data": {
      "firstName": "Alice",
      "appName": "Orchords",
      "ctaUrl": "https://example.com/dashboard"
    }
  }'

# Query audit log
npx wrangler d1 execute email-audit \
  --command="SELECT * FROM email_audit ORDER BY sent_at DESC LIMIT 10;"

# List R2 templates
npx wrangler r2 object list email-templates

# Update a template without redeploying
npx wrangler r2 object put email-templates/welcome/en.hbs \
  --file=./templates/welcome_en_v2.hbs
# Cache expires within TEMPLATE_CACHE_TTL seconds (default 3600)
```

---

## Anti-patterns

- **Compiling Handlebars on every request without caching** — `Handlebars.compile()` is synchronous and CPU-bound; compiling a complex template on each request wastes CPU time. Use the Cache API to store the raw template string and call `compile()` once per cache miss.
- **Storing rendered HTML in R2** — Rendered output is data-specific; store the reusable `.hbs` source, not the rendered result. Storing rendered HTML means template updates require regenerating every pre-rendered variant.
- **Missing `ctx.waitUntil` for audit writes** — If the audit `INSERT` is not wrapped in `waitUntil`, the Worker runtime may terminate before it completes, silently losing audit records.

---

## Gotchas

- The Cache API in Workers stores responses keyed by `Request`; the URL must be consistent — use a stable synthetic URL (e.g. `https://r2-cache.internal/<key>`) rather than the actual R2 object URL which includes signed query parameters.
- Handlebars `strict: true` mode throws on missing template variables rather than rendering empty string — use it to catch data shape mismatches early.
- R2 `get()` returns `null` (not a thrown error) when the key does not exist; always null-check the result before calling `.text()`.
- `wrangler r2 object put` with no `--content-type` defaults to `application/octet-stream`; set `--content-type` explicitly for readability, though it does not affect Worker behavior.

---

## Verification

```bash
# Confirm template exists in R2
npx wrangler r2 object get email-templates/welcome/en.hbs --file=/dev/stdout

# Check audit log for recent sends
npx wrangler d1 execute email-audit \
  --command="SELECT recipient, template_key, status_code, sent_at FROM email_audit ORDER BY sent_at DESC LIMIT 5;"

# Deploy and smoke-test
npx wrangler deploy
curl -X POST https://email-template-sender.<account>.workers.dev \
  -H 'Content-Type: application/json' \
  -d '{"templateKey":"welcome/en.hbs","to":"smoke@example.com","subject":"Smoke test","data":{"firstName":"Bot","appName":"Orchords","ctaUrl":"https://example.com"}}'
```

---

## Related

- `mailchannels-dkim-workers-email-auth.md`
- `workers-email-bounce-webhook-handler.md`

---

## Sources

- Cloudflare R2 — https://developers.cloudflare.com/r2/
- Handlebars.js — https://handlebarsjs.com/guide/
- MailChannels Send API — https://api.mailchannels.net/tx/v1/documentation
- Cloudflare Cache API — https://developers.cloudflare.com/workers/runtime-apis/cache/
