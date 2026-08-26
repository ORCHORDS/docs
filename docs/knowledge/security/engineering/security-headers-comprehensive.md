# security-headers-comprehensive

**Issue:** All the security headers you need, with examples
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your app has no security headers. A user opens the dev
tools. They see no CSP, no HSTS, no X-Frame-Options. A
pentester finds XSS, clickjacking, and downgrade attacks.
You scramble to add them all at once.

## Root cause
**Security headers are an afterthought.** They should be
in the response from day 1.

**Source:** Mozilla Observatory:
https://observatory.mozilla.org/

> "Security headers are HTTP response headers that, when
> set, can improve the security of your application."

## The 10 essential headers

### 1. Strict-Transport-Security (HSTS)
Forces HTTPS:
```
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
```

- `max-age=31536000` — 1 year
- `includeSubDomains` — apply to subdomains
- `preload` — submit to browser preload list

### 2. Content-Security-Policy (CSP)
Prevents XSS by controlling what can be loaded:
```
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' https://api.example.com; font-src 'self' https://fonts.gstatic.com; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
```

Breakdown:
- `default-src 'self'` — by default, only same-origin
- `script-src 'self'` — only same-origin scripts
- `style-src 'self' 'unsafe-inline'` — same-origin + inline
  (for some CSS-in-JS)
- `img-src 'self' data: https:` — same-origin + data URLs +
  any HTTPS
- `connect-src 'self' https://api.example.com` — only
  same-origin + the API
- `object-src 'none'` — no `<object>`, `<embed>`
- `base-uri 'self'` — no `<base>` injection
- `frame-ancestors 'none'` — no framing (clickjacking defense)

### 3. X-Frame-Options
Prevents clickjacking (legacy; CSP frame-ancestors is
preferred):
```
X-Frame-Options: DENY
```

Options:
- `DENY` — no framing
- `SAMEORIGIN` — only same-origin
- `ALLOW-FROM https://example.com` — specific origin
  (deprecated)

### 4. X-Content-Type-Options
Prevents MIME sniffing:
```
X-Content-Type-Options: nosniff
```

The browser must respect the Content-Type.

### 5. Referrer-Policy
Controls the Referer header:
```
Referrer-Policy: strict-origin-when-cross-origin
```

Options:
- `no-referrer` — never send
- `same-origin` — only same-origin
- `strict-origin` — only the origin (no path)
- `strict-origin-when-cross-origin` — full URL for same-
  origin, just origin for cross-origin
- `no-referrer-when-downgrade` (default) — send unless
  HTTPS → HTTP

### 6. Permissions-Policy
Controls browser features:
```
Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=(), magnetometer=(), gyroscope=(), accelerometer=()
```

The `()` means "no origins allowed" (deny all).

### 7. Cross-Origin-Opener-Policy (COOP)
Isolates the browsing context:
```
Cross-Origin-Opener-Policy: same-origin
```

Prevents side-channel attacks like Spectre.

### 8. Cross-Origin-Embedder-Policy (COEP)
Requires explicit opt-in for resources:
```
Cross-Origin-Embedder-Policy: require-corp
```

Prevents loading cross-origin resources without explicit
permission.

### 9. Cross-Origin-Resource-Policy (CORP)
Controls who can embed your resources:
```
Cross-Origin-Resource-Policy: same-origin
```

Options:
- `same-origin` — only your origin
- `same-site` — your site
- `cross-origin` — anyone

### 10. Cache-Control
For sensitive responses, prevent caching:
```
Cache-Control: no-store
```

For static assets, allow caching:
```
Cache-Control: public, max-age=31536000, immutable
```

## The "secure headers" middleware

In a Worker:
```ts
export function withSecurityHeaders(response: Response): Response {
  const newResponse = new Response(response.body, response);

  newResponse.headers.set('Strict-Transport-Security', 'max-age=31536000; includeSubDomains; preload');
  newResponse.headers.set('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' https://api.example.com; font-src 'self' https://fonts.gstatic.com; object-src 'none'; base-uri 'self'; frame-ancestors 'none'");
  newResponse.headers.set('X-Frame-Options', 'DENY');
  newResponse.headers.set('X-Content-Type-Options', 'nosniff');
  newResponse.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
  newResponse.headers.set('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
  newResponse.headers.set('Cross-Origin-Opener-Policy', 'same-origin');
  newResponse.headers.set('Cross-Origin-Resource-Policy', 'same-origin');

  return newResponse;
}

// In the handler
return withSecurityHeaders(originalResponse);
```

