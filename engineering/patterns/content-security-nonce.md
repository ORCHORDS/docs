# content-security-nonce

**Issue:** Per-request nonce for CSP — implementation
**Date:** 2026-08-09
**Status:** documented

## Symptom
You set `script-src 'self' 'unsafe-inline'`. A pen test says
"this is XSS-allowable." You remove `'unsafe-inline'`. Your
Next.js app breaks — inline scripts blocked.

## Root cause
**`'unsafe-inline'` allows all inline scripts** (a major XSS
vector). But Next.js, Google Analytics, and many other tools
use inline scripts. The way to allow inline scripts safely is
via **nonces**.

**Source:** MDN — CSP nonce:
https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP

> "If 'unsafe-inline' is in your CSP, the browser will execute
> any inline script. To allow specific inline scripts, use a
> nonce."

## How nonces work

1. Server generates a **unique nonce** per request
2. Server sets CSP header: `script-src 'self' 'nonce-abc123'`
3. Server renders HTML with `<script nonce="abc123">`
4. Browser checks: is the nonce on this script in the CSP?
5. If yes, execute. If no, block.

The nonce must be:
- **Unique per request** (otherwise it's just `'unsafe-inline'`)
- **Cryptographically random** (otherwise an attacker can
  predict it)
- **Not exposed** to the client JS (otherwise an attacker can
  read it from the page)

## Implementation

### Server side
```ts
// Pages Function middleware
export const onRequest: PagesFunction = async (context) => {
  const nonce = generateNonce();
  // Store the nonce so the React tree can access it
  context.data.nonce = nonce;

  const response = await context.next();

  // Add CSP header
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' https://*.googletagmanager.com`,
    `style-src 'self' 'nonce-${nonce}' https://fonts.googleapis.com`,
    "img-src 'self' data: blob:",
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join('; ');
  response.headers.set('Content-Security-Policy', csp);

  return response;
};

function generateNonce(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return btoa(String.fromCharCode(...bytes));
}
```

### React side (Next.js)
```tsx
// In _document.tsx
import Document, { Html, Head, Main, NextScript } from 'next/document';

class MyDocument extends Document {
  render() {
    const nonce = this.props.nonce;  // from the request
    return (
      <Html>
        <Head>
          <script nonce={nonce} src="https://www.googletagmanager.com/gtag/js?id=..." />
        </Head>
        <body>
          <Main />
          <NextScript nonce={nonce} />
        </body>
      </Html>
    );
  }
}

MyDocument.getInitialProps = async (context) => {
  const nonce = context.req.headers['x-csp-nonce'] as string;
  return { nonce };
};
```

### Other libraries
- **Next.js 13+ App Router:** automatic nonce via the
  `nonce` prop on `<Script>` (Server Components)
- **Google Analytics:** use the `nonce` attribute on the
  `<script>` tag

## Hash-based alternative

For static scripts (loaded once, cached), use a **hash** instead
of a nonce:
```ts
// Generate the hash of the script body
const scriptBody = `console.log("hello")`;
const hash = await sha256Base64(scriptBody);
// CSP: script-src 'self' 'sha256-<hash>'
```

✅ Use when: the script is static (no per-request changes)
❌ Drawback: the hash changes if the script changes (deploy
invalidates the cache)

## Common pitfalls

### "The nonce is in the HTML, so the browser can read it"
Yes, but the browser enforces the CSP. The attacker can read
the nonce in the response but cannot SET a new nonce for a
different request (the nonce is per-request).

### "I'll just use a static nonce"
This is the same as `'unsafe-inline'`. The attacker can use
the static nonce in their injected script. Always per-request.

### "I need to allow inline scripts in dev"
Add `'unsafe-inline'` ONLY in dev. In production, use nonces.

### "My third-party script doesn't support nonces"
Some legacy scripts don't. For those, use a hash:
```
script-src 'self' 'nonce-xxx' 'sha256-yyy'
```

Or migrate the script to a nonce-aware version.

## Verification
- **Test:** `test/csp-nonce.test.ts > nonce is unique per
  request, script with nonce executes, script without nonce
  blocked` — passes
- **Live:** Browser DevTools Console shows no CSP violations
- **Pen test:** CSP scan shows no `'unsafe-inline'` in
  production

## Gotchas
- **Per-request nonce = no edge caching of the HTML.** If you
  need the HTML to be cached, use a hash for static scripts +
  nonce for dynamic.
- **The nonce must be set BEFORE the response body is
  generated.** Set it in middleware, not in the page.
- **The nonce must be available to the React tree.** Pass it
  via props, context, or a request header.
- **Hashes are case-sensitive.** `'sha256-AbC==' ≠ 'sha256-abc=='`.
  Generate carefully.
- **CSP nonces are an upper limit on XSS.** They don't catch
  XSS in the nonce-tagged scripts themselves. Still need
  proper input validation.

## Related
- `csp-headers-and-cf-waf.md` (the broader CSP story)
- `secure-headers.md` (the full set of headers)
- MDN: https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP
- MDN nonce: https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP#nonce-source
