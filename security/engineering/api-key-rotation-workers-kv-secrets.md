# api-key-rotation-workers-kv-secrets

**Issue:** Rotating third-party API keys used by Workers causes
mobile clients to receive 401/503 errors during the overlap
window when one key is deactivated before the other propagates
**Date:** 2026-08-22
**Author:** example.com
**Status:** documented — example project project (Workers, KV, Secrets)

## Symptom

After rotating the age-verification provider API key, a wave of
`401 Unauthorized` errors appears in Worker logs for 30–90
seconds. Mobile clients surface this as a failed age check
with no retry. Rolling back to the old key and re-rotating
succeeds, but the failure window repeats.

## Context

example project Workers call a third-party age-verification API and
an R2 presigned URL signing service. Both require API keys.
Cloudflare Workers have two mechanisms for storing secrets:
`wrangler secret put` (Cloudflare Secrets — environment
variable at deploy time) and Workers KV (runtime readable,
updatable without redeployment). The rotation strategy must
differ depending on which mechanism holds the key.

## Cloudflare Secrets vs Workers KV for API keys

```
+----------------------+-----------------+--------------------+
| Property             | CF Secrets      | Workers KV         |
+----------------------+-----------------+--------------------+
| Updated by           | wrangler deploy | KV API / Worker    |
| Propagation delay    | Full deployment | ~60 s (eventual)   |
| Readable at runtime  | env.MY_SECRET   | env.KV.get(key)    |
| Audit log            | Deploy log      | Custom (see below) |
| Dual-key overlap     | Requires deploy | Yes, natively      |
| Encrypted at rest    | Yes             | Yes                |
| Rotation automation  | CI/CD pipeline  | Cron Worker        |
+----------------------+-----------------+--------------------+
```

Use Cloudflare Secrets for static credentials that rotate
infrequently (once per quarter). Use Workers KV for credentials
that require zero-downtime overlap rotation (per-month or on
compromise) because KV allows the Worker to read multiple valid
keys simultaneously without redeployment.

## Dual-key overlap pattern in Workers KV

```ts
// KV schema for dual-key rotation
// keys: "api_key:primary" → { key, issued_at, expires_at }
//       "api_key:secondary" → { key, issued_at, expires_at }
//       "api_key:audit_log" → append-only JSON array (D1 instead)

// Worker — get active key with fallback
async function getApiKey(env: Env): Promise<string> {
  const primary = await env.KV.get<ApiKeyEntry>(
    "api_key:primary", "json"
  );
  if (primary && Date.now() < primary.expires_at) {
    return primary.key;
  }
  const secondary = await env.KV.get<ApiKeyEntry>(
    "api_key:secondary", "json"
  );
  if (secondary && Date.now() < secondary.expires_at) {
    return secondary.key;
  }
  throw new Error("No valid API key available");
}

// Rotation Worker (Cron Trigger) — zero-downtime swap
async function rotateApiKey(env: Env): Promise<void> {
  const newKey = await provisionNewKeyAtProvider(env);
  const now = Date.now();

  // Step 1: Write new key as secondary (primary still live)
  await env.KV.put("api_key:secondary", JSON.stringify({
    key: newKey,
    issued_at: now,
    expires_at: now + 90 * 24 * 60 * 60 * 1000, // 90 days
  }));

  // Step 2: Wait for KV to propagate (~60 s)
  await sleep(90_000);

  // Step 3: Promote secondary to primary
  await env.KV.put("api_key:primary", JSON.stringify({
    key: newKey,
    issued_at: now,
    expires_at: now + 90 * 24 * 60 * 60 * 1000,
  }));

  // Step 4: Wait again, then delete old primary from provider
  await sleep(90_000);
  const old = await env.KV.get<ApiKeyEntry>(
    "api_key:secondary", "json"
  );
  if (old) await revokeKeyAtProvider(old.key, env);
  await env.KV.delete("api_key:secondary");

  await logRotationEvent(env, { new_key_prefix: newKey.slice(0, 8) });
}
```

## Audit logging rotation events to D1

KV is not suitable for audit trails — keys can be overwritten
silently. Log all rotation events to D1 for compliance:

```sql
-- D1 schema
CREATE TABLE api_key_rotation_log (
  id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  event_type  TEXT NOT NULL,  -- 'provisioned','promoted','revoked'
  key_prefix  TEXT NOT NULL,  -- first 8 chars of key
  actor       TEXT NOT NULL,  -- 'cron_worker' or user email
  timestamp   TEXT NOT NULL DEFAULT (datetime('now')),
  metadata    TEXT            -- JSON blob
);
```

