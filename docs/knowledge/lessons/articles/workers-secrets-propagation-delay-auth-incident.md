# Workers Secrets Propagation Delay Causing Intermittent Auth Failures

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

After rotating a JWT signing secret via `wrangler secret put JWT_SECRET`, our API Workers
began returning intermittent `401 Unauthorized` errors. Approximately 15–20 % of requests
failed for roughly 35 minutes after the rotation. The symptom was non-deterministic: the
same client, making identical requests seconds apart, would receive 200 then 401 then 200.
There was no code deployment; the only change was the secret rotation.

## Context

Cloudflare Workers Secrets are stored encrypted in Cloudflare's infrastructure and
propagated to edge PoPs via an eventually-consistent distribution pipeline. When a secret
is updated via `wrangler secret put` or the Cloudflare REST API, the new value does not
become simultaneously available at all PoPs worldwide. Propagation typically completes
within minutes but can take up to 60 seconds per PoP region under normal conditions and
longer under infrastructure load.

During the propagation window, some PoPs serve requests with the **old** secret value and
some serve requests with the **new** secret value. If the secret is used as a
**symmetric signing key** (HMAC or a symmetric JWT algorithm such as HS256), tokens
signed with the old key will fail verification on PoPs that have already received the
new key — and vice versa. This creates a window where valid user tokens are rejected.

We rotated without any overlap strategy, invalidating all active user sessions.

---

## Timeline

| UTC | Event |
|-----|-------|
| 16:00 | Security team requests emergency JWT secret rotation after credential scan alert |
| 16:02 | `wrangler secret put JWT_SECRET --env production` completes; CLI returns success |
| 16:03 | First `401` errors appear in logs across multiple PoPs |
| 16:07 | PagerDuty fires: auth failure rate 17 % |
| 16:12 | Engineers confirm no code deploy; begin investigating secret propagation |
| 16:22 | Decision: accept 401s until propagation completes rather than roll back |
| 16:37 | 401 error rate falls to < 0.1 %; propagation confirmed complete |
| 16:38 | Incident closed; 401s caused ~4,200 user session invalidations |

---

## Why Symmetric Keys Are Dangerous to Rotate Live

With HS256 (HMAC-SHA256), the same secret is used to both sign and verify tokens. There
is only one key at any given time. When that key changes:

- PoPs with the **new** key reject tokens signed with the **old** key ✗
- PoPs with the **old** key reject tokens signed with the **new** key ✗

The overlap window cannot be controlled by the operator — it is governed by Cloudflare's
propagation infrastructure.

Asymmetric keys (RS256, ES256) allow a **key ID (`kid`)** rotation strategy: publish the
new public key alongside the old one in a JWKS endpoint, and Workers verify against the
published key set. Tokens signed with the old private key continue to verify against the
old public key during the transition.

---

## Fix A: Asymmetric JWT with JWKS Rotation (Preferred)

```typescript
// auth-worker.ts — verify JWTs using a JWKS endpoint stored in KV
import { importJWK, jwtVerify, createRemoteJWKSet } from "jose"; // bundled

const JWKS_CACHE_TTL = 300; // 5 minutes

export async function verifyToken(
  token: string,
  env: Env
): Promise<boolean> {
  const cached = await env.KV.get("jwks:current", "json") as JsonWebKeySet | null;
  const jwks = cached ?? await fetchAndCacheJWKS(env);

  for (const key of jwks.keys) {
    try {
      const publicKey = await importJWK(key);
      await jwtVerify(token, publicKey, { algorithms: ["ES256"] });
      return true;
    } catch {
      // Try next key — support both old and new key during rotation
    }
  }
  return false;
}

async function fetchAndCacheJWKS(env: Env): Promise<JsonWebKeySet> {
  // JWKS_URL is a Workers Secret pointing to your key server / R2-hosted JSON
  const res  = await fetch(env.JWKS_URL);
  const jwks = await res.json<JsonWebKeySet>();
  await env.KV.put("jwks:current", JSON.stringify(jwks), {
    expirationTtl: JWKS_CACHE_TTL,
  });
  return jwks;
}
```

**Rotation procedure with JWKS:**

