# OAuth 2.0 Device Authorization Flow for CLI Tools with Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

You are building a CLI tool (e.g., `mytool login`) that needs to authenticate the user against an OAuth 2.0 authorization server backed by Cloudflare Workers. The standard Authorization Code flow with PKCE requires a redirect URI that the CLI can receive — either a `localhost` callback server or a custom URL scheme. Both approaches have drawbacks:

- Spinning up a `localhost` HTTP server is fragile (firewall rules, port conflicts, headless CI environments).
- Custom URL schemes require OS-level registration and don't work in SSH sessions or headless Docker containers.

The **OAuth 2.0 Device Authorization Grant** (RFC 8628) solves this: the CLI requests a short-lived code, displays a URL and user code, and polls a token endpoint until the user completes authorization in a browser on *any device* (including a phone). The CLI never needs to open a browser or receive a redirect.

## Context

RFC 8628 defines three endpoints:

1. **Device Authorization Endpoint** (`/device/authorize`): Issues a `device_code` (for the client to poll with) and a `user_code` + `verification_uri` (for the human to type into a browser). Returns optional `verification_uri_complete` embedding the user code for QR display.
2. **Authorization UI** (your Workers-served HTML page): The user navigates to `verification_uri`, logs in, sees the `user_code`, and confirms. The Worker binds the user's identity to the `device_code`.
3. **Token Endpoint** (`/token`): The CLI polls with `grant_type=urn:ietf:params:oauth:grant-type:device_code&device_code=...` until the user confirms, the code expires, or the user denies.

Security properties required:
- `device_code` must be cryptographically random and unguessable (≥ 128 bits).
- `user_code` must be short and human-typeable but collision-resistant (8 alphanumeric characters ≈ 36^8 ≈ 2.8×10¹² combinations — sufficient for a 5-minute window).
- Polling interval must be enforced server-side (Slow Down / access_denied on excessive polling) to prevent brute-force of the `device_code`.
- The binding between `user_code` and authenticated identity must happen only after the user explicitly confirms, never automatically.

State is stored in Cloudflare KV with per-entry TTLs matching the `expires_in` value.

## Device Authorization Endpoint

```typescript
// src/device-auth.ts
import { Env } from './types';

const DEVICE_CODE_EXPIRY_SECONDS = 300;    // 5 minutes
const POLLING_INTERVAL_SECONDS   = 5;
const USER_CODE_CHARSET          = 'BCDFGHJKLMNPQRSTVWXYZ'; // no ambiguous chars
const VERIFICATION_URI           = 'https://auth.example.com/activate';

function randomBytes(n: number): Uint8Array {
  const buf = new Uint8Array(n);
  crypto.getRandomValues(buf);
  return buf;
}

function generateDeviceCode(): string {
  return btoa(String.fromCharCode(...randomBytes(32)))
    .replace(/[+/=]/g, '') // URL-safe, no padding
    .slice(0, 43);          // 43 chars ~ 256 bits of base64url
}

function generateUserCode(): string {
  const bytes = randomBytes(8);
  let code = '';
  for (const byte of bytes) {
    code += USER_CODE_CHARSET[byte % USER_CODE_CHARSET.length];
  }
  // Format as XXXX-XXXX for readability
  return code.slice(0, 4) + '-' + code.slice(4, 8);
}

export async function handleDeviceAuthorize(
  request: Request,
  env: Env
): Promise<Response> {
  // Validate client_id — in a real deployment, look it up in a clients table
  const body      = await request.formData();
  const clientId  = body.get('client_id');
  const scope     = body.get('scope') ?? 'openid profile';

  if (!clientId) {
    return Response.json({ error: 'invalid_client' }, { status: 400 });
  }

  const deviceCode = generateDeviceCode();
  const userCode   = generateUserCode();
  const expiresAt  = Date.now() + DEVICE_CODE_EXPIRY_SECONDS * 1000;

  // Store device code state in KV with TTL
  await env.DEVICE_CODES.put(
    `device:${deviceCode}`,
    JSON.stringify({
      userCode,
      clientId,
      scope,
      status: 'pending',   // 'pending' | 'authorized' | 'denied' | 'used'
      userId: null,
      expiresAt,
      lastPolled: 0,
    }),
    { expirationTtl: DEVICE_CODE_EXPIRY_SECONDS }
  );

  // Also index by user code so the activation UI can look it up
  await env.DEVICE_CODES.put(
    `usercode:${userCode.replace('-', '')}`,
    deviceCode,
    { expirationTtl: DEVICE_CODE_EXPIRY_SECONDS }
  );

  return Response.json({
    device_code:              deviceCode,
    user_code:                userCode,
    verification_uri:         VERIFICATION_URI,
    verification_uri_complete: `${VERIFICATION_URI}?user_code=${userCode}`,
    expires_in:               DEVICE_CODE_EXPIRY_SECONDS,
    interval:                 POLLING_INTERVAL_SECONDS,
  });
}
```

