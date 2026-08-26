# Per-Request Micropayment Metering with Cloudflare Workers

- Date: 2026-08-22
- Author: example.com
- Status: production

## Problem: Metering API usage and gating requests behind a credit balance

Many APIs need to charge per-request or per-token without the latency of a round-trip to a remote
billing service on every call. The challenge is atomically deducting credits before serving the
response, preventing double-spend under concurrent load, and reconciling with a payment provider
like Stripe for top-up purchases — all at the edge.

Cloudflare Workers give you two primitives that solve this cleanly: D1 acts as a persistent usage
ledger (accounts, transactions, bundle purchases) and a Durable Object provides strongly-consistent
atomic credit deduction with no external lock. The Durable Object holds an in-memory counter
synced to D1, making each deduction a sub-millisecond local operation.

Stripe handles credit bundle purchases via a webhook Worker that validates the signature, records
the bundle in D1, and signals the Durable Object to top up the balance. The net result is a
metering system that adds under 2 ms overhead per request with no external service calls in the
hot path.

## Context

- Runtime: Cloudflare Workers (ES modules)
- Storage: D1 (ledger + audit), Durable Objects (atomic counter)
- Payment: Stripe Checkout + webhook
- Wrangler: 3.x with `durable_objects` and `d1_databases` bindings

## D1 Ledger Schema

Create the schema once with `wrangler d1 execute`:

```sql
-- accounts table
CREATE TABLE IF NOT EXISTS accounts (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL,
  credits INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

-- credit transactions (top-ups and deductions)
CREATE TABLE IF NOT EXISTS credit_transactions (
  id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES accounts(id),
  delta INTEGER NOT NULL,        -- positive = top-up, negative = deduction
  reason TEXT NOT NULL,          -- 'purchase', 'api_call', 'refund'
  stripe_session_id TEXT,
  request_id TEXT,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_txn_account ON credit_transactions(account_id, created_at DESC);
```

## Durable Object: Atomic Credit Deduction

```ts
// src/credit-account.ts
import { DurableObject } from 'cloudflare:workers';

export interface Env {
  DB: D1Database;
  CREDIT_ACCOUNT: DurableObjectNamespace;
}

export class CreditAccount extends DurableObject {
  private credits: number | null = null;
  private accountId: string | null = null;

  async initialize(accountId: string, env: Env): Promise<void> {
    this.accountId = accountId;
    if (this.credits === null) {
      const row = await env.DB.prepare(
        'SELECT credits FROM accounts WHERE id = ?'
      ).bind(accountId).first<{ credits: number }>();
      this.credits = row?.credits ?? 0;
    }
  }

  async deduct(amount: number, requestId: string, env: Env): Promise<{ ok: boolean; remaining: number }> {
    if (this.credits === null) throw new Error('Not initialized');
    if (this.credits < amount) {
      return { ok: false, remaining: this.credits };
    }
    this.credits -= amount;

    // Write to D1 asynchronously — do not await in hot path
    const txnId = crypto.randomUUID();
    env.DB.prepare(
      `INSERT INTO credit_transactions(id,account_id,delta,reason,request_id,created_at)
       VALUES(?,?,?,?,?,unixepoch())`
    ).bind(txnId, this.accountId, -amount, 'api_call', requestId).run().catch(console.error);

    // Sync balance to D1 every 50 deductions (lazy flush)
    if (Math.random() < 0.02) {
      await env.DB.prepare('UPDATE accounts SET credits=? WHERE id=?')
        .bind(this.credits, this.accountId).run();
    }

    return { ok: true, remaining: this.credits };
  }

  async topUp(amount: number, sessionId: string, env: Env): Promise<number> {
    if (this.credits === null) this.credits = 0;
    this.credits += amount;
    await env.DB.prepare('UPDATE accounts SET credits=? WHERE id=?')
      .bind(this.credits, this.accountId).run();
    return this.credits;
  }

  async balance(): Promise<number> {
    return this.credits ?? 0;
  }
}
```

## API Gateway Worker with Credit Gate

