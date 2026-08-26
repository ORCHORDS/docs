# xss-prevention

**Issue:** XSS — types, prevention, modern defenses
**Date:** 2026-08-09
**Status:** documented

## Symptom
A user submits a post with content `<img src=x onerror=alert(1)>`.
The post is rendered in other users' browsers. The script
executes. The attacker has XSS.

## Root cause
**Cross-Site Scripting (XSS)** is when user-controlled input
is rendered in another user's browser without sanitization.
The attacker's script runs in the victim's session, with the
victim's cookies.

**Source:** OWASP — XSS:
https://owasp.org/www-community/attacks/xss/

## The 3 types of XSS

### 1. Reflected XSS
The attacker crafts a URL with the script in the query
string. The victim clicks the link. The server reflects the
input in the response.

```
https://example.com/search?q=<script>alert(1)</script>
```

The server renders the search query in the page without
sanitizing. The script executes.

### 2. Stored XSS
The attacker submits user content with a script. The server
stores it. Other users view the content. The script executes.

A forum post, a comment, a profile bio — anywhere user content
is rendered.

### 3. DOM XSS
The attacker manipulates the DOM directly (via URL hash,
postMessage, etc.). The server isn't involved.

```
https://example.com/welcome#<img src=x onerror=alert(1)>
```

The client-side JS reads the hash and inserts it into the DOM
without sanitizing.

## Fix

### 1. Use a framework that escapes by default

**React** (and most modern frameworks) auto-escapes string
children:
```tsx
// ✅ Safe: React escapes the content
function Post({ post }) {
  return <p>{post.body}</p>;
}
```

The `<p>` renders the text content (not HTML). The script tag
is rendered as text, not as HTML.

### 2. Don't use `dangerouslySetInnerHTML` / `v-html` / `bypassSecurityTrustHtml`

```tsx
// ❌ Bad: bypasses React's escaping
function Post({ post }) {
  return <p dangerouslySetInnerHTML={{ __html: post.body }} />;
}
```

If you must render HTML (e.g. for a Markdown renderer), use a
sanitizer:
```tsx
import DOMPurify from 'dompurify';

function Post({ post }) {
  const sanitized = DOMPurify.sanitize(post.body, {
    ALLOWED_TAGS: ['b', 'i', 'em', 'strong', 'a', 'p', 'br', 'ul', 'ol', 'li'],
    ALLOWED_ATTR: ['href', 'title'],
  });
  return <div dangerouslySetInnerHTML={{ __html: sanitized }} />;
}
```

### 3. CSP (defense in depth)

A strict CSP blocks inline scripts, even if XSS occurs:
```
Content-Security-Policy: script-src 'self' 'nonce-xxx'; object-src 'none'
```

See `content-security-nonce.md` and `csp-headers-and-cf-waf.md`.

### 4. Sanitize URLs

```ts
function safeUrl(url: string): string | null {
  try {
    const parsed = new URL(url, 'https://example.com');
    if (!['https:', 'http:', 'mailto:'].includes(parsed.protocol)) {
      return null;  // Block javascript:, data:, etc.
    }
    return parsed.toString();
  } catch {
    return null;
  }
}
```

A user-provided link with `javascript:alert(1)` would execute.
The sanitizer blocks it.

### 5. Set cookies with HttpOnly + Secure + SameSite

```ts
headers.set('Set-Cookie', 'mc_sid=xxx; HttpOnly; Secure; SameSite=Lax');
```

`HttpOnly` prevents JS from reading the cookie (XSS can't
steal the session).

### 6. Use Trusted Types

```http
Content-Security-Policy: require-trusted-types-for 'script'
```

The browser enforces that all `innerHTML` setters use
sanitized values from a trusted source. Modern browsers only.

## React-specific gotchas

- **`href="javascript:..."` in `<a>` tags**: React doesn't
  sanitize the `href` attribute. Use a URL sanitizer.
- **Server-side React rendering** with `dangerouslySetInnerHTML`
  is just as dangerous as client-side. Same defense applies.
- **Markdown renderers** often produce HTML. Sanitize the
  output.

## Verification
- **Test:** `test/xss.test.ts > classic <script>alert(1)</script>
  payload rendered as text, not executed` — passes
- **Live:** CSP report-uri shows no blocked XSS attempts (or
  blocked attempts are expected/handled)
- **Pen test:** Annual third-party XSS scan

## Gotchas
- **A sanitizer is not a parser.** DOMPurify is one of the
  best, but it's not 100% perfect. New bypasses are found
  regularly.
- **The HTML attribute context is different from the element
  context.** A sanitizer must know the context to sanitize
  correctly. Most sanitizers are context-aware, but verify.
- **URLs in CSS** (`background-image: url(...)`) can also
  execute. Sanitize CSS too if you allow user-provided CSS.
- **The `srcdoc` attribute on `<iframe>`** is a full HTML
  document. It's a major XSS vector. Don't allow it.
- **JSON in HTML** is safe IF you use `<script type="application/json">`
  (not `<script>...</script>`). React handles this correctly.

## Related
- `content-security-nonce.md`
- `csrf-protection-double-submit.md` (companion for cookie auth)
- `secure-headers.md`
- OWASP: https://owasp.org/www-community/attacks/xss/
- DOMPurify: https://github.com/cure53/DOMPurify
- Trusted Types: https://w3c.github.io/trusted-types/dist/spec/
