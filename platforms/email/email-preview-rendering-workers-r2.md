# Email Preview Rendering with Workers and R2

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Marketing and engineering teams need to inspect the fully-merged HTML of an email template before a campaign sends, but passing raw HTML around in Slack is error-prone and leaks PII test data. You want a secure, time-limited preview URL that renders the final HTML with sample variables merged, served from R2 through a Cloudflare Worker with a strict Content-Security-Policy.

## Context

Cloudflare R2 stores versioned email template snapshots keyed by `templates/{id}/{version}.html`. A Worker generates previews by fetching a template, applying a sample variable map, and writing the rendered HTML to a separate `previews/` R2 prefix with expiry encoded in custom metadata. A second route serves those previews with a tight CSP so arbitrary JavaScript in a template cannot execute in a reviewer's browser. A scheduled Worker (Cron Trigger) sweeps expired preview objects daily.

## Storing and Rendering Template Snapshots

```typescript
// src/preview.ts
export interface Env {
  EMAIL_TEMPLATES: R2Bucket;
  PREVIEW_STORE: R2Bucket;
}

export async function storeTemplate(
  env: Env,
  templateId: string,
  version: string,
  html: string
): Promise<void> {
  await env.EMAIL_TEMPLATES.put(
    `templates/${templateId}/${version}.html`,
    html,
    {
      httpMetadata: { contentType: 'text/html; charset=utf-8' },
      customMetadata: { templateId, version, createdAt: new Date().toISOString() },
    }
  );
}

export async function generatePreview(
  env: Env,
  templateId: string,
  version: string,
  vars: Record<string, string>
): Promise<string> {
  const obj = await env.EMAIL_TEMPLATES.get(
    `templates/${templateId}/${version}.html`
  );
  if (!obj) throw new Error(`Template ${templateId}@${version} not found in R2`);

  let html = await obj.text();
  for (const [k, v] of Object.entries(vars)) {
    // Replace {{key}} placeholders; escape value to prevent HTML injection
    const safe = v.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    html = html.replaceAll(`{{${k}}}`, safe);
  }

  const previewKey = `previews/${templateId}/${version}/${crypto.randomUUID()}.html`;
  const expiresAt = new Date(Date.now() + 24 * 3_600_000).toISOString();

  await env.PREVIEW_STORE.put(previewKey, html, {
    httpMetadata: { contentType: 'text/html; charset=utf-8' },
    customMetadata: { expiresAt },
  });

  return previewKey;
}
```

## Serving Previews via Worker Fetch Handler

```typescript
// src/worker.ts
import { generatePreview, storeTemplate, type Env } from './preview';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/templates') {
      const { templateId, version, html } = await request.json<{
        templateId: string; version: string; html: string;
      }>();
      await storeTemplate(env, templateId, version, html);
      return Response.json({ ok: true, key: `templates/${templateId}/${version}.html` });
    }

    if (request.method === 'POST' && url.pathname === '/preview') {
      const { templateId, version, vars } = await request.json<{
        templateId: string; version: string; vars: Record<string, string>;
      }>();
      const previewKey = await generatePreview(env, templateId, version, vars);
      return Response.json({
        previewUrl: `${url.origin}/render/${encodeURIComponent(previewKey)}`,
        expiresIn: '24h',
      });
    }

    if (request.method === 'GET' && url.pathname.startsWith('/render/')) {
      const key = decodeURIComponent(url.pathname.slice('/render/'.length));
      const obj = await env.PREVIEW_STORE.get(key);
      if (!obj) return new Response('Preview not found', { status: 404 });

      const expiresAt = obj.customMetadata?.expiresAt;
      if (expiresAt && Date.parse(expiresAt) < Date.now()) {
        await env.PREVIEW_STORE.delete(key);
        return new Response('Preview expired', { status: 410 });
      }

      return new Response(obj.body, {
        headers: {
          'Content-Type': 'text/html; charset=utf-8',
          'X-Frame-Options': 'DENY',
          'Content-Security-Policy':
            "default-src 'none'; style-src 'unsafe-inline'; img-src data: https:; font-src https:;",
          'Cache-Control': 'no-store',
        },
      });
    }

    return new Response('Not found', { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

## Cron-Based Cleanup of Expired Previews

```typescript
// src/cleanup.ts — attach to a Cron Trigger (e.g. "0 3 * * *")
export async function sweepExpiredPreviews(env: Env): Promise<number> {
  let deleted = 0;
  let cursor: string | undefined;

  do {
    const listed = await env.PREVIEW_STORE.list({
      prefix: 'previews/',
      cursor,
      limit: 500,
    });

    for (const obj of listed.objects) {
      const expiresAt = obj.customMetadata?.expiresAt;
      if (expiresAt && Date.parse(expiresAt) < Date.now()) {
        await env.PREVIEW_STORE.delete(obj.key);
        deleted++;
      }
    }

    cursor = listed.truncated ? listed.cursor : undefined;
  } while (cursor);

  return deleted;
}

// In your scheduled handler:
export const scheduled: ExportedHandlerScheduledHandler<Env> = async (_event, env) => {
  const count = await sweepExpiredPreviews(env);
  console.log(`Swept ${count} expired preview objects`);
};
```

## Anti-patterns

- Re-fetching and re-merging the template on every preview request — snapshot once per (version, var-set) to avoid R2 read amplification.
- Serving preview HTML without `Content-Security-Policy` — a broken or malicious template can run JavaScript in the reviewer's session.
- Storing preview objects without expiry and no cleanup job — preview objects accumulate silently and inflate R2 storage costs.

## Gotchas

- R2 has no native object TTL; expiry must be enforced by reading `customMetadata.expiresAt` in the Worker at serve time and by the nightly cleanup Cron.
- `encodeURIComponent` the R2 key when embedding it in a URL path; keys contain `/` which browsers interpret as path segments.

## Verification

```bash
# Upload a template
curl -X POST https://preview.example.com/templates \
  -H 'Content-Type: application/json' \
  -d '{"templateId":"welcome","version":"v4","html":"<h1>Hello {{name}}</h1><p>{{tagline}}</p>"}'

# Generate a preview with sample vars
curl -X POST https://preview.example.com/preview \
  -H 'Content-Type: application/json' \
  -d '{"templateId":"welcome","version":"v4","vars":{"name":"Alice","tagline":"Thanks for joining"}}'

# Open the returned previewUrl in a browser; expect merged HTML with tight CSP headers
curl -I "$(curl -s ... | jq -r .previewUrl)"
# Expect: Content-Security-Policy: default-src 'none'; ...
```

## Related

- `email/email-template-versioning.md`
- `email/email-transactional-template-personalization-r2-workers.md`
- `email/email-template-mjml-cloudflare-pages.md`

## Sources

- https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
- https://developers.cloudflare.com/workers/runtime-apis/scheduled-event/
- https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy
