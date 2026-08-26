# feature-cookbook-auth

**Issue:** Auth implementation — password, OAuth, MFA, session
**Date:** 2026-08-09
**Status:** documented

## Symptom
You build a login. The user enters email + password. The
password is checked. The session is created. A week
later, a security audit finds the password is in plain
text. The session cookie is http-only but the token is
visible in localStorage. MFA is "coming soon."

## Root cause
**Auth is the most security-sensitive feature.** Get it
right from day 1.

**Source:** OWASP Authentication Cheat Sheet:
https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html

## The "password" pattern (Argon2id)

For password hashing, use Argon2id (the modern standard):
```ts
import { hash, verify, Algorithm } from '@node-rs/argon2';

const hashed = await hash(password, {
  algorithm: Algorithm.Argon2id,
  memoryCost: 19456,  // 19 MB
  timeCost: 2,
  parallelism: 1,
});

const isValid = await verify(hashed, password);
```

Argon2id is the winner of the Password Hashing Competition.

## The "password requirements" pattern

For password strength:
```ts
const PASSWORD_MIN_LENGTH = 12;
const COMMON_PASSWORDS = ['password', 'qwerty', '12345678', 'admin', 'welcome'];

function isPasswordStrong(password: string, userInfo: { email: string; name: string }): { ok: boolean; reason?: string } {
  if (password.length < PASSWORD_MIN_LENGTH) {
    return { ok: false, reason: 'Password must be at least 12 characters' };
  }
  if (COMMON_PASSWORDS.includes(password.toLowerCase())) {
    return { ok: false, reason: 'Password is too common' };
  }
  if (password.includes(userInfo.email.split('@')[0])) {
    return { ok: false, reason: 'Password cannot contain your email' };
  }
  if (password.includes(userInfo.name)) {
    return { ok: false, reason: 'Password cannot contain your name' };
  }
  return { ok: true };
}
```

For NIST 800-63B, focus on length + breach detection, not
complexity.

## The "breach detection" pattern

For checking passwords against known breaches:
```ts
async function isPasswordBreached(password: string): Promise<boolean> {
  // Use haveibeenpwned's k-anonymity API
  const sha1 = crypto.subtle.digest('SHA-1', new TextEncoder().encode(password));
  const hash = Array.from(new Uint8Array(sha1)).map(b => b.toString(16).padStart(2, '0')).join('').toUpperCase();
  const prefix = hash.slice(0, 5);
  const suffix = hash.slice(5);

  const response = await fetch(`https://api.pwnedpasswords.com/range/${prefix}`);
  const text = await response.text();

  return text.split('\n').some((line) => line.startsWith(suffix));
}
```

The HIBP API is the standard.

## The "session" pattern

For sessions, use HTTP-only cookies:
```ts
async function createSession(userId: string, env: Env): Promise<{ token: string; expiresAt: number }> {
  const token = crypto.randomUUID();
  const expiresAt = Date.now() + 24 * 60 * 60 * 1000;  // 24 hours

  await env.SESSIONS.put(`session:${token}`, JSON.stringify({
    userId,
    createdAt: Date.now(),
    expiresAt,
  }), {
    expirationTtl: 86400,
  });

  return { token, expiresAt };
}

function setSessionCookie(token: string, expiresAt: number): string {
  return `session=${token}; HttpOnly; Secure; SameSite=Lax; Path=/; Expires=${new Date(expiresAt).toUTCString()}`;
}
```

The session token is a random UUID; the cookie is HTTP-only.

## The "session validation" pattern

For every request, validate the session:
```ts
async function validateSession(request: Request, env: Env): Promise<Session | null> {
  const cookie = parseCookie(request.headers.get('Cookie') ?? '');
  const token = cookie.session;
  if (!token) return null;

  const data = await env.SESSIONS.get(`session:${token}`);
  if (!data) return null;

  return JSON.parse(data);
}
```

The session is validated on every request.

## The "session rotation" pattern

For privilege escalation, rotate the session:
```ts
async function rotateSession(oldToken: string, userId: string, env: Env): Promise<string> {
  // 1. Invalidate the old session
  await env.SESSIONS.delete(`session:${oldToken}`);

  // 2. Create a new session
  return createSession(userId, env);
}
```

A new token is created; the old one is invalidated.

## The "CSRF" pattern

For CSRF protection, use the double-submit cookie pattern:
```ts
function setCsrfTokenCookie(): string {
  const token = crypto.randomUUID();
  return `csrf=${token}; HttpOnly=false; Secure; SameSite=Lax; Path=/`;
}

// On the client, send the token in a header
// On the server, verify the header matches the cookie
async function verifyCsrf(request: Request, env: Env): Promise<boolean> {
  const cookie = parseCookie(request.headers.get('Cookie') ?? '');
  const header = request.headers.get('X-CSRF-Token');
  return cookie.csrf === header;
}
```

The cookie + header must match.

## The "rate limiting" pattern for auth

For login attempts, rate limit per IP:
```ts
const MAX_LOGIN_ATTEMPTS = 5;
const LOCKOUT_MINUTES = 15;

