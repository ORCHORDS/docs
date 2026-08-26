# XSS Prevention with HTMLRewriter Sanitization in Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Workers that proxy or assemble HTML from CMS APIs, user-generated content feeds, or partner services risk reflecting unsanitized markup to browsers. Unlike Node.js where DOMPurify is available, Workers have no DOM; HTMLRewriter provides a streaming SAX-style API that can strip dangerous elements and attributes without buffering the full response.

## Context

HTMLRewriter was designed for response transformation but doubles as a sanitization stage. It processes the HTML byte stream at the edge without holding the full document in memory, making it viable for large pages. The critical design choice is an allowlist, not a blocklist: enumerate permitted elements and attributes explicitly, and strip everything else. This protects against both stored XSS (content from a database written before sanitization was added) and reflected XSS (user input echoed in search results or error pages). Pair the sanitization pass with a strict `Content-Security-Policy` header so a bypassed element cannot execute scripts.

## Allowlist Element and Attribute Handler

```typescript
const ALLOWED_ELEMENTS = new Set([
  'p', 'br', 'hr', 'b', 'i', 'em', 'strong', 'u', 's', 'del', 'ins',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'ul', 'ol', 'li', 'dl', 'dt', 'dd',
  'blockquote', 'pre', 'code', 'kbd', 'samp',
  'a', 'img', 'figure', 'figcaption',
  'table', 'thead', 'tbody', 'tr', 'th', 'td', 'caption',
  'div', 'span', 'section', 'article', 'header', 'footer', 'main',
]);

// Per-element allowed attributes; '*' applies to all elements
const ALLOWED_ATTRS: Record<string, Set<string>> = {
  '*':   new Set(['class', 'id', 'lang', 'dir', 'aria-label', 'aria-hidden', 'aria-describedby', 'role']),
  'a':   new Set(['href', 'title', 'target', 'rel']),
  'img': new Set(['src', 'alt', 'title', 'width', 'height', 'loading', 'decoding']),
  'th':  new Set(['colspan', 'rowspan', 'scope']),
  'td':  new Set(['colspan', 'rowspan']),
};

// Schemes that execute code or leak data when used in URL attributes
const DANGEROUS_SCHEMES = /^(?:javascript|data|vbscript|file)\s*:/i;

class AllowlistSanitizer implements ElementHandler {
  element(element: Element): void {
    const tag = element.tagName.toLowerCase();

    if (!ALLOWED_ELEMENTS.has(tag)) {
      // remove() strips the element AND its children from the output stream
      element.remove();
      return;
    }

    // Snapshot attribute names before mutating — live iterators may behave
    // unexpectedly when attributes are removed during iteration
    const names: string[] = [];
    for (const [name] of element.attributes) names.push(name);

    for (const name of names) {
      const lc = name.toLowerCase();
      const globalOk = ALLOWED_ATTRS['*']?.has(lc) ?? false;
      const tagOk    = ALLOWED_ATTRS[tag]?.has(lc) ?? false;

      if (!globalOk && !tagOk) {
        element.removeAttribute(name);
        continue;
      }

      const value = (element.getAttribute(name) ?? '').trim();

      // Block dangerous URL schemes in any attribute that accepts URLs
      if (['href', 'src', 'action', 'formaction', 'data'].includes(lc) &&
          DANGEROUS_SCHEMES.test(value)) {
        element.removeAttribute(name);
        continue;
      }

      // Enforce rel="noopener noreferrer" on _blank links
      if (tag === 'a' && lc === 'target' && value === '_blank') {
        element.setAttribute('rel', 'noopener noreferrer');
      }
    }
  }

  // Strip HTML comments — may contain IE conditional execution or serve as
  // XSS payloads in browsers that parse them differently
  comments(comment: Comment): void {
    comment.remove();
  }
}
```

