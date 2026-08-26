# Email Link Rewriting and UTM Injection with Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Outbound HTML emails need links enriched with UTM parameters for GA4 attribution, routed through
a click-tracking proxy, or scanned against a URL blocklist before delivery. Doing this inside
the ESP template is brittle and loses standardization across multiple templates. A Worker intercepts
the rendered HTML body, parses every `<a href>`, and rewrites links before the email is handed
to the ESP API — ensuring consistent UTM tagging, click proxy enrollment, and malicious URL
blocking across all campaigns and transactional sends.

## Context

Link rewriting happens in a Worker that sits between your application and the ESP. The Worker
receives a JSON payload containing the HTML body and campaign metadata, rewrites all `href`
attributes, and returns the mutated HTML. It uses a lightweight HTML parser (or a regex pipeline
for known-safe template output) rather than a full DOM — Workers cannot run a browser engine.
A KV-backed blocklist guards against accidentally mailing phishing URLs.

## Parsing and Rewriting href Attributes

```typescript
interface LinkRewriteOptions {
  utmSource: string;
  utmMedium: string;
  utmCampaign: string;
  utmContent?: string;
  proxyBase?: string;  // e.g. "https://click.example.com/r"
}

function rewriteLinks(html: string, opts: LinkRewriteOptions): string {
  // Targets  in <a> tags only — avoids rewriting image src or CSS url()
  return html.replace(
    /(<a\s[^>]*]+)(")/gi,
    (_match, open, rawUrl, close) => {
      const rewritten = rewriteUrl(rawUrl, opts);
      return `${open}${rewritten}${close}`;
    }
  );
}

function rewriteUrl(rawUrl: string, opts: LinkRewriteOptions): string {
  // Skip mailto:, tel:, #anchors, and unsubscribe links
  if (/^(mailto:|tel:|#|{%|{{)/.test(rawUrl)) return rawUrl;

  try {
    const url = new URL(rawUrl);

    // 1. Inject UTM parameters
    url.searchParams.set('utm_source', opts.utmSource);
    url.searchParams.set('utm_medium', opts.utmMedium);
    url.searchParams.set('utm_campaign', opts.utmCampaign);
    if (opts.utmContent) url.searchParams.set('utm_content', opts.utmContent);

    const utmUrl = url.toString();

    // 2. Wrap in click proxy if configured
    if (opts.proxyBase) {
      const encoded = encodeURIComponent(utmUrl);
      return `${opts.proxyBase}?u=${encoded}`;
    }

    return utmUrl;
  } catch {
    // Malformed URL — return unchanged
    return rawUrl;
  }
}
```

## KV-Backed URL Blocklist Check

```typescript
async function isMaliciousUrl(rawUrl: string, kv: KVNamespace): Promise<boolean> {
  try {
    const url = new URL(rawUrl);
    const host = url.hostname.toLowerCase();

    // Exact domain match
    const exact = await kv.get(`blocklist:${host}`);
    if (exact) return true;

    // Apex domain match (www.evil.com → evil.com)
    const parts = host.split('.');
    if (parts.length > 2) {
      const apex = parts.slice(-2).join('.');
      const apexMatch = await kv.get(`blocklist:${apex}`);
      if (apexMatch) return true;
    }

    return false;
  } catch {
    return false; // Unparseable URL — let it through; ESP will reject broken links
  }
}

async function rewriteLinksWithCheck(
  html: string,
  opts: LinkRewriteOptions,
  kv: KVNamespace
): Promise<{ html: string; blocked: string[] }> {
  const blocked: string[] = [];
  const hrefRegex = /(<a\s[^>]*]+)(")/gi;

  const result = await replaceAsync(html, hrefRegex, async (_m, open, rawUrl, close) => {
    if (await isMaliciousUrl(rawUrl, kv)) {
      blocked.push(rawUrl);
      return `${open}#blocked${close}`; // Replace with safe anchor
    }
    return `${open}${rewriteUrl(rawUrl, opts)}${close}`;
  });

  return { html: result, blocked };
}

// replaceAsync helper — String.prototype.replace doesn't support async callbacks
async function replaceAsync(
  str: string,
  regex: RegExp,
  asyncFn: (...args: string[]) => Promise<string>
): Promise<string> {
  const promises: Promise<string>[] = [];
  str.replace(regex, (...args) => {
    promises.push(asyncFn(...args.slice(0, -2) as string[]));
    return '';
  });
  const results = await Promise.all(promises);
  return str.replace(regex, () => results.shift()!);
}
```

## Worker HTTP Handler

```typescript
interface RewriteRequest {
  html: string;
  campaign: string;
  medium?: string;
  content?: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('POST only', { status: 405 });

