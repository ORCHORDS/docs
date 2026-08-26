# Template-Based Email Rendering in Workers with R2 and KV Cache

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Hardcoding HTML email templates inside Worker source forces a full redeploy for every copy tweak. Storing Handlebars templates as R2 objects and caching compiled outputs in KV allows non-engineers to update templates without touching code, while keeping render latency low through a 1-hour KV cache.

---

## Context

Handlebars is a logic-less template engine with a compact runtime suitable for Worker bundle-size constraints. Templates are stored as plain `.hbs` files in an R2 bucket keyed by `templates/{templateName}.hbs`. On first use the Worker fetches the template from R2, compiles it with Handlebars, caches the compiled template source string in KV with a 3600-second TTL, and renders it with a sanitised context object. CSS is inlined via a simple regex-based style block extraction and attribute injection so that email clients that strip `<style>` tags still render correctly. The rendered HTML and a plain-text fallback are sent via MailChannels.

---

## Section 1 — wrangler.toml / Schema

```toml
name = "email-template-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[vars]
TEMPLATE_CACHE_TTL = "3600"   # seconds

[[r2_buckets]]
binding = "TEMPLATES"
bucket_name = "email-templates"

[[kv_namespaces]]
binding = "TEMPLATE_CACHE"
id = "YOUR_KV_NAMESPACE_ID"
```

## Section 2 — Worker implementation

```typescript
import Handlebars from 'handlebars';

export interface Env {
  TEMPLATES: R2Bucket;
  TEMPLATE_CACHE: KVNamespace;
  TEMPLATE_CACHE_TTL: string;
}

// Sanitise context to prevent prototype pollution via template injection
function sanitiseContext(ctx: Record<string, unknown>): Record<string, unknown> {
  return JSON.parse(
    JSON.stringify(ctx, (_key, value) => {
      if (typeof value === 'function') return undefined;
      return value;
    })
  );
}

async function getTemplate(
  env: Env,
  templateName: string
): Promise<HandlebarsTemplateDelegate> {
  const cacheKey = `tpl:${templateName}`;
  const ttl = parseInt(env.TEMPLATE_CACHE_TTL, 10);

  // 1. Try KV cache
  const cached = await env.TEMPLATE_CACHE.get(cacheKey);
  if (cached) {
    return Handlebars.template(JSON.parse(cached));
  }

  // 2. Fetch from R2
  const r2Key = `templates/${templateName}.hbs`;
  const obj = await env.TEMPLATES.get(r2Key);
  if (!obj) throw new Error(`Template not found: ${r2Key}`);

  const source = await obj.text();

  // 3. Compile and cache the precompiled spec
  const precompiled = Handlebars.precompile(source);
  await env.TEMPLATE_CACHE.put(cacheKey, JSON.stringify(precompiled), {
    expirationTtl: ttl,
  });

  return Handlebars.template(JSON.parse(precompiled));
}

// Inline <style> block rules into matching elements (best-effort)
function inlineStyles(html: string): string {
  const styleMatch = html.match(/<style[^>]*>([\s\S]*?)<\/style>/i);
  if (!styleMatch) return html;

  const cssText = styleMatch[1];
  // Extract simple class rules: .class-name { property: value; ... }
  const ruleRegex = /\.([\w-]+)\s*\{([^}]+)\}/g;
  let ruleMatch: RegExpExecArray | null;
  const rules: Record<string, string> = {};

  while ((ruleMatch = ruleRegex.exec(cssText)) !== null) {
    const className = ruleMatch[1];
    const declarations = ruleMatch[2]
      .split(';')
      .map((d) => d.trim())
      .filter(Boolean)
      .join('; ');
    rules[className] = declarations;
  }

  let result = html;
  for (const [className, declarations] of Object.entries(rules)) {
    // Find elements with this class and append inline style
    const elementRegex = new RegExp(
      `(<[^>]+class="[^"]*\\b${className}\\b[^"]*"[^>]*)(>)`,
      'g'
    );
    result = result.replace(elementRegex, (_match, before, close) => {
      const styleAttr = before.includes('style=')
        ? before.replace(
            /style="([^"]*)"/,
            (_s: string, existing: string) => `style="${existing}; ${declarations}"`
          )
        : `${before} style="${declarations}"`;
      return `${styleAttr}${close}`;
    });
  }

  return result;
}

function htmlToText(html: string): string {
  return html
    .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

export async function renderAndSend(
  env: Env,
  templateName: string,
  to: string,
  subject: string,
  context: Record<string, unknown>
): Promise<Response> {
  const tplFn = await getTemplate(env, templateName);
  const safeCtx = sanitiseContext(context);
  const rawHtml = tplFn(safeCtx);
  const inlinedHtml = inlineStyles(rawHtml);
  const plainText = htmlToText(rawHtml);

  const payload = {
    personalizations: [{ to: [{ email: to }] }],
    from: { email: 'noreply@yourdomain.com', name: 'Orchords' },
    subject,
    content: [
      { type: 'text/plain', value: plainText },
      { type: 'text/html', value: inlinedHtml },
    ],
  };

  return fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }
    const body = await request.json<{
      template: string;
      to: string;
      subject: string;
      context: Record<string, unknown>;
    }>();
    const resp = await renderAndSend(
      env,
      body.template,
      body.to,
      body.subject,
      body.context
    );
    return new Response(String(resp.status), { status: resp.ok ? 200 : 502 });
  },
};
```