## Worker Proxy with Sanitization Pass

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    const upstream = await fetch(`${env.CMS_ORIGIN}${url.pathname}${url.search}`, {
      headers: {
        Authorization: `Bearer ${env.CMS_TOKEN}`,
        Accept: 'text/html',
      },
    });

    const contentType = upstream.headers.get('Content-Type') ?? '';
    if (!contentType.includes('text/html')) {
      // Non-HTML (JSON, images, etc.) — pass through without transformation
      return upstream;
    }

    const sanitizer = new AllowlistSanitizer();

    const sanitized = new HTMLRewriter()
      .on('*', sanitizer)
      // Belt-and-suspenders: explicitly remove dangerous elements even if the
      // allowlist handler already does so via element.remove() — HTMLRewriter
      // processes handlers in registration order
      .on('script',               { element: el => el.remove() })
      .on('style',                { element: el => el.remove() })
      .on('iframe',               { element: el => el.remove() })
      .on('object',               { element: el => el.remove() })
      .on('embed',                { element: el => el.remove() })
      .on('base',                 { element: el => el.remove() })
      .on('noscript',             { element: el => el.remove() })
      .on('link[rel="import"]',   { element: el => el.remove() })
      .on('meta[http-equiv]',     { element: el => el.remove() }) // blocks http-equiv CSP override
      .transform(upstream);

    // Rebuild response with hardened security headers
    const headers = new Headers(sanitized.headers);
    headers.set('Content-Type', 'text/html; charset=utf-8');
    headers.set(
      'Content-Security-Policy',
      "default-src 'self'; script-src 'none'; style-src 'self'; img-src 'self' https:; base-uri 'none'; form-action 'self'",
    );
    headers.set('X-Content-Type-Options', 'nosniff');
    headers.set('X-Frame-Options', 'SAMEORIGIN');
    headers.delete('X-Powered-By');

    return new Response(sanitized.body, { status: sanitized.status, headers });
  },
};
```

## Sanitizing User-Generated Content Fragments

```typescript
// For sanitizing stored UGC snippets before inserting them into a page
async function sanitizeFragment(ugcHtml: string): Promise<string> {
  // Wrap in a full document so HTMLRewriter has a valid root to traverse
  const wrapped = `<!doctype html><html><body><div id="_ugc_">${ugcHtml}</div></body></html>`;

  const response = new HTMLRewriter()
    .on('*', new AllowlistSanitizer())
    .on('script', { element: el => el.remove() })
    .on('style',  { element: el => el.remove() })
    .transform(new Response(wrapped, { headers: { 'Content-Type': 'text/html' } }));

  const full = await response.text();
  // Extract just the sanitized fragment
  const match = full.match(/<div id="_ugc_">([\s\S]*?)<\/div>/i);
  return match?.[1]?.trim() ?? '';
}
```

## Anti-patterns

- Using a blocklist of known-dangerous tags (`script`, `iframe`, `svg`) — attackers routinely use lesser-known vectors like `<math href>`, `<details ontoggle>`, and `<svg><use xlink:href="data:...">` that a blocklist misses
- Sanitizing only on write (input-time) — data written before the sanitizer was deployed bypasses it; sanitize on read/output as well
- Allowing the `style` attribute — CSS `background-image: url(...)` and `expression()` (legacy IE) can exfiltrate data or execute code regardless of `script-src: none`

## Gotchas

- `element.attributes` is a live iterable in HTMLRewriter: removing an attribute while iterating over it may skip the next attribute in the list — always snapshot attribute names into an array first, as shown above
- Calling `.text()` on a `HTMLRewriter`-transformed response buffers the entire body into memory; for large CMS pages, pipe `sanitized.body` directly to the client via streaming instead
- HTMLRewriter processes `<noscript>` contents as raw text in some runtime versions, not as HTML children — explicitly register `.on('noscript', ...)` to remove the element entirely rather than relying on the wildcard handler to strip child elements inside it

## Verification

```bash
# Script tags must be stripped
curl -s https://api.example.com/cms/article | grep -c '<script'   # expect 0

# Event handler attributes must be stripped
curl -s https://api.example.com/cms/article | grep -cP 'on\w+\s*=' # expect 0

# javascript: href must be removed
curl -s https://api.example.com/cms/article | grep -c 'javascript:' # expect 0

# CSP header must be present and block scripts
curl -sI https://api.example.com/cms/article | grep 'Content-Security-Policy'
```

## Related

- `security/xss-deep-dive.md`
- `security/content-security-policy-workers-nonce.md`
- `security/http-parameter-pollution-workers.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html
- https://portswigger.net/web-security/cross-site-scripting
