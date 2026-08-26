# api-key-authentication

**Issue:** API key design — format, scopes, storage, rotation
**Date:** 2026-08-09
**Status:** documented

## Symptom
You ship a "public API" with API keys. Users paste the key in
JS code on their site. The key is in the browser's source. It's
harvested by malicious browser extensions, scrapers, and bots.
You get $50k of abuse in a week.

## Root cause
**An API key in client-side code is a public key, not a secret.**
The threat model is different from server-side keys.

**Source:** OWASP API Security Top 10:
https://owasp.org/www-project-api-security/

> "API keys are meant for identification, not authentication.
> They should not be used to authenticate the user; they should
> be used to identify the calling project."

## Fix
A 3-tier API key design:

### Tier 1: Server-side secret keys (`sk_live_xxx`)
- **Format:** `mc_live_<8 hex>_<64 hex>` (industry standard,
  Stripe-style)
- **Stored:** In the user's secret manager (1Password, Vault),
  NEVER in client-side code
- **Permissions:** Full access to the user's account
- **Rotation:** 90 days recommended (or on suspicion of leak)

### Tier 2: Publishable keys (`pk_live_xxx`)
- **Format:** `mc_pub_<8 hex>_<32 hex>`
- **Stored:** Safe to expose in client-side code (browser,
  mobile app)
- **Permissions:** Read-only, or specific write actions
  (e.g. "create a checkout session")
- **Limitations:** Rate-limited per key; can't perform admin
  actions

### Tier 3: Restricted keys (`rk_live_xxx` or `rk_test_xxx`)
- **Format:** `mc_rk_<8 hex>_<32 hex>`
- **Stored:** In backend services, NEVER in client-side code
- **Permissions:** Specific resource types (e.g. "read-only
  on /users") or specific tenant scopes
- **Limitations:** Custom rate limits per key

## API key format

```
<prefix>_<env>_<key_id>_<secret>

Examples:
mc_live_a1b2c3d4_e5f6a1b2c3d4e5f6...   # server-side, production
mc_test_a1b2c3d4_e5f6a1b2c3d4e5f6...   # server-side, test
mc_pub_a1b2c3d4_e5f6a1b2c3d4e5f6       # publishable
mc_rk_live_a1b2c3d4_e5f6a1b2c3d4e5f6   # restricted
```

- **`<prefix>`** identifies the platform (e.g. `mc` for
  "MissionControl")
- **`<env>`** is `live` or `test`
- **`<key_id>`** is a short identifier (8 hex) — used for
  lookups
- **`<secret>`** is the long secret (32-64 hex) — the actual
  auth

The full key is shown to the user ONCE (at creation). After
that, only the `key_id` + a SHA-256 hash of the secret is stored.

## Storage

```ts
// On key creation
const keyId = crypto.randomUUID().slice(0, 8);
const secret = <redacted-secret> '') + ...;  // 32+ hex
const fullKey = `mc_live_${keyId}_${secret}`;
const keyHash = await sha256Hex(fullKey);

// Store in DB
await env.DB!.prepare(
  `INSERT INTO api_keys (id, user_id, tenant_id, key_hash, name, scopes, created_at)
   VALUES (?, ?, ?, ?, ?, ?, ?)`
).bind(keyId, userId, tenantId, keyHash, name, JSON.stringify(scopes), Date.now()).run();

// Return the full key ONCE
return new Response(JSON.stringify({ key: fullKey, id: keyId }), { status: 201 });
```

```ts
// On auth
async function authenticateApiKey(auth: string, env: Env): Promise<ApiKey | null> {
  const match = auth.match(/^Bearer\s+(mc_(?:live|test)_[a-f0-9]{8}_[a-f0-9]{64})$/);
  if (!match) return null;
  const fullKey = match[1];
  const keyHash = await sha256Hex(fullKey);
  const apiKey = await env.DB!.prepare(
    `SELECT id, user_id, tenant_id, scopes, expires_at, revoked_at
       FROM api_keys
      WHERE id = ? AND key_hash = ? AND (expires_at IS NULL OR expires_at > ?) AND revoked_at IS NULL
      LIMIT 1`
  ).bind(/* extract key_id */, keyHash, Math.floor(Date.now() / 1000)).first();
  return apiKey;
}
```

## Scopes

```ts
// On key creation
const scopes = [
  'users:read',
  'users:write',
  'posts:read',
  'webhooks:write',
  // 'admin:*',  // never include in scoped keys
];

// On auth, check the scope
if (!apiKey.scopes.includes('users:write')) {
  return new Response('Forbidden', { status: 403 });
}
```

Common scope patterns:
- `<resource>:<action>` — `users:read`, `users:write`,
  `users:delete`
- `admin:*` — for admin actions (NOT for restricted keys)
- `tenant:<id>` — limit to a specific tenant (for service
  accounts that manage one tenant)

## Rotation

API keys should be rotated periodically:
- **Server-side secret keys:** every 90 days
- **Publishable keys:** rarely (they're meant to be public)
- **Restricted keys:** every 180 days
- **On suspicion of leak:** immediately

For rotation, see `secrets-rotation-runbook.md`.

## Verification
- **Test:** `test/api-key.test.ts` — key format, scope check,
  rotation, revocation
- **Live:** Keys are hashed in the DB (not stored in plaintext)
- **Audit:** Annual review of key scopes + rotation cadence

## Gotchas
- **Never log the full key.** Log only the key_id. A stack trace
  that includes the auth header is a leak.
- **The key prefix (`mc_live_...`) is a fingerprint.** Don't
  reject keys with different prefixes (forward compat). But do
  flag them in logs for monitoring.
- **The "show key once" pattern is intentional.** If the user
  loses the key, they generate a new one. The old is revoked.
- **Scope design is hard.** Start with broad scopes, then
  narrow based on user feedback. Don't over-engineer.
- **Per-IP rate limits on publishable keys** prevent abuse
  even if the key is leaked.
- **CF Workers + Pages can use short-lived tokens** (1 hour)
  generated by the server for the client. The client uses the
  short-lived token; the server uses the long-lived key.

## Related
- `secrets-rotation-runbook.md`
- `csrf-protection-double-submit.md` (for cookie auth)
- `rate-limiting-strategies.md` (per-key rate limits)
- Stripe API keys: https://stripe.com/docs/keys
