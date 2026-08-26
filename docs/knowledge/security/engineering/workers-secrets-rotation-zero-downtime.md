# Zero-Downtime Secret Rotation for Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to rotate a signing secret, API key, or encryption key used by a Cloudflare Worker without dropping live traffic or requiring a maintenance window. A single atomic swap of the secret causes a window during which some requests carry tokens signed with the old secret and others carry tokens signed with the new secret, causing authentication failures. The dual-secret pattern — maintaining both `SECRET_CURRENT` and `SECRET_PREVIOUS` as Worker bindings and falling back from current to previous during verification — provides a zero-downtime rotation path.

---

## Context

Cloudflare Worker secrets are bound as environment variables and are only updated at deploy time. Rotating a secret therefore requires a deploy; the dual-secret pattern turns this into a two-step deploy process that maintains continuity. In step one the old secret becomes `SECRET_PREVIOUS` and the new secret becomes `SECRET_CURRENT`. Clients still holding tokens or cookies signed with the old secret are verified against `SECRET_PREVIOUS` transparently. After a safe window (typically 48 hours, after which all old tokens have expired or been reissued) a second deploy removes `SECRET_PREVIOUS`. A Cron Trigger Worker checks whether `SECRET_PREVIOUS` is still being exercised after 48 hours and alerts if so, preventing the rotation from completing prematurely.

---

## Section 1 — Wrangler Config / Secret Bindings

```toml
# wrangler.toml
name            = "auth-worker"
main            = "src/index.ts"
compatibility_date = "2025-09-01"

# Cron for the rotation-staleness alert
[triggers]
crons = ["0 */6 * * *"]   # every 6 hours

[[kv_namespaces]]
binding = "ROTATION_KV"
id      = "<your-kv-namespace-id>"
# KV keys used:
#   rotation:start_ts        — Unix timestamp when rotation began
#   rotation:prev_use_count  — number of requests that matched SECRET_PREVIOUS
```

```bash
# How to set / update secrets (never store these in wrangler.toml)
# Step 0 — initial state (only current exists)
npx wrangler secret put SECRET_CURRENT

# Step 1 — start rotation: promote old current to previous, set new current
npx wrangler secret put SECRET_PREVIOUS   # paste value of the OLD SECRET_CURRENT
npx wrangler secret put SECRET_CURRENT    # paste the NEW secret
npx wrangler deploy

# Record rotation start time in KV
npx wrangler kv key put --binding ROTATION_KV rotation:start_ts "$(date +%s)"
npx wrangler kv key put --binding ROTATION_KV rotation:prev_use_count "0"

# Step 2 — after 48 h, verify prev_use_count is 0, then remove previous
npx wrangler secret delete SECRET_PREVIOUS
npx wrangler deploy
```

---

## Section 2 — Worker Implementation

```typescript
// src/hmac.ts  — HMAC-SHA256 sign/verify using Web Crypto

const ALGO = { name: 'HMAC', hash: 'SHA-256' } as const;

async function importHmacKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    ALGO,
    false,
    ['sign', 'verify'],
  );
}

export async function signPayload(payload: string, secret: string): Promise<string> {
  const key = await importHmacKey(secret);
  const sig = await crypto.subtle.sign(ALGO, key, new TextEncoder().encode(payload));
  return btoa(String.fromCharCode(...new Uint8Array(sig)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

export async function verifyPayload(
  payload: string,
  signature: string,
  secret: string,
): Promise<boolean> {
  try {
    const key = await importHmacKey(secret);
    // Reconstruct standard base64 from base64url
    const b64 = signature.replace(/-/g, '+').replace(/_/g, '/') +
      '='.repeat((4 - (signature.length % 4)) % 4);
    const sigBytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    return crypto.subtle.verify(ALGO, key, sigBytes, new TextEncoder().encode(payload));
  } catch {
    return false;
  }
}
```

