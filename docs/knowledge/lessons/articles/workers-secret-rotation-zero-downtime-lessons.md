# Zero-Downtime Secrets Rotation in Workers: Lessons Learned

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

We rotate API keys for our payment processor every 90 days per our security policy. The first rotation caused a 4-minute outage:

- `wrangler secret put PAYMENT_API_KEY` was called with the new key
- The payment processor portal revoked the old key immediately
- During propagation (~2 minutes), roughly half our Workers were still running the old secret
- Those requests failed with `401 Unauthorized`, which surfaced as checkout errors

We repeated a variation of this mistake when rotating a third-party webhook HMAC secret — this time causing silent dropped webhooks instead of user-visible errors.

This article documents the dual-version pattern and coordination strategy that now makes our rotations zero-downtime.

---

## Context

`wrangler secret put` pushes a new secret value to Cloudflare. The value is **encrypted at rest** and **injected into Worker processes at startup**. This means:

- Workers already running at the time of the `secret put` continue to use the OLD secret until the next cold start or until Cloudflare propagates the update to running isolates.
- Propagation is **eventually consistent** and takes **30 seconds to 3 minutes** in our observation across different regions and traffic levels.
- There is no Cloudflare-provided API to confirm that all running Workers have received the new secret — you infer it from your own metrics.
- Secrets are scoped to a Worker, not shared across Workers. Rotating a secret used by multiple Workers requires updating each Worker independently.

---

## Solution

### 1. Dual-version secret pattern

Instead of a single `PAYMENT_API_KEY` secret, we carry two: `PAYMENT_API_KEY` and `PAYMENT_API_KEY_PREVIOUS`. During a rotation window, the Worker accepts both and attempts the current key first, falling back to the previous.

```typescript
// workers/src/payment-client.ts

interface Env {
  PAYMENT_API_KEY: string;          // current (new) key
  PAYMENT_API_KEY_PREVIOUS: string;  // previous (old) key — kept during rotation window
}

interface PaymentResult {
  transactionId: string;
  status: 'success' | 'failed';
}

export async function chargeCard(
  env: Env,
  amount: number,
  token: string,
): Promise<PaymentResult> {
  // Try current key first
  try {
    return await attemptCharge(env.PAYMENT_API_KEY, amount, token);
  } catch (err) {
    if (!isAuthError(err)) throw err; // non-auth errors bubble up immediately

    // On auth failure, try the previous key (rotation may be in progress)
    console.warn('Current payment key rejected, trying previous key (rotation in progress?)');
    try {
      return await attemptCharge(env.PAYMENT_API_KEY_PREVIOUS, amount, token);
    } catch (fallbackErr) {
      if (!isAuthError(fallbackErr)) throw fallbackErr;
      // Both keys failed — propagation may not be complete or keys are wrong
      throw new Error('Payment auth failed with both current and previous key');
    }
  }
}

async function attemptCharge(
  apiKey: string,
  amount: number,
  token: string,
): Promise<PaymentResult> {
  const response = await fetch('https://api.payment-processor.example.com/v1/charges', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ amount, source: token }),
  });

  if (response.status === 401 || response.status === 403) {
    throw new AuthError(`Payment API returned ${response.status}`);
  }

  if (!response.ok) {
    throw new Error(`Payment API error: ${response.status}`);
  }

  return response.json<PaymentResult>();
}

class AuthError extends Error {
  readonly isAuthError = true;
}

function isAuthError(err: unknown): err is AuthError {
  return err instanceof AuthError;
}
```

### 2. Rotation procedure script

