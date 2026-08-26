# Email Template Rendering Engine Using Workers + R2

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You need to send richly formatted transactional emails (welcome, password reset, invoice, shipment notice) whose HTML layout is maintained by a design team separately from application code. Hardcoding HTML in TypeScript string literals makes templates unmanageable and forces deploys for copy changes. You want a template store that non-engineers can update, with variable substitution, conditional blocks, and shared layout inheritance — all rendered at the edge with zero cold-start latency.

## Context

Cloudflare R2 is an S3-compatible object store with no egress fees. A Cloudflare Worker can read from R2 using a binding, render a template, and hand the result to MailChannels (or another SMTP relay) in a single request without leaving the Cloudflare network. R2 objects are globally consistent within a region and can be versioned by path convention. Template rendering in Workers must be done with a zero-dependency or bundled engine because `npm install` packages with Node built-ins will fail unless polyfilled.

Handlebars proper requires `fs` and `vm`; the recommended approach is a lightweight mustache-style replacement loop written in ~60 lines of TypeScript. For complex logic (loops, nested partials) use a pre-compiled template approach where the template is a JS function stored as a Worker module, or adopt `mustache.js` (pure ESM, no Node built-ins, ~14 KB).

## Solution

### R2 Bucket + Worker Binding Setup

```toml
# wrangler.toml
name = "email-renderer"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[r2_buckets]]
binding = "EMAIL_TEMPLATES"
bucket_name = "email-templates-prod"
```

### Template File Conventions in R2

```
email-templates-prod/
  layouts/
    base.html          # <!DOCTYPE html> wrapper with {{slot}}
  partials/
    header.html
    footer.html
  templates/
    welcome/
      v1.html          # pinned version
      latest.html      # symlink-by-convention: always most recent
    password-reset/
      latest.html
    invoice/
      latest.html
```

### Core Template Engine (TypeScript)

```typescript
// src/template-engine.ts

export interface RenderContext {
 | number | boolean | RenderContext | RenderContext[];
}

/**
 * Resolve a dotted path like "user.firstName" against ctx.
 */
function resolvePath(ctx: RenderContext, path: string): unknown {
  return path.split('.').reduce((acc: unknown, key) => {
    if (acc && typeof acc === 'object') return (acc as RenderContext)[key];
    return undefined;
  }, ctx);
}

/**
 * Replace {{variable}} and {{nested.path}} tokens.
 */
function interpolate(template: string, ctx: RenderContext): string {
  return template.replace(/\{\{([^#\/][^}]*)\}\}/g, (_match, path) => {
    const val = resolvePath(ctx, path.trim());
    if (val === null || val === undefined) return '';
    // Escape HTML to prevent injection via user-supplied values.
    return String(val)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  });
}

/**
 * Process {{#if condition}}...{{/if}} blocks.
 * Only evaluates truthiness, no expressions.
 */
function processConditionals(template: string, ctx: RenderContext): string {
  return template.replace(
    /\{\{#if ([^}]+)\}\}([\s\S]*?)\{\{\/if\}\}/g,
    (_match, condition, block) => {
      const val = resolvePath(ctx, condition.trim());
      return val ? block : '';
    }
  );
}

/**
 * Process {{#each items}}...{{/each}} blocks.
 * Inside the block, {{this.field}} refers to the current item.
 */
function processLoops(template: string, ctx: RenderContext): string {
  return template.replace(
    /\{\{#each ([^}]+)\}\}([\s\S]*?)\{\{\/each\}\}/g,
    (_match, listPath, block) => {
      const items = resolvePath(ctx, listPath.trim());
      if (!Array.isArray(items)) return '';
      return items
        .map((item) =>
          interpolate(block, { ...ctx, this: item as RenderContext })
        )
        .join('');
    }
  );
}

export function renderTemplate(template: string, ctx: RenderContext): string {
  let output = processLoops(template, ctx);
  output = processConditionals(output, ctx);
  output = interpolate(output, ctx);
  return output;
}
```

### R2 Template Loader

```typescript
// src/template-loader.ts
import { renderTemplate, RenderContext } from './template-engine';

export interface Env {
  EMAIL_TEMPLATES: R2Bucket;
}

/**
 * Load a template by name and optional version from R2,
 * resolve its layout, inject rendered content.
 */
export async function loadAndRender(
  env: Env,
  templateName: string,
  ctx: RenderContext,
  version: string = 'latest'
): Promise<{ html: string; text: string }> {
  const templateKey = `templates/${templateName}/${version}.html`;
  const layoutKey = 'layouts/base.html';

  const [templateObj, layoutObj] = await Promise.all([
    env.EMAIL_TEMPLATES.get(templateKey),
    env.EMAIL_TEMPLATES.get(layoutKey),
  ]);

  if (!templateObj) {
    throw new Error(`Template not found: ${templateKey}`);
  }
  if (!layoutObj) {
    throw new Error('Base layout not found in R2');
  }

  const [templateHtml, layoutHtml] = await Promise.all([
    templateObj.text(),
    layoutObj.text(),
  ]);

  // Render the inner template first.
  const innerHtml = renderTemplate(templateHtml, ctx);

  // Inject into layout via {{slot}} token.
  const fullHtml = layoutHtml.replace('{{slot}}', innerHtml);

  // Second pass: interpolate layout-level variables (subject, preheader, etc.).
  const finalHtml = renderTemplate(fullHtml, ctx);

  // Derive plain-text from HTML (strip tags, preserve whitespace).
  const text = finalHtml
    .replace(/<style[\s\S]*?<\/style>/gi, '')
    .replace(/<[^>]+>/g, '')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();

  return { html: finalHtml, text };
}
```