## Section 3 — Template upload helper

```typescript
// Run locally or as a one-off Worker route to upload templates to R2
export async function uploadTemplate(
  env: Env,
  templateName: string,
  hbsSource: string
): Promise<void> {
  await env.TEMPLATES.put(`templates/${templateName}.hbs`, hbsSource, {
    httpMetadata: { contentType: 'text/x-handlebars-template' },
  });
  // Bust the KV cache for this template
  await env.TEMPLATE_CACHE.delete(`tpl:${templateName}`);
  console.log(`Uploaded and cache-busted: ${templateName}`);
}

// Example template source (welcome.hbs)
/*
<!DOCTYPE html>
<html>
<head>
  <style>
    .header { background: #1a1a2e; color: #fff; padding: 24px; }
    .body   { font-family: sans-serif; padding: 16px; }
    .cta    { background: #e94560; color: #fff; padding: 12px 24px;
              border-radius: 4px; text-decoration: none; }
  </style>
</head>
<body>
  <div class="header"><h1>Welcome, {{firstName}}!</h1></div>
  <div class="body">
    <p>Thanks for joining {{orgName}}. Your account is ready.</p>
    <a  class="cta">Get Started</a>
  </div>
</body>
</html>
*/
```

---

## Anti-patterns

- **Fetching from R2 on every request** — R2 GET latency is 10-50 ms; on high-volume send paths this adds up. Always layer the KV cache in front of R2 reads.
- **Trusting context values without sanitisation** — Handlebars escapes HTML by default in `{{expr}}`, but triple-brace `{{{expr}}}` outputs raw HTML. Sanitise the context object and avoid triple-brace unless you control the data source.
- **Shipping compiled templates in the Worker bundle** — Bundling templates makes non-engineer updates impossible without a deploy. Keep templates in R2.
- **Ignoring plain-text part** — Many enterprise mail servers and accessibility tools rely on the `text/plain` part. Always include it alongside HTML.
- **Inlining entire external CSS files** — The regex inliner is intentionally simple. For complex stylesheets, use a purpose-built inliner or pre-inline during the upload step.

---

## Gotchas

- `Handlebars.precompile` returns a string of JavaScript source, not a function. Store and re-hydrate it with `Handlebars.template(JSON.parse(...))` — wrapping in `JSON.parse` is required because `precompile` returns a JS object literal, not valid JSON; use `Handlebars.precompile(source, { srcName: templateName })` for better error messages.
- KV `get` returns `null` on miss, not an empty string. Check `if (cached)` rather than `if (cached !== null)` to handle both null and empty-string edge cases.
- Handlebars must be listed in `package.json`; the Worker runtime does not include it. Bundle size impact is ~15 KB minified+gzipped.
- Template names are user-controlled in the example fetch handler; validate against an allowlist before passing to `getTemplate` to prevent path traversal to unintended R2 keys.
- MailChannels limits the `content` array to two entries (HTML + plain-text); adding additional parts may be silently dropped.

---

## Verification

```bash
# Upload a test template
npx wrangler r2 object put email-templates/templates/welcome.hbs \
  --file ./templates/welcome.hbs

# Deploy the Worker
npx wrangler deploy

# Send a rendered email
curl -s -X POST https://your-worker.workers.dev/ \
     -H 'Content-Type: application/json' \
     -d '{
       "template": "welcome",
       "to": "test@example.com",
       "subject": "Welcome!",
       "context": {"firstName": "Alice", "orgName": "Orchords", "ctaUrl": "https://example.com/start"}
     }'

# Confirm KV cache entry was written
npx wrangler kv key get --namespace-id YOUR_KV_NAMESPACE_ID 'tpl:welcome'
```

---

## Related

- `email-attachment-extraction-r2-workers.md`
- `email-rate-limiting-kv-mailchannels-workers.md`

---

## Sources

- Handlebars.js — https://handlebarsjs.com/
- Cloudflare KV — https://developers.cloudflare.com/kv/
- Cloudflare R2 Workers API — https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
- MailChannels Send API — https://docs.mailchannels.net/transactional-email/send-email