## Token Endpoint (Polling)

```typescript
// src/token.ts
import { Env } from './types';

export async function handleDeviceToken(
  request: Request,
  env: Env
): Promise<Response> {
  const body       = await request.formData();
  const grantType  = body.get('grant_type');
  const deviceCode = body.get('device_code');
  const clientId   = body.get('client_id');

  if (grantType !== 'urn:ietf:params:oauth:grant-type:device_code') {
    return Response.json({ error: 'unsupported_grant_type' }, { status: 400 });
  }
  if (!deviceCode || !clientId) {
    return Response.json({ error: 'invalid_request' }, { status: 400 });
  }

  const raw = await env.DEVICE_CODES.get(`device:${deviceCode}`);
  if (!raw) {
    return Response.json({ error: 'expired_token' }, { status: 400 });
  }

  const state = JSON.parse(raw);

  // Validate client binding
  if (state.clientId !== clientId) {
    return Response.json({ error: 'invalid_client' }, { status: 401 });
  }

  // Enforce polling interval to prevent brute force
  const now = Date.now();
  if (now - state.lastPolled < 5000) {
    // Update lastPolled even on slow_down to reset the interval
    state.lastPolled = now;
    await env.DEVICE_CODES.put(`device:${deviceCode}`, JSON.stringify(state), {
      expirationTtl: Math.ceil((state.expiresAt - now) / 1000),
    });
    return Response.json({ error: 'slow_down' }, { status: 400 });
  }

  state.lastPolled = now;

  if (state.expiresAt < now) {
    return Response.json({ error: 'expired_token' }, { status: 400 });
  }

  if (state.status === 'denied') {
    return Response.json({ error: 'access_denied' }, { status: 400 });
  }

  if (state.status === 'pending') {
    await env.DEVICE_CODES.put(`device:${deviceCode}`, JSON.stringify(state), {
      expirationTtl: Math.ceil((state.expiresAt - now) / 1000),
    });
    return Response.json({ error: 'authorization_pending' }, { status: 400 });
  }

  if (state.status === 'authorized') {
    // Mark as used — one-time redemption
    state.status = 'used';
    await env.DEVICE_CODES.put(`device:${deviceCode}`, JSON.stringify(state), {
      expirationTtl: 30, // short TTL; just prevents a race on double-redemption
    });

    // Issue tokens — in production, generate a real JWT with env.SIGNING_KEY
    const accessToken  = await issueAccessToken(state.userId, state.scope, state.clientId, env);
    const refreshToken = await issueRefreshToken(state.userId, state.clientId, env);

    return Response.json({
      access_token:  <redacted-secret>
      token_type:    'Bearer',
      expires_in:    3600,
      refresh_token: refreshToken,
      scope:         state.scope,
    });
  }

  return Response.json({ error: 'invalid_grant' }, { status: 400 });
}

async function issueAccessToken(userId: string, scope: string, clientId: string, env: Env): Promise<string> {
  // Placeholder — use your JWT signing logic from jwt-best-practices.md
  const payload = { sub: userId, scope, aud: clientId, iat: Math.floor(Date.now()/1000), exp: Math.floor(Date.now()/1000) + 3600 };
  return btoa(JSON.stringify({ alg: 'EdDSA' })) + '.' + btoa(JSON.stringify(payload)) + '.SIGNATURE';
}

async function issueRefreshToken(userId: string, clientId: string, env: Env): Promise<string> {
  const token = btoa(String.fromCharCode(...crypto.getRandomValues(new Uint8Array(32))));
  await env.REFRESH_TOKENS.put(token, JSON.stringify({ userId, clientId }), { expirationTtl: 86400 * 30 });
  return token;
}
```

