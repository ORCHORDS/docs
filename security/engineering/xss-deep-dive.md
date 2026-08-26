# xss-deep-dive

**Issue:** XSS — patterns, prevention, sanitization
**Date:** 2026-08-09
**Status:** documented

## Symptom
A user submits a comment: `<script>alert('xss')</script>`.
The comment is stored. Another user views it. The
script runs. Their session is stolen.

## Root cause
**Untrusted input is rendered as HTML.** Use output
encoding.

**Source:** OWASP XSS.

## The "output encoding" pattern

For HTML output, encode the user input:
```ts
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

const safe = escapeHtml(userInput);
return `<p>${safe}</p>`;
```

The user input is escaped.

## The "framework auto-escape" pattern

For React, JSX auto-escapes:
```tsx
function Comment({ comment }: { comment: string }) {
  // Auto-escaped
  return <p>{comment}</p>;
}
```

The framework handles escaping.

For Angular, `{{ }}` is escaped:
```html
<p>{{ comment }}</p>
```

For Vue, `{{ }}` is escaped:
```html
<p>{{ comment }}</p>
```

The framework is your friend.

## The "dangerouslySetInnerHTML" anti-pattern

For dangerouslySetInnerHTML (use with caution):
```tsx
// ❌ DANGEROUS
return <div dangerouslySetInnerHTML={{ __html: userInput }} />;

// ✅ Safe (with DOMPurify)
import DOMPurify from 'isomorphic-dompurify';
const clean = DOMPurify.sanitize(userInput);
return <div dangerouslySetInnerHTML={{ __html: clean }} />;
```

Sanitize before rendering.

**Source:** DOMPurify:
https://github.com/cure53/DOMPurify

## The "URL validation" pattern

For URL validation, prevent javascript: URLs:
```ts
function isSafeUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return ['http:', 'https:', 'mailto:'].includes(parsed.protocol);
  } catch {
    return false;
  }
}

const safe = isSafeUrl(userInput) ? userInput : '#';
return <a href={safe}>Link</a>;
```

The URL is validated.

## The "attribute encoding" pattern

For attribute values, quote + encode:
```ts
// ❌ Bad: no quotes, allows escape
<img src={{userInput}}>

// ✅ Good: quoted
<img >

// ✅ Best: framework handles it
<img src={userInput} />
```

The attribute is safe.

## The "context-aware encoding" pattern

For context-aware encoding:
- **HTML body:** `escapeHtml`
- **Attribute:** `escapeAttr` (different for `'` vs `"`)
- **JS:** `escapeJs`
- **URL:** `escapeUrl`
- **CSS:** `escapeCss`

```ts
import { encode } from 'html-entities';

// HTML body
const safe1 = encode(userInput);

// JS string
const safe2 = JSON.stringify(userInput);
```

The encoding matches the context.

**Source:** html-entities:
https://github.com/nicktindall/html-entities

## The "CSP" pattern

For CSP, defense in depth:
```ts
response.headers.set('Content-Security-Policy', "default-src 'self'; script-src 'self'; object-src 'none'");
```

CSP blocks inline scripts.

## The "Trusted Types" pattern

For Trusted Types (modern browsers):
```ts
// 1. Set the policy
response.headers.set('Content-Security-Policy', "require-trusted-types-for 'script'");

// 2. Use Trusted Types
const policy = trustedTypes.createPolicy('myPolicy', {
  createHTML: (s: string) => DOMPurify.sanitize(s),
});

element.innerHTML = policy.createHTML(userInput);
```

The browser enforces the policy.

**Source:** W3C Trusted Types:
https://w3c.github.io/trusted-types/dist/spec/

## The "input validation" pattern

For input validation, allow-list:
```ts
function isValidUsername(s: string): boolean {
  return /^[a-zA-Z0-9_-]{3,20}$/.test(s);
}

if (!isValidUsername(userInput)) {
  throw new Error('Invalid username');
}
```

The input is validated.

## The "stored XSS" pattern

For stored XSS (the comment scenario):
1. **Validate input:** Server-side
2. **Sanitize:** Before storage (optional)
3. **Encode on output:** Always
4. **CSP:** Block inline scripts

```ts
async function createComment(input: CommentInput, env: Env): Promise<Comment> {
  // 1. Validate
  if (!isValidInput(input)) throw new Error('Invalid');

  // 2. Store
  const id = crypto.randomUUID();
  await env.DB!.prepare(
    `INSERT INTO comments (id, body) VALUES (?, ?)`
  ).bind(id, input.body).run();

  return { id, body: input.body };
}

async function renderComment(comment: Comment): Promise<string> {
  // 3. Encode on output
  return `<p>${escapeHtml(comment.body)}</p>`;
}
```

The XSS is prevented at output.

## The "reflected XSS" pattern

For reflected XSS (in URL params):
```ts
// ❌ Bad
app.get('/search', (req) => {
  const q = new URL(req.url).searchParams.get('q');
  return new Response(`<p>Results for ${q}</p>`, { headers: { 'content-type': 'text/html' } });
});

// ✅ Good
app.get('/search', (req) => {
  const q = new URL(req.url).searchParams.get('q') ?? '';
  return new Response(`<p>Results for ${escapeHtml(q)}</p>`, { headers: { 'content-type': 'text/html' } });
});
```

The output is encoded.

## The "DOM XSS" pattern

For DOM XSS (client-side):
```ts
// ❌ Bad
const q = new URL(window.location.href).searchParams.get('q');
document.getElementById('results')!.innerHTML = `Results for ${q}`;

// ✅ Good
document.getElementById('results')!.textContent = `Results for ${q}`;
```

The textContent is safe.

## The "XSS observability" pattern

For observability:
- **CSP report:** Inline script attempted
- **Log:** User input with HTML

```ts
logEvent('xss.attempt', 'warn', { userId, input: userInput.substring(0, 100) });
```

The XSS is monitored.

## The "XSS anti-pattern" anti-patterns

### 1. No output encoding
- **Issue:** Stored XSS
- **Fix:** Always encode

### 2. innerHTML with user input
- **Issue:** DOM XSS
- **Fix:** textContent

### 3. dangerouslySetInnerHTML without sanitize
- **Issue:** Stored XSS
- **Fix:** DOMPurify

### 4. javascript: URL
- **Issue:** URL XSS
- **Fix:** Validate protocol

### 5. eval with user input
- **Issue:** Code injection
- **Fix:** Never eval user input

## Verification
- **Test:** Output is encoded
- **Test:** XSS attempts are blocked
- **Live:** CSP reports
- **Audit:** Annual review

## Gotchas
- **The "no output encoding" anti-pattern.** Always
  encode.
- **The "innerHTML with user input" anti-pattern.** Use
  textContent.
- **The "eval with user input" anti-pattern.** Never.

## Related
- `xss-prevention.md`
- `xss-prevention-detail.md`
- `csp-headers-and-cf-waf.md`
- `security-headers-comprehensive.md`
- `security-headers-deep-dive.md`
- OWASP: https://owasp.org/www-community/attacks/xss/
- DOMPurify: https://github.com/cure53/DOMPurify