### Worker Entry Point

```typescript
// src/index.ts
import { Env, loadAndRender } from './template-loader';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const body = await request.json<{
      template: string;
      version?: string;
      to: string;
      subject: string;
      context: Record<string, unknown>;
    }>();

    const { html, text } = await loadAndRender(
      env,
      body.template,
      body.context as Record<string, string>,
      body.version
    );

    // Send via MailChannels (or pass html/text back to caller).
    const mcResponse = await fetch('https://api.mailchannels.net/tx/v1/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        personalizations: [{ to: [{ email: body.to }] }],
        from: { email: 'noreply@example.com', name: 'Orchords' },
        subject: body.subject,
        content: [
          { type: 'text/plain', value: text },
          { type: 'text/html', value: html },
        ],
      }),
    });

    if (!mcResponse.ok) {
      const err = await mcResponse.text();
      return new Response(`Send failed: ${err}`, { status: 502 });
    }

    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

### Template Versioning via R2 Metadata

```typescript
// src/publish-template.ts  (run from CI, not the Worker)
import { S3Client, PutObjectCommand } from '@aws-sdk/client-s3';

const client = new S3Client({
  region: 'auto',
  endpoint: `https://${process.env.CF_ACCOUNT_ID}.r2.cloudflarestorage.com`,
  credentials: {
    accessKeyId: process.env.R2_ACCESS_KEY_ID!,
    secretAccessKey: process.env.R2_SECRET_ACCESS_KEY!,
  },
});

async function publishTemplate(name: string, html: string, semver: string) {
  const now = new Date().toISOString();

  // Pin versioned copy.
  await client.send(
    new PutObjectCommand({
      Bucket: 'email-templates-prod',
      Key: `templates/${name}/${semver}.html`,
      Body: html,
      ContentType: 'text/html',
      Metadata: { 'published-at': now, version: semver },
    })
  );

  // Overwrite latest pointer.
  await client.send(
    new PutObjectCommand({
      Bucket: 'email-templates-prod',
      Key: `templates/${name}/latest.html`,
      Body: html,
      ContentType: 'text/html',
      Metadata: { 'published-at': now, 'points-to': semver },
    })
  );

  console.log(`Published ${name}@${semver}`);
}
```

## Implementation Details

- R2 GET latency inside a Worker colocated in the same region is typically 10–30 ms. Cache frequently used templates with `Cache-Control` metadata or a Worker-level Map for the duration of a single isolate lifetime (not shared across requests).
- Layouts and partials should be resolved in parallel using `Promise.all` to avoid serial waterfall fetches.
- Store templates as UTF-8; R2 preserves encoding. The `text()` method on an R2ObjectBody returns a decoded string.
- Template names must be URL-safe. Validate the `templateName` parameter before constructing the R2 key to prevent path traversal (`../../etc/passwd` style injection).
- HTML email best practices: inline all CSS before sending (use a CI step, not the Worker — inlining in the Worker wastes CPU), use `<table>`-based layouts for Outlook compatibility, set `<meta charset="UTF-8">`, include a preheader `<span>` with `font-size:0; max-height:0; overflow:hidden;`.

## Anti-patterns

- **Storing templates in Worker source code** — forces a deploy for every copy change and bloats bundle size.
- **Using Handlebars npm package directly** — it pulls in `fs` and `vm` Node built-ins, causing Worker boot failures unless extensively polyfilled.
- **Fetching templates on every send without caching** — at high volume this adds R2 read costs and latency. Cache the compiled output in the Workers KV or use a short-lived in-memory cache.
- **Skipping HTML entity escaping on user-supplied variables** — allows stored XSS in email previews that render HTML in a browser (webmail).
- **Using `latest.html` as the only key** — makes rollback impossible. Always write versioned copies first.

## Gotchas

- R2 keys are case-sensitive. `Welcome/latest.html` and `welcome/latest.html` are different objects.
- `r2Object.text()` consumes the body stream. You cannot call it twice. If you need the raw bytes and the text, use `r2Object.arrayBuffer()` and decode manually.
- Workers CPU time limit is 10 ms on the free plan, 30 s on paid. Template rendering of a 50 KB HTML file is typically under 2 ms, well within budget.
- The `EMAIL_TEMPLATES` binding is read-only at runtime. Writes (template publishing) must use the R2 S3-compatible API with credentials from CI/CD, not from the Worker itself.
- R2 does not support server-side copy/symlinks. The "latest" pointer pattern requires writing the full file content twice per publish.

## Verification

```bash
# Upload a test template
wrangler r2 object put email-templates-prod/templates/welcome/latest.html \
  --file ./templates/welcome.html

# Upload base layout
wrangler r2 object put email-templates-prod/layouts/base.html \
  --file ./layouts/base.html

# Test render via local dev
curl -X POST http://localhost:8787 \
  -H 'Content-Type: application/json' \
  -d '{"template":"welcome","to":"test@example.com","subject":"Hi","context":{"user":{"firstName":"Ada"}}}'

# Confirm R2 object exists
wrangler r2 object get email-templates-prod/templates/welcome/latest.html --file /tmp/check.html
```

## Related

- `documentation/docs/policies/email/workers-transactional-email-queue.md`
- `documentation/docs/policies/email/workers-email-suppression-list-kv.md`
- Cloudflare R2 Workers binding docs: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- MailChannels Workers Send API: https://support.mailchannels.com/hc/en-us/articles/4565898358797

## Sources

- Cloudflare R2 docs — Workers API Reference (2025)
- MailChannels transactional send via Workers (2025)
- Email on Acid — HTML email best practices guide (2024)
- WHATWG HTML spec — entity encoding requirements
