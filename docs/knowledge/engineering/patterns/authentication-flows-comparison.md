# authentication-flows-comparison

**Issue:** Pick the right auth flow — password, magic link, OAuth, passkey
**Date:** 2026-08-09
**Status:** documented

## Symptom
You build a login screen with email + password. Users
complain "I forgot my password." You add a "forgot password"
flow. Users complain "I don't want to remember another
password." You add OAuth (Sign in with Google). Users
complain "I don't have a Google account." You add magic
links. Users complain "It expired."

## Root cause
**No single auth flow is perfect.** Each has tradeoffs. Pick
the one that fits your audience.

**Source:** Various auth guides.

## The 5 main auth flows

### 1. Email + password
- **What:** User enters email + password
- **Pros:** Familiar, no third party
- **Cons:** Users forget passwords; password DB is a target

### 2. Magic link (passwordless)
- **What:** User enters email; receives a link; clicks to log in
- **Pros:** No password to remember
- **Cons:** Inbox-dependent; can be intercepted

### 3. OAuth (Sign in with Google, Apple, etc.)
- **What:** User clicks "Sign in with Google"; redirected to
  Google; back to your app
- **Pros:** No password; identity verified
- **Cons:** Vendor dependency; user data shared

### 4. Passkey (WebAuthn)
- **What:** User uses device biometrics (Face ID, Touch ID,
  Windows Hello)
- **Pros:** No password; phishing-resistant
- **Cons:** Device-dependent; not yet universal

### 5. SMS OTP
- **What:** User enters phone; receives a code; enters the code
- **Pros:** Works on any phone
- **Cons:** SMS interception; SIM swap; cost

## The "best practice" stack for a 21+ social platform

For a regulated social platform (with age verification,
KYC, etc.):

1. **Primary: Email + password** (familiar, works for most)
2. **Secondary: Passkey** (for users who want passwordless)
3. **Recovery: Magic link** (for "forgot password")
4. **OAuth: Optional** (Sign in with Google, Apple — for
   friction reduction)

Age verification is REQUIRED before account activation, so
the auth flow must be followed by a KYC step.

## The "password" flow

```ts
// Server
async function login(email: string, password: string, env: Env): Promise<string> {
  const user = await env.DB!.prepare(
    `SELECT id, password_hash, salt FROM users WHERE email = ?`
  ).bind(email).first<User>();

  if (!user) {
    // Don't reveal whether the user exists
    throw new Error('Invalid credentials');
  }

  const isValid = await verifyPassword(password, user.password_hash, user.salt);
  if (!isValid) {
    throw new Error('Invalid credentials');
  }

  return createSession(user.id, env);
}
```

For password hashing, use **Argon2id** (or **bcrypt** as a
fallback):
```ts
import { hash, verify } from '@node-rs/argon2';

const hashed = await hash(password);
const isValid = await verify(hashed, password);
```

Argon2id is the modern standard. Don't use SHA-256, MD5, or
even bcrypt for new apps.

## The "magic link" flow

```ts
// 1. User enters email
async function requestMagicLink(email: string, env: Env): Promise<void> {
  const user = await env.DB!.prepare(
    `SELECT id FROM users WHERE email = ?`
  ).bind(email).first<User>();
  if (!user) return;  // Don't reveal whether the user exists

  // 2. Generate a one-time token
  const token = crypto.randomUUID();
  const expiresAt = new Date(Date.now() + 15 * 60 * 1000);  // 15 min

  // 3. Store the token
  await env.DB!.prepare(
    `INSERT INTO magic_links (token, user_id, expires_at) VALUES (?, ?, ?)`
  ).bind(token, user.id, expiresAt.toISOString()).run();

  // 4. Send the link
  await sendEmail(email, `Click to sign in: https://example.com/auth/magic?token=${token}`);
}

// User clicks the link:
// 5. Verify the token
async function consumeMagicLink(token: string, env: Env): Promise<string> {
  const row = await env.DB!.prepare(
    `SELECT user_id, expires_at FROM magic_links WHERE token = ? AND used_at IS NULL`
  ).bind(token).first<{ user_id: string; expires_at: string }>();

  if (!row || new Date(row.expires_at) < new Date()) {
    throw new Error('Invalid or expired link');
  }

  // 6. Mark as used
  await env.DB!.prepare(
    `UPDATE magic_links SET used_at = ? WHERE token = ?`
  ).bind(new Date().toISOString(), token).run();

  // 7. Create a session
  return createSession(row.user_id, env);
}
```

The token must be:
- **One-time:** Consumed on use
- **Short-lived:** 15 minutes max
- **Cryptographically random:** Use `crypto.randomUUID()` or
  a CSPRNG

## The "OAuth" flow

```ts
// 1. Redirect to Google
const state = crypto.randomUUID();
const redirectUri = `https://example.com/auth/google/callback`;
const url = `https://accounts.google.com/o/oauth2/v2/auth?` +
  `client_id=${env.GOOGLE_CLIENT_ID}` +
  `&redirect_uri=${redirectUri}` +
  `&response_type=code` +
  `&scope=openid+email+profile` +
  `&state=${state}`;
