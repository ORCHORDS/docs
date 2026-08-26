# Workers KV TTL-Gated Token Revocation and Expiry

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You issue short-lived API tokens, magic-link nonces, or password-reset codes that must be revocable before their stated expiry (e.g. user logs out on all devices, detects compromise, or an admin force-expires a session). JWTs are stateless and cannot be revoked without a blocklist. Storing revocation state in D1 adds a DB round-trip per request. KV's built-in TTL mechanism provides a low-latency, automatically self-cleaning revocation store that disappears at expiry with zero maintenance.

## Context

Cloudflare Workers KV supports per-key `expirationTtl` (seconds from now) or `expiration` (Unix epoch). Reads return `null` for expired or missing keys — the same sentinel. This makes KV ideal for two complementary token patterns:

1. **Allowlist pattern** — write the token on issuance; absence = revoked or expired.
2. **Blocklist pattern** — write the token only on revocation; presence = invalid.

The allowlist pattern is safer (no window between issuance and write) but consumes more KV writes. The blocklist pattern is write-efficient but requires enforcing JWT expiry independently to prevent blocklist bypass after TTL clears.

example project tokens are issued as opaque 256-bit random identifiers stored in KV with a JWT that carries only a lookup reference (`kid`), so the KV read is the single source of truth for validity.

---

## 1. Issuing Tokens with KV TTL (Allowlist Pattern)

```typescript
import { Buffer } from "node:buffer";

const TOKEN_TTL_SECONDS = 900; // 15 minutes

async function issueToken(
  userId: string,
  env: Env,
): Promise<{ token: string; expiresAt: number }> {
  const raw = crypto.getRandomValues(new Uint8Array(32));
  const token = Buffer.from(raw).toString("base64url");

  const expiresAt = Math.floor(Date.now() / 1000) + TOKEN_TTL_SECONDS;

  await env.TOKENS_KV.put(
    `token:${token}`,
    JSON.stringify({ userId, issuedAt: Math.floor(Date.now() / 1000) }),
    { expirationTtl: TOKEN_TTL_SECONDS },
  );

  return { token, expiresAt };
}
```

KV automatically deletes the key after `TOKEN_TTL_SECONDS` — no cron cleanup job needed.

---

## 2. Validating Tokens with Constant-Time Safety

```typescript
async function validateToken(
  token: string,
  env: Env,
): Promise<{ userId: string } | null> {
  // Reject structurally invalid tokens before KV lookup to prevent enumeration
  if (!/^[A-Za-z0-9_-]{43}$/.test(token)) return null;

  const raw = await env.TOKENS_KV.get(`token:${token}`, { type: "json" }) as
    | { userId: string; issuedAt: number }
    | null;

  if (!raw) return null; // expired or never issued
  return { userId: raw.userId };
}
```

The 43-character check matches a base64url-encoded 32-byte value — reject anything outside that shape immediately so KV is not used as an oracle for token format guessing.

---

## 3. Immediate Revocation (Blocklist Overlay)

For the allowlist pattern, revocation is a KV delete:

```typescript
async function revokeToken(token: string, env: Env): Promise<void> {
  await env.TOKENS_KV.delete(`token:${token}`);
}

// Revoke all tokens for a user (requires a secondary index in D1)
async function revokeAllUserTokens(userId: string, env: Env): Promise<void> {
  const rows = await env.DB.prepare(
    "SELECT token_id FROM active_tokens WHERE user_id = ? AND expires_at > unixepoch()",
  ).bind(userId).all<{ token_id: string }>();

  await Promise.all(
    rows.results.map((r) => env.TOKENS_KV.delete(`token:${r.token_id}`)),
  );

  await env.DB.prepare(
    "DELETE FROM active_tokens WHERE user_id = ?",
  ).bind(userId).run();
}
```

D1 serves as the index for bulk revocation; KV serves as the fast per-request validity check.

---

## 4. One-Time-Use Nonce Pattern (Magic Links, CSRF Tokens)

```typescript
async function consumeNonce(nonce: string, env: Env): Promise<boolean> {
  if (!/^[A-Za-z0-9_-]{43}$/.test(nonce)) return false;

  // getWithMetadata is not atomic — use a compare-and-delete idiom via
  // a Durable Object for true single-use guarantees under concurrent load.
  // For low-traffic flows, KV delete + check is sufficient.
  const value = await env.NONCES_KV.get(`nonce:${nonce}`);
  if (!value) return false; // already consumed or expired

  await env.NONCES_KV.delete(`nonce:${nonce}`);
  return true;
}

async function issueNonce(purpose: string, env: Env): Promise<string> {
  const raw = crypto.getRandomValues(new Uint8Array(32));
  const nonce = Buffer.from(raw).toString("base64url");
  await env.NONCES_KV.put(
    `nonce:${nonce}`,
    JSON.stringify({ purpose, ts: Date.now() }),
    { expirationTtl: 300 }, // 5-minute magic link window
  );
  return nonce;
}
```

