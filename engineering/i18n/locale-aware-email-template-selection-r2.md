# Locale-Aware Email Template Selection from R2

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You store HTML email templates in Cloudflare R2 and need to serve each user the right
locale variant — falling back gracefully through the BCP-47 hierarchy when an exact
match does not exist.

## Context
Cloudflare R2 provides zero-egress object storage accessible from any Worker via the
`env.BUCKET` binding. Email templates are stored with keys like
`emails/welcome/pt-BR.html`, `emails/welcome/pt.html`, and
`emails/welcome/en.html`. A Worker resolves the user's locale, walks the fallback chain,
and fetches the first key that exists before handing the template to the sending service.

---

## R2 Key Convention and Template Structure

Organize templates under a predictable path scheme so the resolution logic stays generic:

```
emails/
  {template-name}/
    {locale}.html          ← exact locale  e.g. pt-BR.html
    {language}.html        ← language-only e.g. pt.html
    en.html                ← ultimate English fallback
```

Each template is a self-contained HTML file with `{{variable}}` placeholders:

```html
<!-- emails/welcome/pt-BR.html -->
<!DOCTYPE html>
<html lang="pt-BR" dir="ltr">
<head><meta charset="utf-8"><title>Bem-vindo, {{name}}!</title></head>
<body>
  <h1>Bem-vindo ao {{appName}}, {{name}}!</h1>
  <p>Obrigado por se cadastrar. Sua conta está pronta.</p>
  <p><a >Começar agora</a></p>
</body>
</html>
```

---

## Locale Fallback Chain Builder

Build the ordered list of R2 keys to try from most-specific to least-specific:

```typescript
// src/lib/locale-fallback.ts

/**
 * Returns an ordered array of BCP-47 subtags to try, most-specific first.
 * "pt-BR"  → ["pt-BR", "pt", "en"]
 * "zh-Hant-TW" → ["zh-Hant-TW", "zh-Hant", "zh", "en"]
 */
export function buildFallbackChain(locale: string, ultimateFallback = "en"): string[] {
  const chain: string[] = [];
  const parts = locale.replace(/_/g, "-").split("-");

  // Add progressively shorter tags
  for (let i = parts.length; i > 0; i--) {
    const tag = parts.slice(0, i).join("-");
    if (!chain.includes(tag)) chain.push(tag);
  }

  // Append ultimate fallback if not already present
  if (!chain.includes(ultimateFallback)) {
    chain.push(ultimateFallback);
  }

  return chain;
}
```

---

## R2 Template Fetcher with Fallback

```typescript
// src/lib/email-templates.ts
import { buildFallbackChain } from "./locale-fallback";

export interface Env {
  BUCKET: R2Bucket;
}

export interface TemplateResult {
  html: string;
  resolvedLocale: string;
}

/**
 * Fetches the best-matching email template from R2.
 * Walks the fallback chain and returns the first hit.
 */
export async function fetchEmailTemplate(
  bucket: R2Bucket,
  templateName: string,
  locale: string,
): Promise<TemplateResult> {
  const chain = buildFallbackChain(locale);

  for (const tag of chain) {
    const key = `emails/${templateName}/${tag}.html`;
    const obj = await bucket.get(key);

    if (obj !== null) {
      return {
        html: await obj.text(),
        resolvedLocale: tag,
      };
    }
  }

  throw new Error(
    `No template found for "${templateName}" in chain: ${chain.join(", ")}`,
  );
}

/**
 * Simple mustache-style variable substitution.
 * Replaces {{key}} tokens with values from the data map.
 */
export function renderTemplate(
  html: string,
  data: Record<string, string>,
): string {
  return html.replace(/\{\{(\w+)\}\}/g, (_, key) => {
    if (!(key in data)) {
      console.warn(`[email-template] Missing variable: ${key}`);
      return "";
    }
    return data[key];
  });
}
```

---

## Worker Endpoint — Locale-Aware Send Pipeline