```typescript
// src/index.ts
import { signPayload, verifyPayload } from './hmac';

export interface Env {
  SECRET_CURRENT: string;
  SECRET_PREVIOUS?: string;   // optional — absent after rotation completes
  ROTATION_KV: KVNamespace;
}

/**
 * Verify a signature against current secret first, then previous.
 * Returns which secret matched ('current' | 'previous' | null).
 */
async function verifyWithFallback(
  payload: string,
  signature: string,
  env: Env,
): Promise<'current' | 'previous' | null> {
  if (await verifyPayload(payload, signature, env.SECRET_CURRENT)) {
    return 'current';
  }
  if (env.SECRET_PREVIOUS && await verifyPayload(payload, signature, env.SECRET_PREVIOUS)) {
    return 'previous';
  }
  return null;
}

export default {
  // ── Scheduled handler: rotation staleness alert ──────────────────────────
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    if (!env.SECRET_PREVIOUS) return; // rotation already complete

    const startRaw = await env.ROTATION_KV.get('rotation:start_ts');
    if (!startRaw) return;

    const startTs = parseInt(startRaw, 10);
    const ageHours = (Date.now() / 1000 - startTs) / 3600;

    const prevCountRaw = await env.ROTATION_KV.get('rotation:prev_use_count');
    const prevCount = prevCountRaw ? parseInt(prevCountRaw, 10) : 0;

    if (ageHours >= 48 && prevCount > 0) {
      // Alert: SECRET_PREVIOUS is still being used after 48 hours.
      // In production, forward to your alerting system (PagerDuty, Slack, etc.)
      console.error(
        `[ROTATION ALERT] SECRET_PREVIOUS still matched ${prevCount} requests ` +
        `after ${ageHours.toFixed(1)} hours. Do NOT remove SECRET_PREVIOUS yet.`,
      );
    } else if (ageHours >= 48 && prevCount === 0) {
      console.log(
        `[ROTATION OK] No requests matched SECRET_PREVIOUS in ${ageHours.toFixed(1)} hours. ` +
        'Safe to run: wrangler secret delete SECRET_PREVIOUS && wrangler deploy',
      );
    }
  },

  // ── Fetch handler ────────────────────────────────────────────────────────
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // Issue a signed token (sign endpoint — demo only, add auth in production)
    if (url.pathname === '/sign' && request.method === 'POST') {
      const body = await request.text();
      const sig = await signPayload(body, env.SECRET_CURRENT);
      return new Response(JSON.stringify({ payload: body, signature: sig }), {
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Verify a signed token
    if (url.pathname === '/verify' && request.method === 'POST') {
      const { payload, signature } = await request.json<{ payload: string; signature: string }>();
      const matched = await verifyWithFallback(payload, signature, env);

      if (!matched) {
        return new Response('Invalid signature', { status: 401 });
      }

      // Track previous-secret usage for the rotation alert
      if (matched === 'previous') {
        ctx.waitUntil(
          env.ROTATION_KV.get('rotation:prev_use_count').then(async (raw) => {
            const count = raw ? parseInt(raw, 10) : 0;
            await env.ROTATION_KV.put('rotation:prev_use_count', String(count + 1));
          }),
        );
      }

      return new Response(JSON.stringify({ valid: true, matchedSecret: matched }), {
        headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

---

## Section 3 — Testing / Verification

```typescript
// test/rotation.test.ts
import { describe, it, expect } from 'vitest';
import { signPayload, verifyPayload } from '../src/hmac';

describe('HMAC sign/verify', () => {
  it('verifies a payload signed with the same secret', async () => {
    const secret = 'test-secret-1';
    const payload = 'hello world';
    const sig = await signPayload(payload, secret);
    expect(await verifyPayload(payload, sig, secret)).toBe(true);
  });

  it('rejects a payload verified with a different secret', async () => {
    const sig = await signPayload('data', 'secret-a');
    expect(await verifyPayload('data', sig, 'secret-b')).toBe(false);
  });

  it('rejects a tampered payload', async () => {
    const secret = 'secret';
    const sig = await signPayload('original', secret);
    expect(await verifyPayload('tampered', sig, secret)).toBe(false);
  });
});
```

```bash
# Rotation runbook verification