```bash
#!/usr/bin/env bash
# scripts/rotate-payment-key.sh
# Run this script from your CI/CD pipeline, NOT interactively with the key in the argument.

set -euo pipefail

WORKER_NAMES=("api-worker" "webhook-worker" "cron-worker") # all workers sharing this secret
NEW_KEY="${NEW_PAYMENT_API_KEY:?NEW_PAYMENT_API_KEY environment variable must be set}"
OLD_KEY="${OLD_PAYMENT_API_KEY:?OLD_PAYMENT_API_KEY environment variable must be set}"

echo "Step 1: Set previous key to current old key across all workers"
for worker in "${WORKER_NAMES[@]}"; do
  echo "$OLD_KEY" | npx wrangler secret put PAYMENT_API_KEY_PREVIOUS --name "$worker"
done

echo "Step 2: Wait for PREVIOUS key propagation"
sleep 90  # 90s is conservative; adjust based on your observed propagation time

echo "Step 3: Activate new key in payment processor portal (manual step)"
echo "Register new key in payment processor, keep old key ACTIVE for now."
read -rp "Press ENTER when new key is registered in the payment processor portal: "

echo "Step 4: Push new key to all workers"
for worker in "${WORKER_NAMES[@]}"; do
  echo "$NEW_KEY" | npx wrangler secret put PAYMENT_API_KEY --name "$worker"
done

echo "Step 5: Wait for new key propagation"
sleep 120

echo "Step 6: Verify auth success rate in your monitoring dashboard."
read -rp "Auth error rate < 0.1%? (y/n): " confirm
if [[ "$confirm" != "y" ]]; then
  echo "Aborting — check logs before revoking old key."
  exit 1
fi

echo "Step 7: Revoke old key in payment processor portal (manual step)"
read -rp "Press ENTER when old key is revoked in the payment processor portal: "

echo "Rotation complete."
```

### 3. Webhook HMAC rotation — accept both signatures

For HMAC-signed webhooks, implement a two-signature window:

```typescript
// workers/src/webhook-verifier.ts

interface Env {
  WEBHOOK_SECRET: string;          // current
  WEBHOOK_SECRET_PREVIOUS: string;  // previous (kept during rotation)
}

export async function verifyWebhookSignature(
  env: Env,
  request: Request,
): Promise<boolean> {
  const signature = request.headers.get('x-signature-sha256');
  if (!signature) return false;

  const body = await request.arrayBuffer();

  // Try current secret first
  const currentValid = await checkHmac(env.WEBHOOK_SECRET, body, signature);
  if (currentValid) return true;

  // Fall back to previous secret during rotation window
  const previousValid = await checkHmac(env.WEBHOOK_SECRET_PREVIOUS, body, signature);
  if (previousValid) {
    console.warn('Webhook verified with PREVIOUS secret — rotation may be in progress');
    return true;
  }

  return false;
}

async function checkHmac(
  secret: string,
  body: ArrayBuffer,
  expectedSignature: string,
): Promise<boolean> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );

  const signatureBuffer = await crypto.subtle.sign('HMAC', key, body);
  const computedHex = Array.from(new Uint8Array(signatureBuffer))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');

  // Use timing-safe comparison
  const expected = expectedSignature.replace(/^sha256=/, '');
  return timingSafeEqual(computedHex, expected);
}

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}
```

### 4. Monitoring for rotation success

```typescript
// workers/src/auth-metrics.ts

interface AuthAttempt {
  keyVersion: 'current' | 'previous' | 'failed';
  service: string;
  ts: number;
}

export function recordAuthAttempt(
  ctx: ExecutionContext,
  attempt: Omit<AuthAttempt, 'ts'>,
): void {
  // Emit to Workers Analytics Engine or a logging endpoint
  ctx.waitUntil(
    fetch('https://metrics.internal/auth-attempt', {
      method: 'POST',
      body: JSON.stringify({ ...attempt, ts: Date.now() }),
    }).catch(() => { /* fire and forget */ }),
  );
}
```

A rotation is considered complete when `keyVersion: 'previous'` events drop to zero for 10 consecutive minutes.

---

## Implementation Details

### Propagation delay by region

In our testing across ~30 deployments:

| Scenario | P50 propagation | P95 propagation |
|----------|----------------|----------------|
| Low-traffic Worker (<100 rps) | 45 s | 90 s |
| High-traffic Worker (>1000 rps) | 20 s | 60 s |
| Multi-region, Workers in 10+ PoPs | 60 s | 150 s |

We use 120 seconds as our standard wait after a `wrangler secret put`.

### Multi-Worker coordination

When a secret is shared across several Workers (as in a microservice mesh), update them in this order:

1. All **consumer** Workers (those that validate the secret, e.g., webhook receivers) — update `PREVIOUS` first.
2. Wait for propagation.
3. All **producer** Workers (those that sign or present the secret) — switch to `CURRENT`.
4. Wait and verify.
5. Revoke old secret at the provider.

### Rotation runbook checklist

```
[ ] Create new secret at external provider (do not revoke old yet)
[ ] Set WEBHOOK_SECRET_PREVIOUS = current value across all consumers
[ ] Wait 120 seconds
[ ] Set WEBHOOK_SECRET = new value across all Workers
[ ] Wait 120 seconds
[ ] Check auth_attempt metric: previous_key_used = 0 for 10 min
[ ] Revoke old secret at external provider
[ ] Remove WEBHOOK_SECRET_PREVIOUS values (or set to placeholder)
[ ] Record rotation date and next rotation date in runbook
```