---

## 5. Sliding Window Refresh via TTL Extension

Extend the TTL on each successful use to implement sliding-window sessions without a separate session store:

```typescript
const SESSION_TTL = 1800; // 30 minutes idle timeout
const SESSION_MAX = 86400; // 24-hour hard ceiling

async function touchSession(
  sessionId: string,
  env: Env,
): Promise<{ userId: string } | null> {
  const key = `session:${sessionId}`;
  const data = await env.SESSIONS_KV.get(key, { type: "json" }) as
    | { userId: string; createdAt: number }
    | null;

  if (!data) return null;

  const age = Math.floor(Date.now() / 1000) - data.createdAt;
  if (age >= SESSION_MAX) {
    await env.SESSIONS_KV.delete(key);
    return null;
  }

  // Re-write with fresh TTL (idle reset)
  await env.SESSIONS_KV.put(key, JSON.stringify(data), {
    expirationTtl: SESSION_TTL,
  });

  return { userId: data.userId };
}
```

The hard ceiling prevents indefinite session extension even if an attacker keeps making requests to keep the idle TTL alive.

---

## 6. Namespace Isolation and Scoping

Bind separate KV namespaces per token type in `wrangler.toml` to limit blast radius if a namespace binding is misconfigured:

```toml
[[kv_namespaces]]
binding = "TOKENS_KV"
id = "aaa..."

[[kv_namespaces]]
binding = "NONCES_KV"
id = "bbb..."

[[kv_namespaces]]
binding = "SESSIONS_KV"
id = "ccc..."
```

Each namespace can have independent access policies and is auditable separately in the Cloudflare dashboard.

---

## Anti-patterns

- **Using KV keys as the secret** — the key namespace is not encrypted client-side; the token must be a cryptographically random value stored as the key suffix or as a hashed value, not a predictable identifier.
- **Blocklist without independent expiry enforcement** — once the TTL clears the blocklist entry, a replayed token passes validation; always enforce JWT `exp` independently.
- **Listing all KV keys to find user tokens** — `list()` is eventually consistent and slow; maintain a D1 index for bulk revocation instead.
- **Storing sensitive payload in KV value** — KV values are visible to anyone with the namespace binding; store only non-sensitive metadata (userId, issuedAt) and keep secrets in Workers Secrets Store.
- **Setting no TTL on revocation blocklist entries** — blocklist grows unbounded; always match the TTL to the token's maximum lifetime.

## Gotchas

- KV is eventually consistent — a freshly written key may not be visible from all edge locations for up to 60 seconds. For security-critical revocation (e.g. compromised credentials), use Durable Objects for strongly consistent reads or accept a brief revocation propagation delay.
- `expirationTtl` minimum is 60 seconds; you cannot use KV TTL for sub-minute nonces.
- KV `delete()` is not transactional with a concurrent `get()` — two simultaneous nonce consumption attempts can both read a value before either delete completes. Use a Durable Object alarm or atomic counter for strict single-use guarantees.
- KV free tier allows 1,000 writes/day; high-issuance token flows can hit limits unexpectedly — size the namespace billing tier appropriately.

## Verification

```bash
# Confirm token appears in KV after issuance
wrangler kv key get --namespace-id=<id> "token:<your-token-value>"

# Confirm token is gone after revocation or TTL expiry
wrangler kv key get --namespace-id=<id> "token:<your-token-value>"
# Expected: Value not found

# Smoke test one-time nonce (second call must return 401)
curl -X POST https://api.example.com/auth/magic \
  -d '{"nonce":"<nonce>"}' -H "Content-Type: application/json"
# Second attempt:
curl -X POST https://api.example.com/auth/magic \
  -d '{"nonce":"<nonce>"}' -H "Content-Type: application/json"
# Expected: {"error":"invalid_nonce"}
```

## Related

- `jwt-sliding-window-refresh-workers-kv.md`
- `api-key-rotation-workers-kv-secrets.md`
- `durable-objects-alarm-session-expiry-revocation.md`
- `idempotency-one-time-secret-replay.md`
- `rate-limiting-sliding-window-durable-objects.md`

## Sources

- Cloudflare Workers KV — TTL and expiration — https://developers.cloudflare.com/kv/api/write-key-value-pairs/#expiring-keys
- NIST SP 800-63B §4.1.3 — Session Management
- RFC 6749 §10.3 — OAuth 2.0 Access Token Security Considerations
