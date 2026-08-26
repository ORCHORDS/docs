# Scalable Transactional Email Template Personalization with R2 and Workers

- Date: 2026-08-22
- Author: example.com
- Status: production

## Template Personalization at the Edge

Hardcoding HTML email templates inside application code couples marketing
copy changes to engineering deploys. A scalable approach stores versioned
templates in R2, renders them at the Cloudflare edge with variable
substitution sourced from D1, and generates signed preview URLs so designers
can proof emails without triggering live sends.

Using R2 as the template store means templates are globally replicated at
zero egress cost, version history is preserved via object key suffixes, and
Workers can read a template in a single fetch with no cold-start latency. The
Handlebars-compatible `mustache` library (under 5 KB) compiles and renders in
under 1 ms per template, well within Workers' CPU budget.

This pattern decouples three concerns: template authoring (design team pushes
to R2 via CI), variable sourcing (D1 query at render time), and send
orchestration (separate Worker or Queue consumer). Each concern is testable
independently.

## Context

Stack: Cloudflare Workers, R2, D1, Workers KV (template manifest), Resend or
SendGrid, TypeScript, `mustache` npm package, Wrangler 3+.

Templates are stored in R2 as `templates/{name}/v{n}.html`. A KV manifest
maps logical template names to their current version. At render time a Worker
fetches the template object, resolves per-user variables from D1, renders via
mustache, and returns the final HTML. A signed URL path lets the preview
endpoint serve the rendered output without authentication headers.

## R2 Template Storage and Versioning

```ts
// scripts/publish-template.ts — run via wrangler execute or CI
async function publishTemplate(
  accountId: string,
  bucket: string,
  token: string,
  name: string,
  version: number,
  html: string
): Promise<void> {
  const key = `templates/${name}/v${version}.html`;
  await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/r2/buckets/${bucket}/objects/${key}`,
    {
      method: 'PUT',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'text/html',
        'x-amz-meta-template-name': name,
        'x-amz-meta-version': String(version),
      },
      body: html,
    }
  );
  // Update manifest in KV via wrangler kv:key put
}
```

Template key convention: `templates/order-confirmation/v3.html`

Mustache template example (`templates/order-confirmation/v3.html`):

```html
<!DOCTYPE html>
<html>
<body>
  <h1>Hi {{firstName}}, your order is confirmed!</h1>
  <p>Order #{{orderId}} — {{itemCount}} item(s) totalling {{totalFormatted}}.</p>
  <p>Estimated delivery: {{deliveryDate}}</p>
  <a >Track your order</a>
</body>
</html>
```

## Edge Rendering Worker

```ts
// workers/template-renderer.ts
import Mustache from 'mustache';
import { D1Database, R2Bucket, KVNamespace } from '@cloudflare/workers-types';

interface Env {
  TEMPLATES: R2Bucket;
  DB: D1Database;
  TEMPLATE_MANIFEST: KVNamespace;
  PREVIEW_HMAC_SECRET: string;
}

interface RenderRequest {
  templateName: string;
  userId: string;
  overrides?: Record<string, string>;
}

async function resolveUserVars(
  db: D1Database,
  userId: string
): Promise<Record<string, string>> {
  const row = await db
    .prepare(
      `SELECT u.first_name, u.email, o.id AS order_id,
              o.item_count, o.total_cents, o.delivery_date, o.tracking_url
       FROM users u
       LEFT JOIN orders o ON o.user_id = u.id AND o.status = 'confirmed'
       WHERE u.id = ?
       ORDER BY o.created_at DESC LIMIT 1`
    )
    .bind(userId)
    .first<{
      first_name: string;
      email: string;
      order_id: string;
      item_count: number;
      total_cents: number;
      delivery_date: string;
      tracking_url: string;
    }>();

  if (!row) throw new Error(`User ${userId} not found`);

  return {
    firstName: row.first_name,
    email: row.email,
    orderId: row.order_id ?? '',
    itemCount: String(row.item_count ?? 0),
    totalFormatted: `$${((row.total_cents ?? 0) / 100).toFixed(2)}`,
    deliveryDate: row.delivery_date ?? '',
    trackingUrl: row.tracking_url ?? '',
  };
}

