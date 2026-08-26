# csrf-deep-dive

**Issue:** CSRF — protection patterns, modern defenses
**Date:** 2026-08-09
**Status:** documented

## Symptom
A user is logged in. They visit a malicious site.
The site sends a request to your app. The browser
includes the session cookie. The request is processed.
The user's account is changed.

## Root cause
**Cookies are sent automatically.** CSRF exploits this.

**Source:** OWASP CSRF.

## The "SameSite cookie" pattern

For SameSite cookies (the strongest CSRF defense):
```ts
response.headers.set('Set-Cookie', 'session=abc123; Path=/; Secure; HttpOnly; SameSite=Lax');
```

**Source:** MDN SameSite:
https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie/SameSite

- **Strict:** Cookie only sent for same-site requests
- **Lax:** Cookie sent for top-level navigations
- **None:** Cookie always sent (requires Secure)

For most apps, **Lax** is the right balance.

## The "double-submit cookie" pattern

For double-submit, send a token in cookie + header:
```ts
// 1. Set the CSRF cookie
response.headers.set('Set-Cookie', `csrf=${token}; Path=/; Secure; SameSite=Lax`);

// 2. Client sends the token in the header
// fetch('/api/users', {
//   method: 'POST',
//   headers: { 'X-CSRF-Token': token },
//   body: JSON.stringify(data),
// });

// 3. Server compares
const cookieToken = request.headers.get('cookie')?.match(/csrf=([^;]+)/)?.[1];
const headerToken = request.headers.get('x-csrf-token');
if (cookieToken !== headerToken) {
  return new Response('CSRF token mismatch', { status: 403 });
}
```

The attacker can't read the cookie; the header isn't
sent automatically.

## The "synchronizer token" pattern

For synchronizer, a server-side token:
```ts
// 1. Generate the token
const session = await getSession(request);
if (!session.csrfToken) {
  session.csrfToken = crypto.randomUUID();
  await saveSession(session, response);
}

// 2. Form includes the token
// <input type="hidden" name="_csrf" value="{{token}}">

// 3. Server verifies
const formToken = formData.get('_csrf');
if (formToken !== session.csrfToken) {
  return new Response('CSRF token mismatch', { status: 403 });
}
```

The server holds the token.

## The "Origin header check" pattern

For Origin header check (simpler):
```ts
const origin = request.headers.get('origin') ?? request.headers.get('referer');
if (!origin || !new URL(origin).hostname.endsWith('example.com')) {
  return new Response('Invalid origin', { status: 403 });
}
```

The Origin is verified.

## The "SameSite Strict" pattern

For SameSite Strict (maximum protection):
```ts
response.headers.set('Set-Cookie', 'session=abc123; Path=/; Secure; HttpOnly; SameSite=Strict');
```

**Caveat:** Breaks cross-site flows (e.g. redirect from
email link).

## The "CSRF + form" pattern

For forms:
```html
<form method="POST" action="/api/users">
  <input type="hidden" name="_csrf" value="{{csrfToken}}">
  <input name="email" type="email">
  <button type="submit">Submit</button>
</form>
```

The form includes the token.

## The "CSRF + fetch" pattern

For fetch:
```ts
const csrfToken = getCookie('csrf');
const response = await fetch('/api/users', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRF-Token': csrfToken,
  },
  credentials: 'include',
  body: JSON.stringify(data),
});
```

The fetch includes the token.

## The "CSRF + GET" pattern

For GET requests:
- **Safe:** GET should not change state
- **No CSRF needed:** For pure reads

```ts
app.get('/api/users', handler);  // No CSRF needed
app.post('/api/users', withCsrf(handler));  // CSRF needed
```

Only state-changing methods need CSRF.

## The "modern stack" pattern

For modern apps (SPAs):
- **SameSite=Strict** cookie for auth
- **CSRF token** for state-changing operations
- **CORS** for cross-origin

```ts
response.headers.set('Set-Cookie', 'session=abc; SameSite=Strict; Secure; HttpOnly');
response.headers.set('Access-Control-Allow-Origin', 'https://app.example.com');
response.headers.set('Access-Control-Allow-Credentials', 'true');
```

The defense is layered.

**Source:** MDN CORS:
https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS

## The "CSRF token rotation" pattern

For token rotation:
```ts
async function rotateCsrfToken(request: Request, env: Env): Promise<string> {
  const newToken = crypto.randomUUID();
  const session = await getSession(request);
  session.csrfToken = newToken;
  await saveSession(session, env);
  return newToken;
}
```

The token is rotated.

## The "CSRF observability" pattern

For observability:
- **Token mismatch:** Log + alert
- **Missing token:** Log + alert
- **Origin mismatch:** Log + alert

```ts
logEvent('csrf.failed', 'warn', {
  userId: ctx.user?.id,
  origin: request.headers.get('origin'),
  path: new URL(request.url).pathname,
});
```

The CSRF failures are monitored.

## The "CSRF anti-pattern" anti-patterns

### 1. No CSRF protection
- **Issue:** CSRF attacks succeed
- **Fix:** SameSite + token

### 2. Cookie without SameSite
- **Issue:** Cookie is sent cross-site
- **Fix:** SameSite=Lax

### 3. Token in URL
- **Issue:** Token leaks via referer
- **Fix:** Token in header or body

### 4. Token in localStorage
- **Issue:** Token is exposed to JS
- **Fix:** HttpOnly cookie

### 5. GET for state change
- **Issue:** CSRF can be triggered
- **Fix:** Use POST

## Verification
- **Test:** CSRF is enforced
- **Test:** Token is rotated
- **Test:** Origin is checked
- **Live:** CSRF failures are monitored
- **Audit:** Annual review

## Gotchas
- **The "no CSRF" anti-pattern.** Add protection.
- **The "cookie without SameSite" anti-pattern.**
  SameSite=Lax.
- **The "GET for state change" anti-pattern.** Use POST.

## Related
- `csrf-protection-double-submit.md`
- `csrf-modern-defenses.md`
- `csrf-modern-defenses-detail.md`
- `csrf-vs-cors-vs-samesite.md`
- `clickjacking-defense.md`
- OWASP: https://owasp.org/www-community/attacks/csrf
- MDN SameSite: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie/SameSite