```typescript
// src/worker.ts
import { fetchEmailTemplate, renderTemplate, type Env } from "./lib/email-templates";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const body = await request.json<{
      to: string;
      locale: string;
      templateName: string;
      data: Record<string, string>;
    }>();

    const { to, locale, templateName, data } = body;

    // Fetch the best available template from R2
    const { html: rawHtml, resolvedLocale } = await fetchEmailTemplate(
      env.BUCKET,
      templateName,
      locale,
    );

    // Substitute variables
    const finalHtml = renderTemplate(rawHtml, data);

    // Hand off to your sending service (MailChannels, Resend, etc.)
    const sendRes = await fetch("https://api.mailchannels.net/tx/v1/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        personalizations: [{ to: [{ email: to }] }],
        from: { email: "noreply@example.com" },
        subject: extractSubject(rawHtml),
        content: [{ type: "text/html", value: finalHtml }],
      }),
    });

    return new Response(
      JSON.stringify({ ok: sendRes.ok, resolvedLocale }),
      { status: sendRes.ok ? 200 : 502, headers: { "Content-Type": "application/json" } },
    );
  },
};

function extractSubject(html: string): string {
  const m = html.match(/<title>([^<]*)<\/title>/i);
  return m ? m[1] : "Notification";
}
```

---

## Anti-patterns

- **Storing templates in KV** — KV values max at 25 MB and KV is optimized for small
  key-value pairs; R2 is the correct store for HTML documents.
- **Building locale from `Accept-Language` alone** — persist the user's explicit locale
  preference to your database and use `Accept-Language` only as a bootstrap signal.
- **Skipping the fallback chain** — a `pt-BR` user with no `pt-BR` template silently
  receives an error or the wrong language if you don't walk the chain.
- **String-interpolating user data directly into HTML** — always sanitize or escape user-
  supplied values before substitution to prevent XSS in email clients that render HTML.
- **Fetching a template on every request without caching** — R2 reads are fast but not
  free; cache hot templates in the Worker's in-memory module scope for the instance
  lifetime, or use a short-TTL KV cache for frequently sent templates.

---

## Gotchas

- R2 key names are case-sensitive: `emails/welcome/pt-BR.html` and
  `emails/welcome/pt-br.html` are different objects.
- BCP-47 tags are conventionally case-normalized (`pt-BR`, not `pt-br`), but
  incoming locale strings from clients may be lowercase; normalize before building
  the chain: `locale.replace(/^(\w+)-(\w+)$/, (_, l, r) => l + "-" + r.toUpperCase())`.
- The R2 `get()` call counts as a Class B operation (billed); for high-volume transactional
  email, cache the resolved template bytes in a bounded in-process LRU.
- `obj.text()` streams the body; call it only once and store the result.

---

## Verification

```bash
# Upload a test template
wrangler r2 object put MY_BUCKET emails/welcome/pt-BR.html \
  --file ./templates/welcome-pt-BR.html --content-type text/html

# Confirm the object exists
wrangler r2 object get MY_BUCKET emails/welcome/pt-BR.html --pipe | head -5

# Test fallback: request pt-BR, only pt exists
curl -X POST http://localhost:8787/ \
  -H "Content-Type: application/json" \
  -d '{"to":"test@example.com","locale":"pt-BR","templateName":"welcome","data":{"name":"Ana","appName":"Acme","ctaUrl":"https://acme.com/start"}}'
# Expect: {"ok":true,"resolvedLocale":"pt"}
```

---

## Related

- `i18n-content-fallback-chain-kv-workers.md`
- `transactional-email-push-localization.md`
- `locale-fallback-chain.md`
- `translation-kv-caching-ttl-strategy.md`
- `workers-locale-context-service-bindings.md`

---

## Sources

- <https://developers.cloudflare.com/r2/api/workers/workers-api-reference/>
- <https://developers.cloudflare.com/r2/api/workers/workers-api-usage/>
- <https://www.rfc-editor.org/rfc/rfc5646> (BCP-47 language tags)
- <https://mailchannels.zendesk.com/hc/en-us/articles/4565898358413>