return Response.redirect(url, 302);

// 2. Google redirects back with code + state
async function handleGoogleCallback(code: string, state: string, env: Env): Promise<string> {
  // Verify state
  // Exchange code for access token
  // Get user info from Google
  // Create or update user in your DB
  // Create a session
}
```

Use a library to handle the details (e.g. `openid-client`).

## The "passkey" flow

```ts
// 1. Register a passkey
const challenge = crypto.randomUUID();
const options = {
  challenge,
  rp: { name: 'Example' },
  user: { id: userId, name: email, displayName: name },
  pubKeyCredParams: [{ type: 'public-key', alg: -7 }],  // ES256
};

// Send options to the client; client.createCredential(options);

// 2. Verify the registration
const credential = await verifyRegistration(response);
await storePasskey(userId, credential);

// 3. Login with passkey
const challenge = crypto.randomUUID();
const options = {
  challenge,
  allowCredentials: userPasskeys.map(pk => ({ id: pk.id, type: 'public-key' })),
};

// Send options to the client; client.getAssertion(options);

// 4. Verify the assertion
const verified = await verifyAssertion(response);
if (verified) {
  return createSession(user.id, env);
}
```

Use a library like `@simplewebauthn/server`.

## The "SMS OTP" flow

```ts
// 1. User enters phone
const code = String(Math.floor(Math.random() * 1000000)).padStart(6, '0');
await sendSms(phone, `Your code: ${code}`);
await storeCode(phone, code, expiresAt);

// 2. User enters the code
async function verifyCode(phone: string, code: string, env: Env): Promise<string> {
  const row = await env.DB!.prepare(
    `SELECT user_id, expires_at FROM sms_codes WHERE phone = ? AND code = ? AND used_at IS NULL`
  ).bind(phone, code).first<{ user_id: string; expires_at: string }>();

  if (!row || new Date(row.expires_at) < new Date()) {
    throw new Error('Invalid or expired code');
  }

  return createSession(row.user_id, env);
}
```

SMS is the **least secure** of the methods (SIM swap, SMS
interception). Use it only when the alternatives don't work
(no email, no passkey).

## The "MFA" addition

For high-value accounts, add MFA (TOTP, SMS, or passkey):
```ts
// After password login, check if MFA is enabled
if (user.mfaEnabled) {
  // Redirect to MFA challenge
  return redirectToMFA(user.id);
}
```

For a regulated platform, MFA should be required for:
- Admin accounts
- High-value transactions
- Sensitive operations (password change, account deletion)

## Verification
- **Test:** `test/auth.test.ts > login works for valid
  credentials, fails for invalid` — passes
- **Test:** `test/auth.test.ts > magic link expires after
  15 minutes` — passes
- **Live:** Auth flow is monitored; alerts on anomaly
- **Pen test:** Annual third-party security review of auth

## Gotchas
- **The "password" flow requires good password policies.**
  Minimum 12 characters; no common passwords; no user
  info in the password.
- **The "magic link" must be one-time.** A reusable link is
  a security hole.
- **The "OAuth" flow has a state parameter.** Without it,
  CSRF attacks are possible.
- **The "passkey" is device-bound.** A user with a new
  device must re-register. Have a recovery flow.
- **The "SMS" is the least secure.** Don't rely on SMS for
  high-security accounts.
- **The auth log is critical.** Log every login (success and
  failure), every MFA challenge, every password reset. See
  `audit-log-as-product.md`.
- **The session must be secure.** Use HTTP-only, Secure,
  SameSite=Strict cookies. See
  `session-cookies-vs-jwt.md`.

## Related
- `webauthn-passkey-flow.md`
- `totp-mfa-implementation.md`
- `session-cookies-vs-jwt.md`
- `password-hashing-argon2.md` (later)
- `audit-log-as-product.md`
- OWASP auth: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