## Activation UI Worker Route

```typescript
// src/activate.ts — Served at /activate
export async function handleActivate(request: Request, env: Env): Promise<Response> {
  const url      = new URL(request.url);
  const userCode = url.searchParams.get('user_code')?.replace('-', '').toUpperCase();

  if (request.method === 'GET') {
    // Return HTML form — the user sees their user code pre-filled if present
    return new Response(activationHtml(userCode ?? ''), {
      headers: { 'Content-Type': 'text/html; charset=utf-8' },
    });
  }

  if (request.method === 'POST') {
    // In production, validate the session cookie here to confirm user identity
    const form      = await request.formData();
    const inputCode = form.get('user_code')?.toString().replace(/[-\s]/g, '').toUpperCase();
    const action    = form.get('action'); // 'approve' | 'deny'

    if (!inputCode) return new Response('Missing user code', { status: 400 });

    const deviceCodeKey = await env.DEVICE_CODES.get(`usercode:${inputCode}`);
    if (!deviceCodeKey) {
      return new Response('Invalid or expired code', { status: 400 });
    }

    const raw   = await env.DEVICE_CODES.get(`device:${deviceCodeKey}`);
    if (!raw)   return new Response('Code expired', { status: 400 });
    const state = JSON.parse(raw);

    if (state.status !== 'pending') {
      return new Response('Code already used', { status: 400 });
    }

    state.status = action === 'approve' ? 'authorized' : 'denied';
    state.userId = 'user-id-from-session-cookie'; // pull from authenticated session

    const ttl = Math.ceil((state.expiresAt - Date.now()) / 1000);
    await env.DEVICE_CODES.put(`device:${deviceCodeKey}`, JSON.stringify(state), {
      expirationTtl: Math.max(ttl, 1),
    });
    await env.DEVICE_CODES.delete(`usercode:${inputCode}`);

    return new Response(action === 'approve' ? 'Authorized! You may close this tab.' : 'Denied.', {
      headers: { 'Content-Type': 'text/plain' },
    });
  }

  return new Response('Method not allowed', { status: 405 });
}

function activationHtml(prefillCode: string): string {
  return `<!DOCTYPE html><html><body>
<h1>Activate Device</h1>
<form method="POST">
  <label>User Code: <input name="user_code" value="${prefillCode}" required pattern="[A-Z]{4}-[A-Z]{4}"></label>
  <button name="action" value="approve">Approve</button>
  <button name="action" value="deny">Deny</button>
</form></body></html>`;
}
```

## CLI Client Implementation

```bash
#!/usr/bin/env bash
# mytool-login.sh — Device Flow CLI authentication

CLIENT_ID="mytool-cli"
AUTH_SERVER="https://auth.example.com"
TOKEN_FILE="$HOME/.config/mytool/token.json"

# Step 1: Request device + user codes
response=$(curl -s -X POST "$AUTH_SERVER/device/authorize" \
  -d "client_id=$CLIENT_ID" -d "scope=openid profile")

device_code=$(echo "$response" | jq -r '.device_code')
user_code=$(echo "$response"   | jq -r '.user_code')
verify_url=$(echo "$response"  | jq -r '.verification_uri_complete')
interval=$(echo "$response"    | jq -r '.interval')

echo "Open this URL in your browser:"
echo "  $verify_url"
echo ""
echo "Or visit $AUTH_SERVER/activate and enter code: $user_code"
echo ""
echo "Waiting for authorization..."

# Step 2: Poll token endpoint
while true; do
  sleep "$interval"
  token_response=$(curl -s -X POST "$AUTH_SERVER/token" \
    -d "grant_type=urn:ietf:params:oauth:grant-type:device_code" \
    -d "device_code=$device_code" \
    -d "client_id=$CLIENT_ID")

  error=$(echo "$token_response" | jq -r '.error // empty')

  case "$error" in
    authorization_pending) continue ;;
    slow_down) interval=$((interval + 5)); continue ;;
    access_denied) echo "Authorization denied."; exit 1 ;;
    expired_token) echo "Code expired. Run login again."; exit 1 ;;
    "")
      mkdir -p "$(dirname "$TOKEN_FILE")"
      echo "$token_response" > "$TOKEN_FILE"
      chmod 600 "$TOKEN_FILE"
      echo "Logged in successfully."
      exit 0
      ;;
    *) echo "Unexpected error: $error"; exit 1 ;;
  esac
done
```