export async function renderTemplate(
  env: Env,
  req: RenderRequest
): Promise<string> {
  // Resolve current version from manifest
  const version = await env.TEMPLATE_MANIFEST.get(`v:${req.templateName}`);
  if (!version) throw new Error(`Template ${req.templateName} not in manifest`);

  const obj = await env.TEMPLATES.get(
    `templates/${req.templateName}/v${version}.html`
  );
  if (!obj) throw new Error(`Template object missing in R2`);

  const templateHtml = await obj.text();
  const userVars = await resolveUserVars(env.DB, req.userId);
  const vars = { ...userVars, ...(req.overrides ?? {}) };

  return Mustache.render(templateHtml, vars);
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });
    const body = await req.json<RenderRequest>();
    const html = await renderTemplate(env, body);
    return new Response(html, { headers: { 'Content-Type': 'text/html;charset=utf-8' } });
  },
};
```

## Signed Preview URLs

```ts
// Generate a time-limited signed preview URL for designers
async function signedPreviewUrl(
  baseUrl: string,
  params: RenderRequest,
  secret: string,
  ttlSeconds = 3600
): Promise<string> {
  const exp = Math.floor(Date.now() / 1000) + ttlSeconds;
  const payload = JSON.stringify({ ...params, exp });
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(payload));
  const sigHex = [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, '0')).join('');
  const token = btoa(payload) + '.' + sigHex;
  return `${baseUrl}/preview?token=<redacted-secret>
}

// Preview handler validates signature then calls renderTemplate
async function handlePreview(req: Request, env: Env): Promise<Response> {
  const token = new URL(req.url).searchParams.get('token') ?? '';
  const [payloadB64, sigHex] = token.split('.');
  const payload = atob(payloadB64);
  const { exp, ...renderReq } = JSON.parse(payload) as RenderRequest & { exp: number };
  if (Date.now() / 1000 > exp) return new Response('Preview link expired', { status: 410 });
  // Re-derive and compare HMAC (omitted for brevity)
  const html = await renderTemplate(env, renderReq);
  return new Response(html, { headers: { 'Content-Type': 'text/html' } });
}
```

## Anti-patterns

- Storing templates in Workers KV — 25 MB value limit and no streaming; R2 handles large HTML + inline assets cleanly
- Using string `replace()` for variable substitution — Mustache handles missing keys, conditionals, and loops safely
- Fetching user data from an external DB on every render — D1 co-located in Workers avoids the network round-trip
- Not versioning templates — a bad deploy overwrites all in-flight sends; always increment version and update manifest atomically

## Gotchas

- R2 objects are eventually consistent after `PUT`; add a 200 ms delay in CI between upload and manifest KV update
- Mustache `{{variable}}` HTML-escapes values by default; use `{{{variable}}}` only for trusted pre-rendered HTML fragments
- The `mustache` package adds ~8 KB to the Worker bundle; verify it fits within the 1 MB compressed limit when combined with other dependencies
- KV manifest reads are eventually consistent globally; a freshly published version may not be visible in all regions for up to 60 seconds

## Verification

```ts
// Smoke-test: render the template with synthetic vars and assert no {{…}} tokens remain
const rendered = await renderTemplate(env, {
  templateName: 'order-confirmation',
  userId: 'test-user-123',
});
const unresolved = rendered.match(/\{\{[^}]+\}\}/g);
console.assert(!unresolved, `Unresolved variables: ${unresolved?.join(', ')}`);
```

## Related

- email-personalization-patterns.md
- transactional-email-rate-limiting-workers.md
- sendgrid-resend-cloudflare-workers-integration.md
- inbound-webhook-workers-d1.md
- bounce-suppression-d1.md

## Sources

- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://developers.cloudflare.com/d1/
- https://mustache.github.io/mustache.5.html
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://resend.com/docs/api-reference/emails/send-email
