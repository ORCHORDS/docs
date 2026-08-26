# security-headers-deep-dive

**Issue:** HTTP security headers — CSP, HSTS, etc.
**Date:** 2026-08-09
**Status:** documented

## Symptom
You scan your site. The scanner says "missing
Content-Security-Policy" and "missing X-Frame-Options."
You add them. The scan is cleaner. But you don't know
if you have them right.

## Root cause
**Security headers are easy to add but easy to get
wrong.** Use the OWASP cheatsheet.

**Source:** OWASP — Secure Headers Project:
https://owasp.org/www-project-secure-headers/

## Headers cheat sheet

### Content-Security-Policy (CSP)
- **What:** Restrict what the browser can execute
- **Default:** `default-src 'self'`
- **Strict:** `default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:;`

```ts
response.headers.set('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self'; connect-src 'self' https://api.example.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'");
```

The CSP is set.

**Source:** MDN CSP:
https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP

### Strict-Transport-Security (HSTS)
- **What:** Force HTTPS
- **Default:** `max-age=31536000; includeSubDomains`

```ts
response.headers.set('Strict-Transport-Security', 'max-age=31536000; includeSubDomains; preload');
```

The HSTS is set.

**Source:** MDN HSTS:
https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security

### X-Frame-Options
- **What:** Prevent clickjacking
- **Default:** `DENY`

```ts
response.headers.set('X-Frame-Options', 'DENY');
```

**Source:** MDN X-Frame-Options:
https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Frame-Options

### X-Content-Type-Options
- **What:** Disable MIME sniffing
- **Default:** `nosniff`

```ts
response.headers.set('X-Content-Type-Options', 'nosniff');
```

**Source:** MDN:
https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Content-Type-Options

### Referrer-Policy
- **What:** Control the Referer header
- **Default:** `strict-origin-when-cross-origin`

```ts
response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
```

**Source:** MDN:
https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Referrer-Policy

### Permissions-Policy
- **What:** Disable features
- **Default:** `camera=(), microphone=(), geolocation=()`

```ts
response.headers.set('Permissions-Policy', 'camera=(), microphone=(), geolocation=(), payment=()');
```

**Source:** MDN:
https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Permissions-Policy

### Cross-Origin-Embedder-Policy (COEP)
- **What:** Require CORS for embed
- **Default:** `require-corp`

```ts
response.headers.set('Cross-Origin-Embedder-Policy', 'require-corp');
```

### Cross-Origin-Opener-Policy (COOP)
- **What:** Isolate the browsing context
- **Default:** `same-origin`

```ts
response.headers.set('Cross-Origin-Opener-Policy', 'same-origin');
```

### Cross-Origin-Resource-Policy (CORP)
- **What:** Block no-cors cross-origin
- **Default:** `same-origin`

```ts
response.headers.set('Cross-Origin-Resource-Policy', 'same-origin');
```

**Source:** MDN CORP:
https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cross-Origin-Resource-Policy

## The "CF Worker headers" pattern

For CF Workers, the headers are set in the response:
```ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const response = await fetch(request);
    const newResponse = new Response(response.body, response);

    // Security headers
    newResponse.headers.set('Content-Security-Policy', "default-src 'self'; ...");
    newResponse.headers.set('Strict-Transport-Security', 'max-age=31536000; includeSubDomains; preload');
    newResponse.headers.set('X-Frame-Options', 'DENY');
    newResponse.headers.set('X-Content-Type-Options', 'nosniff');
    newResponse.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
    newResponse.headers.set('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');

    return newResponse;
  },
};
```

The headers are set on every response.

## The "CSP nonce" pattern

For a strict CSP with inline scripts, use a nonce:
```ts
async function handleRequest(request: Request, env: Env): Promise<Response> {
  const nonce = btoa(crypto.randomUUID());

  const csp = `default-src 'self'; script-src 'self' 'nonce-${nonce}' 'strict-dynamic'; style-src 'self' 'nonce-${nonce}'`;

  const html = await renderHTML({ nonce });

  return new Response(html, {
    headers: {
      'Content-Security-Policy': csp,
      'Content-Type': 'text/html',
    },
  });
}
```

The nonce is per-request.

**Source:** CSP nonce:
https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP

## The "CSP report-only" pattern

For testing CSP, use report-only:
```ts
response.headers.set('Content-Security-Policy-Report-Only', csp);
```

The CSP doesn't block, just reports.

## The "headers check" pattern

For verification, use securityheaders.com:
```bash
curl -I https://example.com
# Check for missing headers
```

The headers are checked.

## The "headers anti-pattern" anti-patterns

### 1. No CSP
- **Issue:** XSS attacks succeed
- **Fix:** Set CSP

### 2. Wildcard CSP
- **Issue:** CSP is ineffective
- **Fix:** Restrictive CSP

### 3. No HSTS
- **Issue:** SSL stripping
- **Fix:** HSTS with preload

### 4. X-Frame-Options: ALLOW
- **Issue:** Clickjacking
- **Fix:** X-Frame-Options: DENY

### 5. Permissions-Policy: *
- **Issue:** All features enabled
- **Fix:** Disable unused

## Verification
- **Test:** Headers are set
- **Test:** CSP is enforced
- **Live:** securityheaders.com scan
- **Audit:** Annual review

## Gotchas
- **The "wildcard CSP" anti-pattern.** Be restrictive.
- **The "no HSTS" anti-pattern.** Add HSTS preload.
- **The "no CSP" anti-pattern.** Add CSP.

## Related
- `security-headers-comprehensive.md`
- `csp-headers-and-cf-waf.md`
- `clickjacking-defense.md`
- `content-security-nonce.md`
- OWASP: https://owasp.org/www-project-secure-headers/
- MDN: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers
