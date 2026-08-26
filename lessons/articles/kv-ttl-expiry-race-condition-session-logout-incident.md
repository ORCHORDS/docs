# KV TTL Expiry Race Condition Session Logout Incident

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project users began reporting intermittent, unexpected logouts while actively using the app. Sessions appeared valid (JWT not expired, refresh token present) but API calls returned HTTP 401 `session_not_found`. The logouts occurred unpredictably — some users were logged out mid-conversation, others after being idle for a few minutes. The issue was not reproducible on demand and appeared more frequently on mobile clients with background refresh behaviour.

## Context

example project stores session state in Cloudflare KV under the key `session:{sessionId}` with a TTL equal to the JWT access token lifetime (15 minutes). A refresh Worker extends the TTL on each successful token refresh. A race condition emerged between the KV TTL expiry and the refresh request: when a client sent a refresh request within the last few seconds of the TTL window, the KV read in the auth Worker would return `null` (key expired) before the refresh Worker could extend it, causing the auth Worker to treat the session as invalid and respond 401.

## Timeline

- **2026-08-18** — example project migrates from in-memory Durable Object session cache to KV-backed sessions to reduce DO costs.
- **2026-08-19 10:00 UTC** — First user reports of unexpected logouts filed in support.
- **2026-08-19 10:30 UTC** — Support team escalates; initially attributed to "token bugs" from the migration.
- **2026-08-19 14:00 UTC** — Engineering investigates: JWT tokens are valid, refresh tokens are not revoked, but KV key is absent at the moment of the 401.
- **2026-08-19 15:30 UTC** — Timeline correlation: all logout events occur 14–16 seconds before or after a 15-minute boundary. Race condition hypothesis formed.
- **2026-08-19 17:00 UTC** — Confirmed: KV TTL window is exactly 15 minutes; auth middleware reads KV before the refresh path can extend TTL; ~2-second eventual consistency propagation window widens the race.
- **2026-08-20 09:00 UTC** — Fix deployed: session TTL extended to 20 minutes; refresh threshold lowered to 10 minutes; auth middleware falls back to JWT validation when KV miss occurs within a grace window.
- **2026-08-20 09:30 UTC** — Logout incidents drop to zero; monitoring confirmed stable.

## Root Cause

**Race condition between KV TTL expiry and refresh request processing:**

```
Timeline view (T = seconds before session TTL boundary):

T-5s:  Client sends refresh request to /api/auth/refresh
T-4s:  Refresh Worker reads old session from KV → succeeds (key still exists)
T-3s:  Refresh Worker generates new access token + new refresh token
T-2s:  [KV TTL expires — key deleted from KV]
T-1s:  Refresh Worker writes new session to KV with new 15min TTL → succeeds
T+0s:  Client receives new access token, sends first API call
T+0s:  Auth Worker reads KV for session validation
T+0s:  KV returns null (KV eventual consistency: write at T-1s not yet visible in all PoPs)
T+0s:  Auth Worker returns 401 "session_not_found"
T+2s:  KV write from T-1s becomes globally consistent — too late
```

```typescript
// workers/auth-middleware.ts — BUGGY VERSION

async function validateSession(
  sessionId: string,
  env: Env
): Promise<Session | null> {
  const raw = await env.SESSIONS.get(`session:${sessionId}`);
  // BUG: returns null for two reasons that are NOT equivalent:
  //   1. Session genuinely expired (user should be logged out)
  //   2. Session was just refreshed but KV write not yet consistent
  if (raw === null) {
    return null; // Triggers 401 — wrong for case 2
  }
  return JSON.parse(raw) as Session;
}
```

```typescript
// workers/refresh.ts — BUGGY VERSION (compounding problem)

async function refreshSession(refreshToken: string, env: Env): Promise<TokenPair> {
  const session = await validateRefreshToken(refreshToken, env);
  const newAccessToken = issueAccessToken(session.userId);
  const newRefreshToken = issueRefreshToken(session.userId);

  // BUG: writes new session with identical TTL (15 minutes from now)
  // Should be longer to provide a grace buffer
  await env.SESSIONS.put(
    `session:${session.id}`,
    JSON.stringify({ ...session, accessToken: <redacted-secret> }),
    { expirationTtl: 900 } // 15 minutes — same as access token lifetime
  );

  // BUG: does not invalidate old refresh token immediately;
  // does not write a "refresh in progress" sentinel to prevent parallel refreshes
  return { accessToken: <redacted-secret> refreshToken: newRefreshToken };
}
```

## Impact

- **Duration:** ~36 hours between first report and fix deployment
- **Users affected:** ~1,400 users experienced at least one unexpected logout
- **Mobile clients disproportionately affected:** Background refresh on iOS/Android fires near the token boundary by design
- **Logout frequency:** ~0.3% of all auth validation calls returned 401 erroneously
- **Data loss:** None — no session data corrupted, only interrupted
- **User trust:** Disproportionate: mobile users interpreted logouts as account security events

## Fix

```typescript
// workers/auth-middleware.ts — FIXED VERSION

const KV_CONSISTENCY_GRACE_SECONDS = 30;

async function validateSession(
  sessionId: string,
  jwtIssuedAt: number, // from JWT iat claim
  env: Env
): Promise<Session | null> {
  const raw = await env.SESSIONS.get(`session:${sessionId}`);

  if (raw !== null) {
    return JSON.parse(raw) as Session;
  }

  // KV miss: check if this is likely a consistency race
  const secondsSinceIssue = Math.floor(Date.now() / 1000) - jwtIssuedAt;
  if (secondsSinceIssue < KV_CONSISTENCY_GRACE_SECONDS) {
    // JWT was issued very recently — this is likely a KV consistency lag, not expiry.
    // Trust the JWT signature validation (already done upstream) and allow the request.
    // Log for monitoring but do not reject.
    console.warn("KV miss within grace window — trusting JWT", {
      sessionId,
      secondsSinceIssue,
    });
    return {
      id: sessionId,
      // Reconstruct minimal session from JWT claims — enough for this request
      userId: extractUserId(sessionId), // derived from sessionId prefix
      gracePeriod: true,
    } as Session;
  }

  // KV miss outside grace window: genuine expiry or invalid session
  return null;
}
```