# 1. Sign a payload with the current Worker
SIG=$(curl -s -X POST https://auth-worker.<subdomain>.workers.dev/sign \
  -H 'Content-Type: text/plain' \
  --data 'my-payload' | jq -r .signature)

# 2. Verify it passes
curl -s -X POST https://auth-worker.<subdomain>.workers.dev/verify \
  -H 'Content-Type: application/json' \
  -d "{\"payload\":\"my-payload\",\"signature\":\"$SIG\"}" | jq

# 3. After rotation (step 1 deploy), verify old token still passes
curl -s -X POST https://auth-worker.<subdomain>.workers.dev/verify \
  -H 'Content-Type: application/json' \
  -d "{\"payload\":\"my-payload\",\"signature\":\"$SIG\"}" | jq
# Expect: {"valid":true,"matchedSecret":"previous"}

# 4. Check KV for previous-secret hit count after 48 h
npx wrangler kv key get --binding ROTATION_KV rotation:prev_use_count

# 5. If count is 0, remove the previous secret and redeploy
npx wrangler secret delete SECRET_PREVIOUS
npx wrangler deploy
```

---

## Anti-patterns

- **Swapping to the new secret in a single atomic deploy** — any in-flight requests carrying tokens signed with the old secret will immediately fail; always use the two-step dual-secret approach.
- **Removing `SECRET_PREVIOUS` before verifying it is no longer needed** — check the `prev_use_count` KV counter and allow at least one token TTL cycle (or 48 hours, whichever is longer) before removing.
- **Hard-coding secrets in `wrangler.toml`** — secrets committed to version control are permanently exposed; always use `wrangler secret put` which stores secrets encrypted in Cloudflare's vault.
- **Re-using the same secret across multiple Workers or environments** — a compromise in one service exposes all services; generate a unique secret per Worker and per environment.
- **Not tracking which secret matched** — without the `matchedSecret` field in the verify response and the KV counter, you have no signal for when it is safe to complete the rotation.

---

## Gotchas

- `wrangler secret put` requires interactive input (it prompts for the value to avoid shell history exposure); in CI pipelines pipe the value: `echo -n "$SECRET_VALUE" | npx wrangler secret put SECRET_CURRENT`.
- Worker secrets are scoped to the Worker name + account; a secret named `SECRET_CURRENT` in one Worker does not affect another Worker with the same name in a different account.
- The Cron Trigger `scheduled` handler and the `fetch` handler share the same `env` binding, so `SECRET_PREVIOUS` is `undefined` (not an empty string) when it has not been set — always guard with `if (env.SECRET_PREVIOUS)`.
- Cloudflare's secrets are encrypted at rest but are visible in plaintext to the Worker runtime; never log them or return them in responses.
- After `wrangler secret delete SECRET_PREVIOUS` the next deploy is required to propagate the removal to all PoPs; until the deploy completes some isolates may still have the old binding.

---

## Verification

```bash
# Confirm secrets are set (values are redacted by Cloudflare)
npx wrangler secret list

# Deploy and run the rotation runbook steps above
npx wrangler deploy

# Trigger the scheduled cron handler manually (Wrangler >= 3.x)
npx wrangler dev --test-scheduled
curl -X POST 'http://localhost:8787/__scheduled?cron=0+*%2F6+*+*+*'

# Unit tests
npx vitest run
```

---

## Related

- `workers-jwt-rs256-verification-webcrypto.md`
- `workers-ip-rate-limiting-kv-sliding-window.md`

---

## Sources

- Cloudflare Workers Secrets — https://developers.cloudflare.com/workers/configuration/secrets/
- Cloudflare Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
- NIST Guidelines for Cryptographic Key Management — https://csrc.nist.gov/publications/detail/sp/800-57-part-1/rev-5/final
- Zero-Downtime Deployments — https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
