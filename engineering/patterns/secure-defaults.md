# secure-defaults

**Issue:** Security defaults that don't need explicit configuration
**Date:** 2026-08-09
**Status:** documented

## Symptom
A new developer adds a new endpoint. They forget to add
auth. The endpoint is public. A user finds it. The data
is leaked.

## Root cause
**Security should be the default, not the opt-in.** A
developer should have to actively disable security, not
actively enable it.

**Source:** OWASP — Secure Defaults:
https://cheatsheetseries.owasp.org/cheatsheets/

> "Secure defaults are settings that are safe by default.
> ... Users don't need to know about the security feature
> to be protected."

## The 10 secure defaults

### 1. Auth on by default
- **Default:** Every endpoint requires auth
- **Opt-out:** Only for explicit "public" endpoints

```ts
// ❌ Bad: auth is opt-in
export async function handler(request: Request, env: Env) {
  // No auth check
  return handleUser(request, env);
}

// ✅ Good: auth is opt-out
export async function handler(request: Request, env: Env) {
  const user = await authenticate(request, env);
  if (!user) return new Response('Unauthorized', { status: 401 });
  return handleUser(request, env, user);
}

// For public endpoints, use a different signature
export async function publicHandler(request: Request, env: Env) {
  return handlePublic(request, env);
}
```

### 2. HTTPS only
- **Default:** HTTP redirects to HTTPS
- **Opt-out:** Never

```ts
export async function handleRequest(request: Request, env: Env): Promise<Response> {
  if (new URL(request.url).protocol === 'http:') {
    return Response.redirect(request.url.replace('http:', 'https:'), 301);
  }
  // ... rest of the handler
}
```

For CF, this is automatic (CF forces HTTPS).

### 3. Secure cookies
- **Default:** `Secure`, `HttpOnly`, `SameSite=Lax`
- **Opt-out:** Never

```ts
const cookie = `session=${sessionId}; Secure; HttpOnly; SameSite=Lax; Path=/; Max-Age=86400`;
```

### 4. CSP headers
- **Default:** Strict CSP
- **Opt-out:** For specific endpoints that need inline scripts

```ts
const csp = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'";
response.headers.set('Content-Security-Policy', csp);
```

### 5. HSTS
- **Default:** `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
- **Opt-out:** Never

### 6. No secrets in code
- **Default:** All secrets from env / secret manager
- **Opt-out:** Test fixtures only

Use a linter to catch secrets in code (gitleaks).

### 7. Password hashing
- **Default:** Argon2id with strong parameters
- **Opt-out:** Never

```ts
import { hash } from '@node-rs/argon2';
const hashed = await hash(password);
```

### 8. Input validation
- **Default:** Validate every user input
- **Opt-out:** For "trusted" inputs (rare)

Use Zod or similar:
```ts
import { z } from 'zod';
const UserSchema = z.object({
  email: z.string().email().max(255),
  displayName: z.string().min(1).max(100),
  age: z.number().int().min(18).max(120),
});

const result = UserSchema.safeParse(input);
if (!result.success) return jsonError('Invalid input', 400);
```

### 9. Rate limiting
- **Default:** All endpoints rate-limited
- **Opt-out:** For specific high-volume endpoints

### 10. Logging
- **Default:** Log every request, every auth event
- **Opt-out:** For health checks, static assets

## The "deny by default" pattern

For authorization, deny by default:
```ts
function canAccess(user: User, resource: Resource): boolean {
  // Default: no access
  if (user.role === 'admin') return true;
  if (resource.ownerId === user.id) return true;
  if (resource.public) return true;
  return false;  // Default: deny
}
```

Not the other way:
```ts
// ❌ Bad: allow by default
function canAccess(user: User, resource: Resource): boolean {
  if (user.role === 'banned') return false;
  return true;  // Default: allow
}
```

## The "secure-by-default" framework

For a new app, set the secure defaults from day 1:
1. **Auth middleware** (applied to all routes)
2. **HTTPS** (CF default)
3. **CSP / security headers** (in the response)
4. **Argon2id** for passwords
5. **Zod** for input validation
6. **Rate limiting** (per IP)
7. **Audit log** (for sensitive actions)
8. **Secret manager** (no secrets in code)
9. **Logging** (structured, PII-aware)
10. **Pen test** (annual)

A new dev who adds a new endpoint inherits all of these.

## The "linter" enforcement

Use ESLint rules to enforce secure defaults:
```json
// .eslintrc.json
{
  "rules": {
    "no-eval": "error",
    "no-implied-eval": "error",
    "no-new-func": "error",
    "no-script-url": "error",
    "no-secrets/no-secrets": "error",  // gitleaks plugin
    "react/no-danger": "error"
  }
}
```

The linter catches the obvious mistakes.

## The "code review" enforcement

The code review checklist should include:
- [ ] Is auth enforced?
- [ ] Is the user authorized for this resource?
- [ ] Is the input validated?
- [ ] Is the rate limit applied?
- [ ] Is the action logged?
- [ ] Are secrets handled correctly?

A reviewer who doesn't check these is rubber-stamping.

## The "framework defaults"

Use frameworks that have secure defaults:
- **Next.js:** HTTPS, HSTS, secure cookies by default
- **Express + Helmet:** security headers
- **CF Workers:** HTTPS, DDoS protection
- **D1:** SQL injection-safe (parameterized queries)

A good framework handles 80% of the security work.

## The "review the defaults" pattern

Periodically, review your defaults:
- Is auth still enforced?
- Are CSP headers still strict?
- Are passwords still hashed with Argon2id?
- Are secrets still in the secret manager?

As the codebase grows, the defaults can drift. Quarterly
review.

## The "secure defaults cheat sheet"

| Concern | Default |
|---|---|
| Auth | Required for all endpoints |
| HTTPS | Always |
| Cookies | Secure, HttpOnly, SameSite=Lax |
| CSP | Strict |
| HSTS | Yes (1 year, includeSubDomains) |
| Passwords | Argon2id |
| Input validation | Zod (or similar) |
| Rate limiting | Per IP, per user |
| Secrets | Secret manager |
| Logging | Structured, PII-aware |
| Audit | Sensitive actions |
| Updates | Auto-update (deps) |
| Backups | Daily |
| Encryption | At rest, in transit |

## Verification
- **Test:** `test/security.test.ts > auth is enforced on
  every endpoint` — passes
- **Live:** Security headers are present on every response
- **Pen test:** Annual third-party review

## Gotchas
- **The "secure default" is not free.** Auth, validation,
  rate limiting add latency. Budget for it.
- **The "secure default" can be a performance hit.** Every
  request runs through middleware. Make the middleware
  fast.
- **The "secure default" can be bypassed.** A developer can
  add a "public" endpoint accidentally. Use a linter +
  review to catch.
- **The "secure default" needs maintenance.** As the
  framework evolves, the defaults may change. Stay
  updated.
- **The "secure default" is not a substitute for design.**
  The app must be designed for security; defaults are the
  last line of defense.

## Related
- `secure-headers.md`
- `csrf-modern-defenses.md`
- `api-key-authentication.md`
- `xss-prevention.md`
- `sql-injection-prevention.md`
- `rate-limiting-strategies.md`
- OWASP: https://cheatsheetseries.owasp.org/cheatsheets/
- Mozilla Observatory: https://observatory.mozilla.org/