```typescript
// workers/refresh.ts — FIXED VERSION

const SESSION_TTL_SECONDS = 1200;     // 20 minutes (was 15)
const REFRESH_THRESHOLD_SECONDS = 600; // Refresh when < 10 minutes remain (was < 2 min implicit)

async function refreshSession(refreshToken: string, env: Env): Promise<TokenPair> {
  const session = await validateRefreshToken(refreshToken, env);

  // Write refresh-in-progress sentinel to prevent parallel refresh storms
  const lockKey = `session-refresh-lock:${session.id}`;
  const existing = await env.SESSIONS.get(lockKey);
  if (existing) {
    throw new AppError(429, "refresh_in_progress");
  }
  await env.SESSIONS.put(lockKey, "1", { expirationTtl: 10 });

  const newAccessToken = issueAccessToken(session.userId);
  const newRefreshToken = issueRefreshToken(session.userId);

  // Extend TTL well beyond access token lifetime to cover consistency windows
  await env.SESSIONS.put(
    `session:${session.id}`,
    JSON.stringify({
      ...session,
      accessToken: <redacted-secret>
      refreshedAt: Date.now(),
    }),
    { expirationTtl: SESSION_TTL_SECONDS }
  );

  // Revoke old refresh token
  await env.SESSIONS.put(
    `rt-revoked:${refreshToken}`,
    "1",
    { expirationTtl: SESSION_TTL_SECONDS }
  );

  await env.SESSIONS.delete(lockKey);
  return { accessToken: <redacted-secret> refreshToken: newRefreshToken };
}
```

```typescript
// Client-side fix: proactive refresh before token boundary
// Refresh when < 5 minutes remain, not at expiry
const REFRESH_BUFFER_MS = 5 * 60 * 1000;

function scheduleRefresh(accessToken: string) {
  const { exp } = decodeJwt(accessToken);
  const expiresAt = exp * 1000;
  const refreshAt = expiresAt - REFRESH_BUFFER_MS;
  const delay = Math.max(0, refreshAt - Date.now());
  setTimeout(() => performRefresh(), delay);
}
```

## Prevention

1. **KV session TTL set to 2× access token lifetime** — decouples KV expiry from JWT expiry, eliminating the tight race window.
2. **Consistency grace period** in auth middleware: KV miss within 30 seconds of JWT issue falls back to JWT signature trust.
3. **Client-side proactive refresh** at 5-minute buffer, not at expiry boundary.
4. **Refresh lock sentinel** in KV prevents parallel refresh storms from mobile clients.
5. **Alert** on `auth_kv_miss_within_grace_window_count` > 10/min — indicates KV consistency lag worse than expected.
6. **Load test** simulating refresh-boundary behaviour added to CI integration suite.

## Anti-patterns

- Setting KV TTL equal to JWT lifetime — creates a zero-margin race window.
- Treating KV miss and session expiry as identical failure modes.
- Not accounting for KV eventual consistency propagation in session validation logic.
- Relying on client-initiated refresh at token expiry rather than ahead of it.
- Not having a refresh lock mechanism — parallel refreshes from mobile background tasks compound the race.
- Using KV as a strict authoritative session store without a fallback to the JWT signature for recent tokens.

## Gotchas

- Cloudflare KV is eventually consistent across PoPs — writes take up to 60 seconds to propagate globally in the worst case, though typically ~1-2 seconds. Auth paths that span multiple PoPs (e.g., CDN edge → origin Worker) are susceptible.
- KV `get()` after a `put()` in the same Worker invocation within the same PoP sees the updated value, but a different Worker in a different PoP may not.
- KV TTL is expressed in seconds and cannot be sub-second. A key expires at the boundary, not before it.
- Using `expirationTtl` vs `expiration` (absolute Unix timestamp) matters: `expirationTtl` is relative to the write time; `expiration` is absolute. Using `expiration` derived from `Date.now()` may create a race if the Worker clock differs from KV's clock.
- KV does not support atomic compare-and-swap — the refresh lock sentinel pattern used above has a small TOCTOU window; for production-critical session management, Durable Objects provide stronger consistency guarantees.

## Verification

```bash
# Confirm session TTL is 20 minutes (1200s) in production
wrangler kv key get --namespace-id=<SESSIONS_NS_ID> "session:test-id" --metadata
# Look for "expiration" field ~1200s in the future

# Load test: simulate refresh at T-5s before expiry
# Confirm auth calls succeed immediately after refresh with no 401
npx vitest run test/integration/refresh-race.test.ts

# Monitor for 24h post-fix
# Alert: auth_unexpected_401_rate < 0.01%
```

## Related

- `kv-cold-start-mobile-latency-spike-postmortem.md`
- `kv-write-rate-limit-exceeded-postmortem.md`
- `kv-read-costs-capacity-planning-retrospective.md`
- `eventual-consistency-surprises-clients.md`
- `cache-invalidation-is-harder-than-caching.md`
- `idempotency-keys-for-all-payment-calls.md`

## Sources

- https://developers.cloudflare.com/kv/reference/consistency/
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/#expiration
- https://developers.cloudflare.com/kv/api/read-key-value-pairs/
- https://developers.cloudflare.com/workers/runtime-apis/kv/
- https://developers.cloudflare.com/durable-objects/best-practices/in-memory-state/
