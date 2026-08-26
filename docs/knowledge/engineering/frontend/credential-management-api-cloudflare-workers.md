# Credential Management API — Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

On example.com (anonymous social platform), users frequently sign in and out across sessions. The native browser sign-in flow — where the browser offers to save credentials and auto-fill on return — is bypassed when the app handles auth entirely in JavaScript. The Credential Management API lets the app mediate credential storage and retrieval through the browser's secure credential store, enabling one-tap sign-in, auto sign-in for returning users, and silent re-authentication without a full form submission.

## Context

Cloudflare Workers handles the auth endpoints (`/api/auth/login`, `/api/auth/token`). The frontend uses the Credential Management API to retrieve saved credentials before showing the login form, passes them to the Workers endpoint, and stores new credentials upon successful authentication. This integrates with the browser's native password manager, as well as passkey (WebAuthn) credentials via the `PublicKeyCredential` sub-type.

## Credential Management API Overview

The API centers on `navigator.credentials` — a `CredentialsContainer` with `get()`, `store()`, `create()`, and `preventSilentAccess()` methods. The `PasswordCredential` type covers username/password pairs. `FederatedCredential` covers OAuth providers. `PublicKeyCredential` covers passkeys (covered separately in `webauthn-conditional-mediation-autofill.md`).

```typescript
// Feature detection
function credentialManagementSupported(): boolean {
  return (
    'credentials' in navigator &&
    typeof navigator.credentials.get === 'function' &&
    typeof window.PasswordCredential !== 'undefined'
  );
}

// Attempt silent sign-in for returning users
async function attemptSilentSignIn(): Promise<boolean> {
  if (!credentialManagementSupported()) return false;

  let credential: Credential | null;
  try {
    credential = await navigator.credentials.get({
      password: true,
      mediation: 'silent', // Only resolves if exactly one credential is stored
    });
  } catch {
    return false;
  }

  if (!credential || credential.type !== 'password') return false;

  const pc = credential as PasswordCredential;
  return signInWithCredential(pc.id, pc.password ?? '');
}
```

## Storing Credentials After Login

After the user successfully authenticates via the login form, call `navigator.credentials.store()` with a `PasswordCredential` constructed from the form element. The browser then prompts the user to save the credentials.

```typescript
// src/lib/auth.ts

interface LoginFormElements extends HTMLFormControlsCollection {
  username: HTMLInputElement;
  password: <redacted-secret>
}

async function loginWithForm(form: HTMLFormElement): Promise<void> {
  const elements = form.elements as LoginFormElements;
  const username = elements.username.value.trim();
  const password = <redacted-secret>

  // Authenticate against Cloudflare Workers endpoint
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error('Authentication failed');
  }

  // Store credentials in the browser's credential manager
  if (credentialManagementSupported()) {
    try {
      // PasswordCredential can accept the form element directly
      const credential = new PasswordCredential(form);
      await navigator.credentials.store(credential);
    } catch (err) {
      // Non-fatal — user may have dismissed the save prompt
      console.warn('Credential storage failed:', err);
    }
  }

  await onAuthSuccess();
}

// Alternative: construct PasswordCredential manually (without a form element)
async function storeCredentialsManually(
  id: string,
  password: string,
  name?: string
): Promise<void> {
  if (!credentialManagementSupported()) return;

  const credential = new PasswordCredential({
    id,
    password,
    name: name ?? id,
    iconURL: `https://example.com/api/avatars/${encodeURIComponent(id)}`,
  });

  await navigator.credentials.store(credential);
}
```

## Sign-in Flow with Mediation Levels

Three mediation levels control how much the browser interacts with the user when retrieving credentials.

```typescript
// src/lib/credential-flow.ts

type MediationRequirement = 'silent' | 'optional' | 'required' | 'conditional';

async function getCredential(
  mediation: MediationRequirement
): Promise<PasswordCredential | null> {
  if (!credentialManagementSupported()) return null;

  try {
    const credential = await navigator.credentials.get({
      password: true,
      federated: {
        providers: [], // No federated providers for this anonymous platform
      },
      mediation,
    });

    if (credential?.type === 'password') {
      return credential as PasswordCredential;
    }
  } catch (err) {
    // AbortError: user dismissed the account chooser
    // NotSupportedError: method not supported in this context
    if ((err as DOMException).name !== 'AbortError') {
      console.error('Credential retrieval error:', err);
    }
  }

  return null;
}

// App entry point — tiered sign-in attempt
async function bootstrapAuth(): Promise<void> {
  // 1. Try silent (no UI, single stored credential)
  const silentCred = await getCredential('silent');
  if (silentCred) {
    const ok = await signInWithCredential(silentCred.id, silentCred.password ?? '');
    if (ok) return;
  }

  // 2. Try optional (shows account chooser if multiple credentials stored)
  const optionalCred = await getCredential('optional');
  if (optionalCred) {
    const ok = await signInWithCredential(optionalCred.id, optionalCred.password ?? '');
    if (ok) return;
  }

  // 3. Fall through to the login form
  showLoginForm();
}

async function signInWithCredential(id: string, password: string): Promise<boolean> {
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: id, password }),
    credentials: 'include',
  });
  return response.ok;
}
```

## Cloudflare Workers Auth Endpoint

The Workers endpoint validates credentials, sets an HttpOnly session cookie, and returns a minimal payload. It never returns the password to the client — it only signals success or failure.

```typescript
// functions/api/auth/login.ts