## The "CSP report-only" pattern

Test CSP without breaking:
```
Content-Security-Policy-Report-Only: default-src 'self'; report-uri /csp-report
```

The browser sends a report for violations but doesn't
enforce. Use this to test your CSP.

## The "per-route" pattern

Some routes need different headers:
```ts
function getSecurityHeaders(pathname: string): Record<string, string> {
  if (pathname.startsWith('/api/')) {
    // API: no CSP needed (JSON)
    return {
      'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
      'X-Content-Type-Options': 'nosniff',
      'Cache-Control': 'no-store',
    };
  }
  if (pathname.startsWith('/embed/')) {
    // Embed: allow framing
    return {
      'X-Frame-Options': 'SAMEORIGIN',
      'Content-Security-Policy': "frame-ancestors 'self' https://trusted-partner.com",
    };
  }
  // Default: strict
  return ALL_SECURITY_HEADERS;
}
```

## The "report-uri" pattern

For CSP violations, collect reports:
```ts
// On the server
export async function handleCSPReport(request: Request, env: Env): Promise<Response> {
  const report = await request.json();
  // Log to your monitoring
  logEvent('csp.violation', 'warn', { report });
  return new Response(null, { status: 204 });
}
```

The browser sends the report when CSP is violated.

## The "Helmet" pattern

For Express-style apps, use Helmet:
```ts
import helmet from 'helmet';
app.use(helmet());
```

Helmet sets all the security headers with sensible defaults.

For Workers, write a similar middleware.

## The "test the headers" pattern

For every page, test the headers:
```ts
test('homepage has all security headers', async () => {
  const res = await fetch('https://staging.example.com/');
  expect(res.headers.get('Strict-Transport-Security')).toContain('max-age=');
  expect(res.headers.get('Content-Security-Policy')).toContain("default-src 'self'");
  expect(res.headers.get('X-Frame-Options')).toBe('DENY');
  // ... etc
});
```

## The "scan for missing headers" pattern

Use Mozilla Observatory to scan:
```bash
# Visit https://observatory.mozilla.org/
# Enter your domain
# Get a score + recommendations
```

The scan checks all the headers + TLS + more.

## The "header" gotchas

### 1. CSP `unsafe-inline` for scripts
```html
<!-- ❌ Allows inline scripts (XSS risk) -->
<script>alert('XSS')</script>
```

Use nonces or hashes for inline scripts:
```html
<script nonce="abc123">alert('hello')</script>
```

```ts
const nonce = crypto.randomUUID();
response.headers.set('Content-Security-Policy', `script-src 'self' 'nonce-${nonce}'`);
response.headers.set('nonce', nonce);
```

### 2. CSP `unsafe-eval` for eval
```ts
// ❌ Allows eval (XSS risk)
eval('alert(1)');
```

Avoid eval. CSP `unsafe-eval` should be rare.

### 3. CORS + CSP
CORS and CSP are different:
- **CORS:** server says "X origin can access my API"
- **CSP:** browser says "this page can only load X origins"

Both are needed for security.

### 4. The "HSTS preload" gotcha
Once you submit to the HSTS preload list, you can't easily
remove. The site is HTTPS-only for all browsers, forever.
Test HSTS thoroughly first.

## Verification
- **Test:** Every endpoint has the expected headers
- **Live:** Mozilla Observatory score = A+
- **Audit:** Annual review of security headers

## Gotchas
- **The "CSP blocks your own code" gotcha.** A strict CSP
  may block legitimate code. Test in report-only first.
- **The "HSTS is permanent" gotcha.** Preload is hard to
  undo. Test with a short max-age first.
- **The "X-Frame-Options is legacy" gotcha.** Use CSP
  frame-ancestors; X-Frame-Options is for old browsers.
- **The "Referrer-Policy leaks" gotcha.** A loose policy
  can leak sensitive URLs. Use `strict-origin-when-cross-
  origin` by default.
- **The "headers don't help if HTTPS is broken" gotcha.**
  HSTS requires HTTPS to be working. Set up HTTPS first.

## Related
- `csp-headers-and-cf-waf.md`
- `xss-prevention.md`
- `csrf-modern-defenses.md`
- `clickjacking-defense.md`
- `secure-defaults.md`
- Mozilla Observatory: https://observatory.mozilla.org/
- CSP reference: https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP
- Security headers: https://securityheaders.com/