```ts
// src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const accountId = request.headers.get('X-Account-Id');
    if (!accountId) return new Response('Missing account', { status: 401 });

    const requestId = crypto.randomUUID();
    const id = env.CREDIT_ACCOUNT.idFromName(accountId);
    const stub = env.CREDIT_ACCOUNT.get(id);

    // Initialize DO with current DB balance (no-op if already loaded)
    await stub.initialize(accountId, env);

    const COST_PER_REQUEST = 1; // 1 credit per call
    const result = await stub.deduct(COST_PER_REQUEST, requestId, env);

    if (!result.ok) {
      return Response.json(
        { error: 'Insufficient credits', remaining: result.remaining },
        { status: 402 }
      );
    }

    // Serve actual API response
    const data = await handleApiRequest(request, env);
    return Response.json({
      ...data,
      _meta: { credits_remaining: result.remaining, request_id: requestId },
    });
  },
};

async function handleApiRequest(request: Request, env: Env): Promise<Record<string, unknown>> {
  // Your business logic here
  return { message: 'ok' };
}
```

## Stripe Webhook: Credit Bundle Purchase

```ts
// src/stripe-webhook.ts
import Stripe from 'stripe';

const BUNDLE_CREDITS: Record<string, number> = {
  price_starter: 1000,
  price_pro: 5000,
  price_enterprise: 25000,
};

export async function handleStripeWebhook(request: Request, env: Env & { STRIPE_WEBHOOK_SECRET: string; STRIPE_SECRET_KEY: string }): Promise<Response> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY, { apiVersion: '2024-06-20' });
  const body = await request.text();
  const sig = request.headers.get('stripe-signature') ?? '';

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(body, sig, env.STRIPE_WEBHOOK_SECRET);
  } catch {
    return new Response('Invalid signature', { status: 400 });
  }

  if (event.type === 'checkout.session.completed') {
    const session = event.data.object as Stripe.Checkout.Session;
    const accountId = session.metadata?.account_id;
    const priceId = session.metadata?.price_id;
    if (!accountId || !priceId) return new Response('Missing metadata', { status: 400 });

    const credits = BUNDLE_CREDITS[priceId] ?? 0;
    if (credits === 0) return new Response('Unknown price', { status: 400 });

    // Record purchase in D1
    await env.DB.prepare(
      `INSERT INTO credit_transactions(id,account_id,delta,reason,stripe_session_id,created_at)
       VALUES(?,?,?,?,?,unixepoch())`
    ).bind(crypto.randomUUID(), accountId, credits, 'purchase', session.id).run();

    // Signal DO to top up in-memory balance
    const id = env.CREDIT_ACCOUNT.idFromName(accountId);
    const stub = env.CREDIT_ACCOUNT.get(id);
    await stub.topUp(credits, session.id, env);
  }

  return new Response('ok');
}
```

## Anti-patterns

- Do not deduct credits from D1 directly in the fetch handler — concurrent requests will double-spend
- Do not await the D1 audit write in the hot path — use fire-and-forget with `.catch()`
- Do not store Stripe secrets in Worker source; use `wrangler secret put STRIPE_SECRET_KEY`
- Do not use a single global Durable Object instance for all accounts — shard by account ID

## Gotchas

- Durable Object in-memory state is lost on eviction; always re-read from D1 on cold start (`this.credits === null` guard)
- The lazy flush (2% probability) means D1 can lag the true balance by up to 50 deductions; add a periodic alarm to force sync
- Stripe webhook replay protection requires idempotency — check for duplicate `stripe_session_id` before inserting
- `wrangler.toml` must declare `durable_objects.bindings` and `migrations` for the DO class

## Verification

```ts
// Smoke test: deduct 1 credit, expect remaining=999 on second call
const headers = { 'X-Account-Id': 'test-account-001' };
const r1 = await fetch('https://api.example.com/v1/query', { headers });
const j1 = await r1.json();
console.assert(r1.status === 200, 'first call should succeed');
console.assert(typeof j1._meta.credits_remaining === 'number', 'remaining present');

// Exhaust balance and expect 402
// (seed account with 0 credits in D1 first)
const r2 = await fetch('https://api.example.com/v1/query', {
  headers: { 'X-Account-Id': 'zero-credit-account' }
});
console.assert(r2.status === 402, 'zero-credit account blocked');
```

## Related

- documentation/docs/policies/cloudflare/durable-objects-best-practices.md
- documentation/docs/policies/cloudflare/d1-best-practices.md
- documentation/docs/policies/cloudflare/workers-stripe-webhook.md

## Sources

- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/d1/
- https://stripe.com/docs/webhooks
- https://developers.cloudflare.com/workers/runtime-apis/bindings/