---

## Anti-patterns

- **Rotating key and revoking old key simultaneously**: the propagation gap guarantees an outage. Always keep the old key valid at the provider until propagation is confirmed complete.
- **Using a single secret slot**: with only one slot, there is no safe way to carry the previous value. Always provision `_PREVIOUS` slots from the start.
- **Manual key rotation without a script**: typing `wrangler secret put` interactively is error-prone under incident pressure. The rotation script should be version-controlled and tested.
- **Not monitoring auth success rate during rotation**: you cannot know propagation is complete without metrics. Flying blind leads to premature revocation.
- **Storing secrets in `wrangler.toml` vars**: `[vars]` entries are plaintext in your config file and visible in the Cloudflare dashboard. Use `wrangler secret put` for all sensitive values.

---

## Gotchas

- `wrangler secret put` does not return a confirmation that all Workers have received the new value. The CLI success message means the secret was stored, not propagated.
- If a Worker has never been deployed with a `_PREVIOUS` secret binding, accessing `env.PAYMENT_API_KEY_PREVIOUS` returns `undefined` (not an empty string). Guard against this:
  ```typescript
  const previousKey = env.PAYMENT_API_KEY_PREVIOUS ?? '';
  if (previousKey) { /* attempt fallback */ }
  ```
- Secrets are **per-environment** in Wrangler. Rotating the production secret while inadvertently targeting the staging Worker is a real risk with manual CLI commands. The rotation script must explicitly target each environment.
- After revoking the old key at the provider, leave the `_PREVIOUS` secret in place with a dummy value for at least 24 hours before removing the binding — removing a binding requires a redeploy, and any in-flight request that tries to read it during a hot reload could encounter a missing environment variable.
- Workers deployed via `wrangler deploy --dry-run` do not propagate secrets. A dry run only validates the bundle.

---

## Verification

```typescript
// tests/webhook-verifier.test.ts
import { describe, it, expect } from 'vitest';
import { verifyWebhookSignature } from '../src/webhook-verifier';

const CURRENT_SECRET = 'new-secret-value';
const PREVIOUS_SECRET = 'old-secret-value';

function makeEnv(current: string, previous: string) {
  return { WEBHOOK_SECRET: current, WEBHOOK_SECRET_PREVIOUS: previous };
}

async function makeSignedRequest(secret: string, body: string): Promise<Request> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(body));
  const hexSig = Array.from(new Uint8Array(sig)).map(b => b.toString(16).padStart(2, '0')).join('');
  return new Request('https://worker.example.com/webhook', {
    method: 'POST',
    headers: { 'x-signature-sha256': `sha256=${hexSig}` },
    body,
  });
}

describe('verifyWebhookSignature', () => {
  it('accepts a request signed with the current secret', async () => {
    const req = await makeSignedRequest(CURRENT_SECRET, '{"event":"charge.success"}');
    expect(await verifyWebhookSignature(makeEnv(CURRENT_SECRET, PREVIOUS_SECRET), req)).toBe(true);
  });

  it('accepts a request signed with the PREVIOUS secret during rotation', async () => {
    const req = await makeSignedRequest(PREVIOUS_SECRET, '{"event":"charge.success"}');
    expect(await verifyWebhookSignature(makeEnv(CURRENT_SECRET, PREVIOUS_SECRET), req)).toBe(true);
  });

  it('rejects a request signed with an unknown secret', async () => {
    const req = await makeSignedRequest('attacker-secret', '{"event":"charge.success"}');
    expect(await verifyWebhookSignature(makeEnv(CURRENT_SECRET, PREVIOUS_SECRET), req)).toBe(false);
  });
});
```

---

## Related

- `documentation/docs/policies/lessons/workers-cold-start-latency-lessons.md`
- `documentation/docs/policies/lessons/email-routing-deliverability-lessons.md`
- `documentation/docs/policies/lessons/workers-durable-objects-storage-lessons.md`

---

## Sources

- Cloudflare Workers secrets: https://developers.cloudflare.com/workers/configuration/secrets/
- wrangler secret put: https://developers.cloudflare.com/workers/wrangler/commands/#secret
- Workers environment variables: https://developers.cloudflare.com/workers/configuration/environment-variables/
- Web Crypto API (SubtleCrypto): https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
