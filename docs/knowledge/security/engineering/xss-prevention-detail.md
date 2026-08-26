# xss-prevention-detail

**Issue:** XSS — types, prevention, examples
**Date:** 2026-08-09
**Status:** documented

## Symptom
A user posts a comment: "Hello!" The comment is rendered
as `<p>Hello!</p>`. The user posts a comment:
`<script>alert('XSS')</script>`. The comment is rendered
as `<p><script>alert('XSS')</script></p>`. The script
runs. The user's session is stolen.

## Root cause
**User input is rendered as HTML without escaping.** The
attacker injects scripts.

**Source:** OWASP — XSS:
https://owasp.org/www-community/attacks/xss/

> "Cross-Site Scripting (XSS) attacks are a type of
> injection in which malicious scripts are injected into
> otherwise benign and trusted websites."

## The 3 types of XSS

### 1. Reflected XSS
- **What:** The user input is reflected in the response
- **Example:** `/search?q=<script>...</script>` renders the
  input in the response

### 2. Stored XSS
- **What:** The user input is stored in the DB and rendered
  to other users
- **Example:** A comment that contains `<script>` is
  rendered to everyone

### 3. DOM-based XSS
- **What:** The user input is in the URL fragment and used
  in the client-side JS
- **Example:** `#<img src=x onerror=alert(1)>` triggers
  JavaScript

## The "escape" rule

The ONLY safe way to render user input in HTML is to
escape it:
```ts
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// Usage
const html = `<p>${escapeHtml(userInput)}</p>`;
```

The input is rendered as text, not HTML.

## The "React auto-escape" pattern

React auto-escapes by default:
```tsx
// ✅ Safe: React escapes
<p>{userInput}</p>

// ❌ Vulnerable: dangerouslySetInnerHTML
<p dangerouslySetInnerHTML={{ __html: userInput }} />
```

Use `dangerouslySetInnerHTML` only with sanitized input.

## The "sanitize" pattern

For rich text, sanitize the input:
```ts
import DOMPurify from 'isomorphic-dompurify';

const sanitized = DOMPurify.sanitize(userInput, {
  ALLOWED_TAGS: ['p', 'b', 'i', 'em', 'strong', 'a', 'ul', 'ol', 'li'],
  ALLOWED_ATTR: ['href'],
});
```

The input is sanitized; dangerous tags are removed.

## The "Markdown" pattern

For user input that's Markdown, parse + sanitize:
```ts
import { marked } from 'marked';
import DOMPurify from 'isomorphic-dompurify';

const html = DOMPurify.sanitize(marked.parse(userInput));
```

Markdown is converted to HTML; the HTML is sanitized.

## The "URL" pattern

For URL inputs, validate the scheme:
```ts
function isSafeUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return ['http:', 'https:'].includes(parsed.protocol);
  } catch {
    return false;
  }
}

// Usage
if (!isSafeUrl(userUrl)) {
  throw new Error('Invalid URL');
}
```

A `javascript:` URL can execute code; reject it.

## The "Content-Security-Policy" pattern

For defense in depth, use CSP:
```
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'
```

The CSP blocks inline scripts, eval, and untrusted sources.

## The "Trusted Types" pattern

For modern browsers, use Trusted Types:
```ts
// In the policy
const policy = trustedTypes.createPolicy('my-policy', {
  createHTML: (input) => DOMPurify.sanitize(input),
});

// In the code
const html = policy.createHTML(userInput);
```

The browser enforces that only sanitized HTML is rendered.

## The "context" awareness pattern

Escape differently based on context:
- **HTML body:** escape `<`, `>`, `&`, `"`, `'`
- **HTML attribute:** escape `"` (or `'` if quoted with `'`)
- **JavaScript string:** escape `\`, `'`, `"`, `<`, `>`, `&`
- **URL:** validate scheme + escape
- **CSS:** escape `\`, `"`, `'`, `<`, `>`, `&`

Most libraries (React) handle this automatically.

## The "stored XSS" pattern

For user content that's stored and rendered:
```ts
// 1. On save: sanitize
const sanitized = DOMPurify.sanitize(userInput, {
  ALLOWED_TAGS: ['p', 'b', 'i', 'em', 'strong', 'a'],
  ALLOWED_ATTR: ['href'],
});

// 2. Store the sanitized version
await env.DB!.prepare(
  `INSERT INTO comments (user_id, body) VALUES (?, ?)`
).bind(userId, sanitized).run();

// 3. On read: render the sanitized version
const comment = await getComment(commentId, env);
return new Response(`<p>${comment.body}</p>`);  // Already sanitized
```

The input is sanitized on save; rendering is safe.

## The "DOM XSS" pattern

For client-side, use safe APIs:
```ts
// ❌ Vulnerable
element.innerHTML = userInput;

// ✅ Safe
element.textContent = userInput;
```

`textContent` is safe; `innerHTML` is not.

## The "URL fragment" pattern

For URL fragments, don't use them for sensitive data:
```ts
// ❌ Vulnerable
const token = location.hash.slice(1);  // XSS risk if attacker controls

// ✅ Use postMessage or server-side exchange
const response = await fetch('/api/auth/exchange', { method: 'POST', body: JSON.stringify({ token }) });
```

Use server-side exchange; not the URL.

## The "cookie" pattern

For session cookies, use `HttpOnly`:
```
Set-Cookie: session=...; HttpOnly; Secure; SameSite=Lax
```

`HttpOnly` blocks JavaScript from accessing the cookie.
XSS can't steal the session.

## The "audit" pattern

For audit, log suspicious input:
```ts
const dangerousPattern = /<script|javascript:|onerror=|onload=/i;
if (dangerousPattern.test(userInput)) {
  logEvent('xss.attempt', 'warn', { userId, input: userInput.slice(0, 100) });
}
```

The log shows XSS attempts.

## The "XSS" anti-patterns

### 1. innerHTML
```ts
// ❌ Always vulnerable
element.innerHTML = userInput;
```

### 2. eval
```ts
// ❌ Executes arbitrary code
eval(userInput);
```

### 3. setTimeout with string
```ts
// ❌ Same as eval
setTimeout(`alert('${userInput}')`, 1000);
```

### 4. document.write
```ts
// ❌ Vulnerable
document.write(userInput);
```

### 5. Direct attribute setting
```ts
// ❌ Vulnerable
element.setAttribute('onclick', userInput);
```

## Verification
- **Test:** Every user input is escaped or sanitized
- **Test:** CSP is set
- **Pen test:** XSS fuzzing
- **Audit:** Quarterly review of input handling

## Gotchas
- **The "React is safe" gotcha.** React is safe BY DEFAULT.
  `dangerouslySetInnerHTML` is the escape hatch.
- **The "no script tags" anti-pattern.** Many XSS vectors
  don't use `<script>`: event handlers, data URIs, etc.
- **The "URL validation is enough" gotcha.** A `javascript:`
  URL is a vector. Always validate the scheme.
- **The "markdown is safe" gotcha.** Markdown can include
  raw HTML; sanitize.
- **The "CSP is enough" gotcha.** CSP is defense in
  depth. Don't rely on it alone.

## Related
- `xss-prevention.md`
- `sql-injection-prevention-detail.md`
- `csp-headers-and-cf-waf.md`
- `security-headers-comprehensive.md`
- `secure-defaults.md`
- OWASP: https://owasp.org/www-community/attacks/xss/
- DOMPurify: https://github.com/cure53/DOMPurify
- Trusted Types: https://developer.mozilla.org/en-US/docs/Web/API/Trusted_Types_API