    const body = await request.json<RewriteRequest>();
    const opts: LinkRewriteOptions = {
      utmSource: 'email',
      utmMedium: body.medium ?? 'email',
      utmCampaign: body.campaign,
      utmContent: body.content,
      proxyBase: env.CLICK_PROXY_URL,
    };

    const { html, blocked } = await rewriteLinksWithCheck(body.html, opts, env.URL_BLOCKLIST);

    if (blocked.length > 0) {
      console.warn(`Blocked URLs in campaign ${body.campaign}:`, blocked);
      // Optionally reject the entire send
      if (env.BLOCK_ON_MALICIOUS === 'true') {
        return Response.json({ error: 'Malicious URLs detected', blocked }, { status: 422 });
      }
    }

    return Response.json({ html, blocked });
  },
} satisfies ExportedHandler<Env>;
```

## Preserving Existing UTM Parameters

```typescript
function rewriteUrlPreservingExisting(rawUrl: string, opts: LinkRewriteOptions): string {
  try {
    const url = new URL(rawUrl);

    // Only set UTM params if not already present — respects hand-crafted links
    if (!url.searchParams.has('utm_source')) {
      url.searchParams.set('utm_source', opts.utmSource);
    }
    if (!url.searchParams.has('utm_medium')) {
      url.searchParams.set('utm_medium', opts.utmMedium);
    }
    if (!url.searchParams.has('utm_campaign')) {
      url.searchParams.set('utm_campaign', opts.utmCampaign);
    }

    return url.toString();
  } catch {
    return rawUrl;
  }
}
```

## Anti-patterns

- **Rewriting `src` attributes on `<img>` tags**: Breaks images; only rewrite `<a href>`.
- **Applying UTM params to unsubscribe links**: Breaks one-click unsubscribe and violates RFC 8058;
  always skip links containing `unsubscribe` in the path or domain.
- **Double-encoding proxy URLs**: If the click proxy itself encodes the destination, don't
  `encodeURIComponent` it a second time in the template.
- **Running full HTML parse on every Worker request**: Parse HTML only for email bodies, not
  arbitrary user content — scope the regex to known template structure.
- **Storing the full blocklist in KV values**: Use keys as the signal; `kv.get()` returning
  non-null means blocked.

## Gotchas

- Regex-based link rewriting fails on single-quoted `` attributes; handle both quote
  styles or use a permissive regex: `href="'["']`.
- URL objects normalise fragment identifiers (`#`) — this changes `#CTA` to `#cta` in some
  environments; test with mixed-case anchors.
- The Workers CPU time limit (10 ms on free / 30 ms on paid for unbundled) can be hit on emails
  with hundreds of links; consider streaming or batching very large bodies.
- `URL` in Workers does not handle relative URLs — only absolute `https://` and `http://` links
  should be rewritten; protect with the try/catch guard.

## Verification

```bash
# Post test HTML body and verify UTM injection
curl -X POST https://rewrite.example.com/ \
  -H "Content-Type: application/json" \
  -d '{"html":"<a href=\"https://example.com/page\">Click</a>","campaign":"aug-2026"}'

# Expected response contains utm_source=email in the rewritten href

# Add a test blocklist entry and verify blocking
wrangler kv:key put --namespace-id=<BLOCKLIST_ID> "blocklist:evil.example.com" "1"
curl -X POST ... -d '{"html":"<a href=\"https://evil.example.com\">X</a>","campaign":"test"}'
# Expect {"html":"<a href=\"#blocked\">X</a>","blocked":["https://evil.example.com"]}
```

## Related

- `email-click-tracking.md`
- `email-click-tracking-privacy-preserving-workers.md`
- `email-open-tracking.md`
- `email-header-injection-security.md`
- `email-content-html-sanitization-workers.md`

## Sources

- UTM Parameters — Google Analytics Campaign URL Builder
- Cloudflare Workers URL API — https://developers.cloudflare.com/workers/runtime-apis/web-standards/#url
- Cloudflare KV — https://developers.cloudflare.com/kv/
- RFC 8058 — One-Click Unsubscribe