## Anti-patterns

**Do not use sequential or predictable device codes.** A numeric counter or timestamp-based code allows an attacker to enumerate pending authorizations. Use `crypto.getRandomValues` with at least 128 bits of entropy.

**Do not skip the polling interval enforcement.** Without server-side rate limiting on the token endpoint, an attacker who intercepts a `device_code` in transit can brute-force user confirmation before the legitimate user acts.

**Do not allow the activation page to auto-confirm without explicit user action.** The confirmation button must be explicitly clicked. JavaScript auto-submit on page load is prohibited by RFC 8628 §6.4.

**Do not issue tokens before marking the device code as `used`.** Read-modify-write without atomicity creates a race where two simultaneous polls both succeed. Use Durable Objects or the KV `put` with `ifMatch` to serialize the redemption.

## Gotchas

- **KV eventual consistency**: In rare cases, a KV write in the activation handler may not be immediately visible to the token endpoint in a different Cloudflare datacenter. Use Durable Objects for strict serialisation if this is a concern.
- **User code ambiguity**: Exclude characters `0, O, 1, I, L` from the user code charset to avoid transcription errors when users type the code manually.
- **PKCE irrelevance**: The device flow does not use PKCE because there is no redirect URI to protect. The `device_code` acts as the proof of possession instead.
- **CI environments**: In CI, the `user_code` will never be entered. Consider a machine-to-machine flow (Client Credentials grant) for automated pipelines instead of the device flow.

## Verification

```bash
# Full end-to-end test
curl -s -X POST https://auth.example.com/device/authorize \
  -d "client_id=mytool-cli&scope=openid" | jq .

# Simulate slow_down by polling twice rapidly
DEVICE_CODE="<from above>"
curl -s -X POST https://auth.example.com/token \
  -d "grant_type=urn:ietf:params:oauth:grant-type:device_code" \
  -d "device_code=$DEVICE_CODE&client_id=mytool-cli" | jq .error
# Expected: "authorization_pending"

# Immediately poll again (within 5s) — expect slow_down
curl -s -X POST https://auth.example.com/token \
  -d "grant_type=urn:ietf:params:oauth:grant-type:device_code" \
  -d "device_code=$DEVICE_CODE&client_id=mytool-cli" | jq .error
# Expected: "slow_down"
```

## Related

- `oauth-pkce-flow.md` — Authorization Code + PKCE for browser-based flows
- `jwt-best-practices.md` — signing the access token issued after device flow
- `api-key-rotation-workers-kv-secrets.md` — managing the refresh token store in KV
- `rate-limiting-per-user-d1-durable-objects.md` — Durable Object serialisation for atomic redemption
- `oauth-2.1-spec-consolidation-migration.md` — RFC 8628 in the OAuth 2.1 context

## Sources

- RFC 8628 — OAuth 2.0 Device Authorization Grant (IETF, 2019)
- RFC 6749 — The OAuth 2.0 Authorization Framework (IETF, 2012)
- Cloudflare Workers KV API — expirationTtl and get documentation
- Cloudflare Durable Objects — serialising state for atomic writes
- GitHub CLI source — reference implementation of the device flow in Go