async function checkLoginAttempts(ip: string, env: Env): Promise<{ allowed: boolean; remaining: number }> {
  const id = env.RATE_LIMIT.idFromName(`login:${ip}`);
  const stub = env.RATE_LIMIT.get(id);
  const response = await stub.fetch('https://rate-limit/check', {
    method: 'POST',
    body: JSON.stringify({ limit: MAX_LOGIN_ATTEMPTS, windowMs: LOCKOUT_MINUTES * 60 * 1000 }),
  });
  return response.json();
}
```

Brute force is blocked.

## The "OAuth" pattern (Google)

```ts
async function startGoogleOAuth(env: Env): Promise<Response> {
  const state = crypto.randomUUID();
  const redirectUri = `https://example.com/auth/google/callback`;

  // Store the state in KV (for verification on callback)
  await env.KV.put(`oauth:state:${state}`, '1', { expirationTtl: 600 });

  const url = new URL('https://accounts.google.com/o/oauth2/v2/auth');
  url.searchParams.set('client_id', env.GOOGLE_CLIENT_ID);
  url.searchParams.set('redirect_uri', redirectUri);
  url.searchParams.set('response_type', 'code');
  url.searchParams.set('scope', 'openid email profile');
  url.searchParams.set('state', state);

  return Response.redirect(url.toString(), 302);
}

async function handleGoogleCallback(code: string, state: string, env: Env): Promise<Response> {
  // 1. Verify the state
  const stored = await env.KV.get(`oauth:state:${state}`);
  if (!stored) throw new Error('Invalid state');
  await env.KV.delete(`oauth:state:${state}`);

  // 2. Exchange the code for an access token
  const tokenResponse = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      code,
      client_id: env.GOOGLE_CLIENT_ID,
      client_secret: env.GOOGLE_CLIENT_SECRET,
      redirect_uri: 'https://example.com/auth/google/callback',
      grant_type: 'authorization_code',
    }),
  });

  const tokens = await tokenResponse.json();

  // 3. Get the user info
  const userResponse = await fetch('https://www.googleapis.com/oauth2/v2/userinfo', {
    headers: { 'Authorization': `Bearer ${tokens.access_token}` },
  });
  const userInfo = await userResponse.json();

  // 4. Create or update the user
  // 5. Create a session
}
```

## The "TOTP MFA" pattern

For MFA, use TOTP (RFC 6238):
```ts
import { authenticator } from 'otplib';

// Generate a secret
const secret = <redacted-secret>
const uri = authenticator.keyuri('alice@example.com', 'MyApp', secret);
// Display the QR code

// Verify a code
const isValid = authenticator.verify({ token: userInput, secret });
```

The user scans the QR code with Google Authenticator / Authy.

## The "backup codes" pattern

For MFA recovery, provide backup codes:
```ts
async function generateBackupCodes(userId: string, env: Env): Promise<string[]> {
  const codes = Array.from({ length: 10 }, () =>
    Array.from({ length: 8 }, () => Math.floor(Math.random() * 10)).join('')
  );

  // Store the hashes (not the plain codes)
  const hashedCodes = await Promise.all(codes.map(c => hash(c)));
  await env.DB!.prepare(
    `UPDATE users SET backup_codes = ? WHERE id = ?`
  ).bind(JSON.stringify(hashedCodes), userId).run();

  return codes;
}
```

The user has 10 backup codes; each can be used once.

## The "session security" pattern

For session security:
- **HTTP-only cookie:** JavaScript can't access
- **Secure flag:** Only over HTTPS
- **SameSite=Lax:** CSRF protection
- **Session ID rotation:** On login + privilege escalation
- **Session timeout:** 24 hours of inactivity
- **IP validation:** Reject if the IP changes (controversial)

## The "user enumeration" pattern

For privacy, don't reveal whether an email is registered:
```ts
// ❌ Bad: reveals whether the user exists
if (!user) return new Response('User not found', { status: 404 });
if (!isPasswordValid) return new Response('Wrong password', { status: 401 });

// ✅ Good: same response for both cases
if (!user || !await verifyPassword(password, user.password_hash)) {
  return new Response('Invalid credentials', { status: 401 });
}
```

The attacker can't enumerate users.

## The "secure password reset" pattern

For password reset:
```ts
// 1. Generate a token
const token = crypto.randomUUID();
const expiresAt = new Date(Date.now() + 60 * 60 * 1000);  // 1 hour

// 2. Store the token (hashed)
const tokenHash = await hash(token);
await env.DB!.prepare(
  `INSERT INTO password_resets (token_hash, user_id, expires_at) VALUES (?, ?, ?)`
).bind(tokenHash, userId, expiresAt.toISOString()).run();

// 3. Send the link (with the unhashed token)
await sendEmail({
  to: email,
  subject: 'Reset your password',
  html: `Click to reset: https://example.com/reset?token=${token}`,
}, env);

// 4. Verify the token (compare hashes)
const row = await env.DB!.prepare(
  `SELECT user_id, expires_at FROM password_resets WHERE token_hash = ? AND used_at IS NULL`
).bind(hash(token)).first();

if (!row || new Date(row.expires_at) < new Date()) {
  throw new Error('Invalid or expired token');
}

// 5. Update the password
// 6. Mark the token as used
```

The token is hashed; the link is sent once.

## Verification
- **Test:** Login works
- **Test:** Wrong password fails
- **Test:** Rate limit blocks brute force
- **Test:** Session is HTTP-only
- **Test:** CSRF is blocked
- **Pen test:** Annual security review

## Gotchas
- **The "plain text password" anti-pattern.** Always hash.
- **The "weak password" anti-pattern.** Enforce minimum
  length.
- **The "session in localStorage" anti-pattern.** XSS can
  steal it. Use HTTP-only cookies.
- **The "no CSRF" anti-pattern.** Every state-changing
  request is vulnerable. Use CSRF tokens.
- **The "user enumeration" anti-pattern.** A 404 vs 401
  tells the attacker the user exists. Use the same
  response.
- **The "no rate limit" anti-pattern.** Brute force is
  trivial. Rate limit login attempts.

## Related
- `authentication-flows-comparison.md`
- `webauthn-passkey-flow.md`
- `totp-mfa-implementation.md`
- `session-cookies-vs-jwt.md`
- `csrf-modern-defenses.md`
- `password-hashing-argon2.md` (later)
- OWASP: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