import type { PagesFunction } from '@cloudflare/workers-types';

interface Env {
  AUTH_KV: KVNamespace;
  SESSION_SECRET: string;
}

interface LoginBody {
  username: string;
  password: string;
}

export const onRequestPost: PagesFunction<Env> = async (ctx) => {
  let body: LoginBody;
  try {
    body = await ctx.request.json<LoginBody>();
  } catch {
    return new Response('Invalid JSON', { status: 400 });
  }

  const { username, password } = body;
  if (!username || !password) {
    return new Response('Missing credentials', { status: 400 });
  }

  // Look up hashed password in KV
  const storedHash = await ctx.env.AUTH_KV.get(`user:${username}:pw`);
  if (!storedHash) {
    // Timing-safe: still do the comparison to avoid timing attacks
    await verifyPassword('dummy', 'dummy-hash');
    return new Response('Invalid credentials', { status: 401 });
  }

  const valid = await verifyPassword(password, storedHash);
  if (!valid) {
    return new Response('Invalid credentials', { status: 401 });
  }

  const sessionToken = crypto.randomUUID();
  await ctx.env.AUTH_KV.put(`session:${sessionToken}`, username, {
    expirationTtl: 60 * 60 * 24 * 7, // 7 days
  });

  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      'Set-Cookie': [
        `session=${sessionToken}`,
        'HttpOnly',
        'Secure',
        'SameSite=Strict',
        'Path=/',
        'Max-Age=604800',
      ].join('; '),
    },
  });
};

async function verifyPassword(password: string, hash: string): Promise<boolean> {
  // Placeholder — use a proper PBKDF2/bcrypt implementation
  const enc = new TextEncoder();
  const keyMaterial = await crypto.subtle.importKey(
    'raw', enc.encode(password), 'PBKDF2', false, ['deriveBits']
  );
  const derived = await crypto.subtle.deriveBits(
    { name: 'PBKDF2', salt: enc.encode('salt'), iterations: 100000, hash: 'SHA-256' },
    keyMaterial, 256
  );
  const derivedHex = Array.from(new Uint8Array(derived))
    .map((b) => b.toString(16).padStart(2, '0')).join('');
  return derivedHex === hash;
}
```

## Preventing Auto Sign-In After Sign-Out

When the user signs out, call `navigator.credentials.preventSilentAccess()` to tell the browser not to auto sign-in on the next page load.

```typescript
async function signOut(): Promise<void> {
  await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });

  if ('credentials' in navigator) {
    // Prevents silent mediation on next visit
    await navigator.credentials.preventSilentAccess();
  }

  window.location.href = '/';
}
```

## Anti-patterns

- Calling `navigator.credentials.get({ mediation: 'required' })` on page load — this forces the account chooser UI even for users who are already signed in, creating friction.
- Constructing `PasswordCredential` with `new PasswordCredential({ id, password })` and then logging `password` anywhere — the password field is intentionally opaque in some browsers.
- Relying on `PasswordCredential.password` being non-null — it returns `null` in Firefox and is non-standardized; always test for null before use.
- Not calling `preventSilentAccess()` on sign-out — users who sign out and return will be auto-signed in, which is a significant UX and privacy issue.
- Using the Credential Management API for anonymous/guest sessions — it is designed for identified users; for anonymous sessions, use a short-lived cookie directly.

## Gotchas

- `PasswordCredential` is not available in Firefox (no implementation as of 2026) — feature-detect with `typeof window.PasswordCredential !== 'undefined'`.
- `mediation: 'silent'` resolves to `null` (not reject) if multiple credentials are stored or if the user previously prevented auto sign-in; always handle `null`.
- The `PasswordCredential` constructor that accepts a form element requires the form to have `autocomplete="username"` and `autocomplete="current-password"` on the respective inputs.
- `navigator.credentials.get()` must be called from a top-level browsing context, not from within an iframe.
- Chrome blocks `navigator.credentials.get()` on pages without HTTPS, including `localhost` without a valid certificate.

## Verification

1. Open example.com login page in Chrome.
2. Submit the login form — Chrome prompts to save the password.
3. Accept the save prompt, then sign out (verify `preventSilentAccess` is called via the Network tab).
4. Reload example.com — the login form should appear (no auto sign-in after `preventSilentAccess`).
5. Click the password field — Chrome's autofill suggests the saved credential.
6. Accept — confirm `navigator.credentials.get({ mediation: 'optional' })` fires and returns the credential.
7. In Firefox, confirm the app falls back gracefully to the standard form (no JS errors).

## Related

- `webauthn-conditional-mediation-autofill.md`
- `cloudflare-pages-middleware-auth-gating.md`
- `web-crypto-api-client-side-encryption-cloudflare-pages.md`
- `cookie-store-async-access-and-change-events.md`
- `feature-flags-cloudflare-workers-kv-edge-config.md`

## Sources

- https://developer.mozilla.org/en-US/docs/Web/API/Credential_Management_API
- https://developer.mozilla.org/en-US/docs/Web/API/PasswordCredential
- https://developers.cloudflare.com/pages/functions/
- https://web.dev/articles/sign-in-form-best-practices
- https://web.dev/articles/security-credential-management
- https://www.w3.org/TR/credential-management-1/
