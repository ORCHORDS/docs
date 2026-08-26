# workers-secrets-rotation-zero-downtime

**Issue:** Zero-downtime Workers secrets rotation
**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

A third-party API key or database credential stored as a Cloudflare
Worker secret must be rotated (scheduled or emergency). Rotating the
secret by running `wrangler secret put` and then immediately deleting
the old value causes a 30–60 second propagation window during which
some Worker instances still hold the old value while others have
picked up the new one. Mobile clients that are mid-request during this
window receive 401 errors from the upstream service because the Worker
sends the wrong key. A hard cutover also prevents rolling back to the
old key if the new one is misconfigured.

## Context

Cloudflare Workers secrets are distributed to edge nodes via
Cloudflare's secrets infrastructure. After `wrangler secret put`, the
new value propagates globally within roughly 30–60 seconds. During
that window, different Worker instances may run with different values
of the same secret name. A naive "delete old, set new" rotation is
therefore not atomic. Zero-downtime rotation requires a brief
dual-value acceptance window: the Worker must accept both the outgoing
and incoming credential simultaneously.

**Source:** Cloudflare Docs — Secrets; Cloudflare Blog — Workers
secrets management.

## The "dual-value acceptance window" pattern

Store credentials as versioned secret names (`API_KEY_V1`,
`API_KEY_V2`) rather than a single `API_KEY`. The Worker accepts
either:

```typescript
// src/auth.ts
export async function verifyInboundToken(
  token: string,
  env: Env,
): Promise<boolean> {
  // Accept both the current and the outgoing key during rotation.
  // env.API_KEY_V2 is undefined before rotation begins.
  const valid = [env.API_KEY_V1, env.API_KEY_V2]
    .filter(Boolean)
    .some((k) => k === token);
  return valid;
}
```

Rotation procedure:

```bash
# Step 1: Set V2 (V1 still active — zero impact)
wrangler secret put API_KEY_V2 --env production
# Enter the new secret value at the prompt

# Step 2: Wait for propagation (>60 s)
sleep 90

# Step 3: Update upstream calls to use V2
# (deploy the new Worker version that prefers V2)
npx wrangler deploy --env production

# Step 4: Revoke V1 at the third-party provider

# Step 5: Remove V1 from the Worker (optional cleanup)
wrangler secret delete API_KEY_V1 --env production
```

## The "Cloudflare Secrets vs KV for rotation" comparison

```
+-------------------+-------------------+------------------------+
| Approach          | Propagation       | Best for               |
+-------------------+-------------------+------------------------+
| Workers Secrets   | ~30-60 s global   | Static credentials;    |
| (wrangler secret) |                   | API keys; DB passwords |
+-------------------+-------------------+------------------------+
| KV store          | ~60 s (eventual)  | Frequently rotated     |
|                   |                   | values; multi-key      |
|                   |                   | acceptance windows     |
+-------------------+-------------------+------------------------+
| KV + versioned    | ~60 s but Worker  | High-frequency         |
| key namespace     | reads at request  | rotation (<1 hr cycle) |
|                   | time, no restart  |                        |
+-------------------+-------------------+------------------------+
```

For high-frequency rotation (e.g., short-lived tokens), use KV and
read the current key at request time rather than binding it as a
secret:

<redacted-secret>
// Read from KV on every request — no redeploy needed
export async function getApiKey(env: Env): Promise<string> {
  const key = await env.SECRETS_KV.get("api_key_current");
  if (!key) throw new Error("api_key_current not found in KV");
  return key;
}
```

## The "mobile client token refresh during rotation" pattern

Mobile clients typically hold a short-lived JWT or API token issued by
the Worker. During a secrets rotation, the signing key changes; tokens
issued before rotation are valid but may be verified with the old key.

Dual-key verification window for JWT signing:

```typescript
import { verify } from "@tsndr/cloudflare-worker-jwt";

export async function verifyJwt(
  token: string,
  env: Env,
): Promise<boolean> {
  // Try current signing key first, fall back to outgoing key.
  const keys = [env.JWT_SECRET_V2, env.JWT_SECRET_V1].filter(Boolean);
  for (const secret of keys) {
    try {
      const ok = await verify(token, secret);
      if (ok) return true;
    } catch {
      // Try next key
    }
  }
  return false;
}
```

Mobile clients receive a 401 only after both old and new keys are
removed — which should not happen until all clients have refreshed.
Use the `exp` claim on JWTs to bound the dual-key window: if tokens
expire in 1 hour, the dual-key window need only last 1 hour.

## The "audit logging pattern" for rotation

Log every secret rotation event to a Cloudflare Logpush dataset or
Analytics Engine:

```typescript
// src/audit.ts
export async function logRotationEvent(
  env: Env,
  event: {
    action: "rotation_started" | "rotation_complete" | "key_revoked";
    keyName: string;
    initiator: string;
  },
): Promise<void> {
  await env.AUDIT_KV.put(
    `rotation:${Date.now()}:${event.keyName}`,
    JSON.stringify({ ...event, ts: new Date().toISOString() }),
    { expirationTtl: 60 * 60 * 24 * 90 }, // 90-day retention
  );
}
```

Trigger from your rotation script:

```bash
# Call the audit endpoint before and after rotation
curl -X POST https://api.example.com/internal/audit \
  -H "Authorization: Bearer $INTERNAL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action":"rotation_started","keyName":"API_KEY","initiator":"ci"}'
```

## Anti-patterns

- **Rotating by overwriting a single secret name.** The 30–60 s
  propagation window means concurrent Worker instances run with
  different keys. Always use versioned names.
- **Deleting the old secret before the upstream provider has
  revoked it.** Leaves a window where the Worker can't retry with
  a valid key if V2 fails.
- **Storing secrets in KV with no expiry.** Stale secrets accumulate;
  always set `expirationTtl` on KV secret values.
- **No audit log.** Without a log, you can't determine which key was
  active during a specific request window for incident analysis.
- **Rotating mobile JWT signing keys without a dual-key window.**
  Mobile clients are often offline for hours; a hard key swap logs
  them all out simultaneously.

## Gotchas

- `wrangler secret put` is interactive by default; use
  `echo "value" | wrangler secret put KEY_NAME` in CI to avoid
  TTY errors.
- Secrets are environment-scoped. Running `wrangler secret put
  API_KEY` without `--env` writes to the default (root) environment,
  not staging or production.
- Cloudflare does not provide a "list secret values" API — only
  names. Store a rotation timestamp in KV to know when each key
  was last rotated.
- After `wrangler secret delete`, the secret is gone globally within
  60 s. Do not delete until you are certain no Worker instance
  will need it.

## Verification

- **During rotation:** Hit the API from a mobile test device and
  confirm 0 auth errors over the 90-second propagation window.
- **Post-rotation:** `wrangler secret list --env production` shows
  `API_KEY_V2` only (after V1 deletion).
- **Audit:** `GET /internal/audit?prefix=rotation:` returns the
  `rotation_started` and `rotation_complete` events for this run.

## Related

- `documentation/categories/deploy/wrangler-deploy-github-actions-workers.md`
- `documentation/categories/deploy/canary-workers-gradual-traffic-split.md`
- `documentation/categories/deploy/gitops-secrets-management.md`
- `documentation/categories/deploy/ansible-vault-secrets.md`
- `documentation/categories/deploy/image-pull-secrets-rotation.md`

## Sources

- https://developers.cloudflare.com/workers/configuration/secrets/
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/
- https://developers.cloudflare.com/workers/observability/logpush/