1. Generate new ES256 key pair.
2. Add the **new public key** to the JWKS alongside the **old public key** (both active).
3. Publish the updated JWKS to R2 / key server.
4. Update `wrangler secret put JWT_SIGNING_KEY_PRIVATE` with the new private key.
5. Wait for Workers to propagate (5 minutes).
6. All new tokens are signed with the new private key; old tokens still verify against
   the old public key in the JWKS.
7. After token TTL expires (e.g. 1 hour), remove the old public key from the JWKS.

---

## Fix B: Dual-Secret Overlap Window for Symmetric Rotation (Fallback)

If asymmetric keys are not feasible, use a two-slot secret strategy:

```typescript
// Verify against CURRENT and PREVIOUS symmetric secrets
export async function verifySymmetric(
  token: string,
  env: Env
): Promise<boolean> {
  const secrets = [env.JWT_SECRET, env.JWT_SECRET_PREV].filter(Boolean);

  for (const secret of secrets) {
    try {
      const encoder = new TextEncoder();
      const key = await crypto.subtle.importKey(
        "raw", encoder.encode(secret),
        { name: "HMAC", hash: "SHA-256" },
        false, ["verify"]
      );
      // ... verify HMAC signature against token
      return true;
    } catch {
      // Try previous secret
    }
  }
  return false;
}
```

**Rotation procedure with dual-slot:**

1. `wrangler secret put JWT_SECRET_PREV` — set it to the current value of `JWT_SECRET`.
2. `wrangler secret put JWT_SECRET` — set it to the new secret.
3. Wait 5 minutes for both secrets to propagate.
4. All PoPs now accept tokens signed with either the old or new secret.
5. After token TTL + propagation window, clear `JWT_SECRET_PREV`.

---

## Anti-patterns

- Rotating a symmetric signing key by simply overwriting it without an overlap window or
  dual-slot strategy.
- Assuming `wrangler secret put` is instantaneously globally consistent — it is
  eventually consistent.
- Not notifying on-call before rotating secrets so they can monitor error rates
  immediately after the rotation.
- Rotating JWT secrets without first calculating the active token TTL; if tokens live for
  24 hours, users will hit failures for the entire propagation window plus the residual
  token lifetime.

---

## Gotchas

- `wrangler secret put` returns success when Cloudflare accepts the new secret value,
  **not** when it has propagated to all PoPs. There is no CLI flag to block until
  propagation is complete.
- Worker instances that are actively handling long-lived WebSocket connections may not
  pick up the new secret until the connection is re-established or the Worker is
  re-invoked for a new request that triggers a new isolate.
- Secrets are visible to all environments that share the script unless you use `--env`
  to scope them; rotating in production may inadvertently affect preview/staging if your
  environments share a script name.
- The Cloudflare dashboard and API both allow listing secret names but never return secret
  values; you cannot compare old and new values to verify a rotation succeeded.

---

## Verification

After any secret rotation:

1. Monitor the `401` error rate in Analytics Engine for at least 10 minutes post-rotation.
2. Query `cf.colo` breakdown of `401`s — if a specific PoP accounts for disproportionate
   `401`s, it likely has not yet received the new secret.
3. Confirm `JWT_SECRET_PREV` is cleared after the overlap window:
   `wrangler secret list --env production` — `JWT_SECRET_PREV` must not appear after TTL.
4. Run a synthetic monitor (e.g. Cloudflare Workers Observability ping) from at least
   5 PoPs immediately after rotation to detect regional divergence.

---

## Related

- `kv-ttl-expiry-race-condition-session-logout-incident.md`
- `never-store-secrets-in-env-files.md`
- `rotate-credentials-after-every-breach.md`
- `workers-binding-version-drift-production-incident.md`
- `certificate-expiry-outage.md`

---

## Sources

- Cloudflare Docs — Workers Secrets: https://developers.cloudflare.com/workers/configuration/secrets/
- JOSE specification — JSON Web Key Sets: https://www.rfc-editor.org/rfc/rfc7517
- Cloudflare Docs — `wrangler secret`: https://developers.cloudflare.com/workers/wrangler/commands/#secret
- Internal incident ticket INC-2026-0302
- Internal security runbook SEC-RUNBOOK-JWT-ROTATION