```ts
async function logRotationEvent(
  env: Env,
  data: { new_key_prefix: string; event?: string }
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO api_key_rotation_log
     (event_type, key_prefix, actor, metadata)
     VALUES (?, ?, ?, ?)`
  ).bind(
    data.event ?? "rotation_complete",
    data.new_key_prefix,
    "cron_worker",
    JSON.stringify({ timestamp: new Date().toISOString() })
  ).run();
}
```

## Mobile client graceful reauthentication

When the overlap window fails (both keys briefly invalid), the
Worker should return a structured error so the mobile client
can retry with exponential back-off rather than surfacing a
bare 401 to the user:

```ts
// Worker — age verification endpoint
export async function verifyAge(
  request: Request,
  env: Env
): Promise<Response> {
  let apiKey: string;
  try {
    apiKey = await getApiKey(env);
  } catch {
    // Both keys unavailable — signal retry-able error
    return Response.json(
      { error: "service_temporarily_unavailable", retryable: true },
      {
        status: 503,
        headers: {
          "Retry-After": "30",
          "X-example project-Error-Code": "AGE_VERIFY_UNAVAILABLE",
        },
      }
    );
  }
  // ... call provider
}
```

React Native client exponential back-off:

```ts
async function verifyAgeWithRetry(
  maxAttempts = 4
): Promise<AgeVerifyResult> {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const res = await fetch("/api/auth/age-verify", {
      method: "POST",
      headers: { Authorization: `Bearer ${await getAccessToken()}` },
    });
    if (res.ok) return res.json();
    const body = await res.json<{ retryable?: boolean }>();
    if (res.status === 503 && body.retryable && attempt < maxAttempts - 1) {
      const delay = 1000 * Math.pow(2, attempt); // 1s, 2s, 4s
      await new Promise((r) => setTimeout(r, delay));
      continue;
    }
    throw new Error(`Age verification failed: ${res.status}`);
  }
  throw new Error("Max retry attempts exceeded");
}
```

## Rotation runbook (zero-downtime)

```
T=0   Provision new key at third-party provider
T=0   Write new key to KV as "secondary"
T+90s Verify secondary key works: curl with new key → 200
T+90s Promote secondary → primary in KV
T+3m  Confirm zero 401s in Worker logs (Cloudflare Analytics)
T+3m  Revoke old key at provider
T+3m  Delete "secondary" KV entry
T+3m  Write D1 audit log entry with actor + key prefix
```

## Anti-patterns

- Storing the live API key in `wrangler.toml` as a `[vars]`
  entry — `vars` are not encrypted and appear in deploy logs
  and `wrangler.toml` committed to git.
- Rotating by deleting the old key first, then writing the new
  one — causes a downtime window of KV propagation delay.
- Using the same KV key name (`api_key`) and overwriting it in
  a single put — no overlap window; all in-flight requests using
  the cached KV value from the previous read will fail.
- Logging the full API key value to D1 or Workers logs — log
  only the prefix (first 8 chars) for correlation.
- Skipping the `Retry-After` header on 503 — mobile clients
  will retry immediately and amplify the error.

## Gotchas

- KV reads are eventually consistent with up to 60 s of lag
  in some regions. The 90 s sleep in the rotation Worker is
  a conservative estimate. In practice, test that KV reads
  from PoPs in US, EU, and APAC all see the new secondary
  key before promoting it to primary.
- Cloudflare Cron Triggers have a minimum interval of 1 minute.
  For rotation logic requiring sub-minute steps, use a self-
  chaining Durable Object or split into two Cron Workers with
  a KV flag to track rotation state.
- Workers KV `list()` by prefix is eventually consistent and
  may return stale keys. Always use explicit KV key names for
  the primary/secondary pattern rather than listing keys.
- Revoking a third-party key before confirming the new key
  works will lock out the Worker. Always test the new key via
  a dry-run request before revoking the old one.

## Verification

- Trigger the rotation Cron Worker manually via `wrangler cron`
  and monitor Worker logs for zero 401 errors during the run
- Query D1: `SELECT * FROM api_key_rotation_log ORDER BY
  timestamp DESC LIMIT 5` — confirm entry written
- After rotation, confirm old key is rejected at provider:
  `curl -H "Authorization: Bearer <old-key>" <provider>` → 401
- Send 100 requests to the age-verify endpoint during rotation
  window and confirm 0 non-retryable errors

## Related

- `security/cloudflare-access-service-token-rotation-and-emergency-revocation.md`
- `security/api-key-rotation-zero-downtime.md`
- `cloudflare/workers-kv-consistency-model.md`
- `cloudflare/workers-cron-triggers.md`
- `database/d1-audit-log-patterns.md`

## Sources

- https://developers.cloudflare.com/kv/api/
- https://developers.cloudflare.com/workers/configuration/secrets/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/d1/
- https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html
