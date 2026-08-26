# solana-helius-webhook-payment-verification

**Date:** 2026-08-22
**Author:** example.com
**Repo:** example-org/example-repo
**Status:** published

## Symptom

example project generates a Solana pay request (SOL or SPL token), hands it to
the user's mobile wallet via a deep link, and must confirm the payment
server-side before provisioning access. The on-chain confirmation event
must be verified for correct amount, correct recipient, and correct token
— a webhook containing the right signature is not the same as a payment
that satisfied the order.

## Context

Delivery chain for a example project checkout:
`User taps Pay → deep-link opens Phantom/Solflare → wallet signs +
broadcasts tx → Solana validator confirms → Helius enhanced webhook
POST → Cloudflare Worker → verify amount + recipient + token →
D1 idempotency write → provision order`

Helius enhanced webhooks (`ENHANCED_TRANSACTION` type) emit one POST
per confirmed transaction with a structured payload including the
parsed `nativeTransfers`, `tokenTransfers`, `accountData`, and
transaction `signature`. Use the `ACCOUNT_ACTIVITY` or
`ADDRESS_ACTIVITY` type to scope delivery to your custodial payment
receiving addresses only.

## Helius authHeader verification

Helius does not HMAC-sign webhook bodies. It echoes a static token
in the `Authorization` header that you supplied at webhook creation.
This differs from Stripe and NOWPayments; treat it as a shared secret.

```typescript
// wrangler secret put HELIUS_AUTH_SECRET
export default {
  async fetch(req: Request, env: Env,
              ctx: ExecutionContext): Promise<Response> {
    const auth = req.headers.get('Authorization') ?? '';
    if (auth !== env.HELIUS_AUTH_SECRET)
      return new Response('Unauthorized', { status: 403 });

    // Return 200 immediately; process asynchronously
    ctx.waitUntil(verifyAndSettle(req.clone(), env));
    return new Response('ok', { status: 200 });
  },
};
```

A 403 stops Helius retries immediately. Keep the auth check as the
very first gate — no body parsing before it.

## Payment verification: amount, recipient, and token

After auth, validate three business invariants before writing any
order state:

```typescript
interface PendingOrder {
  orderId: string;
  expectedLamports: bigint;   // SOL-denominated orders
  expectedMint?: string;      // undefined = SOL only
  recipientAddress: string;
  createdAt: number;
}

async function verifyAndSettle(req: Request, env: Env) {
  const events = (await req.json()) as HeliusEnhancedEvent[];
  for (const evt of events) {
    const sig = evt.signature;
    if (!sig) continue;

    // --- 1. D1 idempotency (see below) ---
    const isNew = await markSeen(sig, env);
    if (!isNew) continue;

    // --- 2. Fetch the pending order keyed by reference ---
    // Reference is a unique public key embedded in the
    // Solana Pay URL and appears in accountData.
    const ref = extractReference(evt);
    if (!ref) { await markFailed(sig, 'no-ref', env); continue; }

    const order = await loadPendingOrder(ref, env);
    if (!order) { await markFailed(sig, 'unknown-order', env); continue; }

    // --- 3. Amount + recipient check ---
    if (order.expectedMint) {
      const transfer = evt.tokenTransfers?.find(
        t => t.mint === order.expectedMint &&
             t.toUserAccount === order.recipientAddress
      );
      if (!transfer || BigInt(transfer.tokenAmount) <
                       order.expectedLamports) {
        await markFailed(sig, 'amount-mismatch', env); continue;
      }
    } else {
      const transfer = evt.nativeTransfers?.find(
        t => t.toUserAccount === order.recipientAddress
      );
      if (!transfer ||
          BigInt(transfer.amount) < order.expectedLamports) {
        await markFailed(sig, 'amount-mismatch', env); continue;
      }
    }

    // --- 4. Expiry guard ---
    if (Date.now() - order.createdAt > 15 * 60_000) {
      await markFailed(sig, 'expired', env); continue;
    }

    await provisionOrder(order.orderId, sig, env);
  }
}
```

`nativeTransfers[].amount` is in lamports (1 SOL = 1 000 000 000).
`tokenTransfers[].tokenAmount` is the human-readable decimal string;
multiply by `10 ** decimals` if you need integer comparison.

## D1 idempotency schema

```sql
-- One-time migration
CREATE TABLE IF NOT EXISTS solana_txns (
  sig        TEXT PRIMARY KEY,
  status     TEXT NOT NULL DEFAULT 'seen',   -- seen | verified | failed
  reason     TEXT,
  order_id   TEXT,
  received   INTEGER NOT NULL
);
```

```typescript
async function markSeen(sig: string, env: Env): Promise<boolean> {
  const { meta } = await env.DB.prepare(
    `INSERT OR IGNORE INTO solana_txns (sig, received)
     VALUES (?, ?)`
  ).bind(sig, Date.now()).run();
  return meta.changes === 1; // false = already processed
}

async function markFailed(sig: string, reason: string, env: Env) {
  await env.DB.prepare(
    `UPDATE solana_txns SET status = 'failed', reason = ?
     WHERE sig = ?`
  ).bind(reason, sig).run();
}

async function provisionOrder(
  orderId: string, sig: string, env: Env) {
  await env.DB.prepare(
    `UPDATE solana_txns SET status = 'verified', order_id = ?
     WHERE sig = ?`
  ).bind(orderId, sig).run();
  // ...update orders table, emit fulfilment event...
}
```

Prune rows in a daily Cron Trigger:
```sql
DELETE FROM solana_txns WHERE received < ? AND status != 'verified';
```
Keep `verified` rows indefinitely for audit; prune `seen`/`failed`
after 30 days.

## Mobile wallet deep link UX

Solana Pay defines two URI schemes:
- `solana:<recipient>?amount=<SOL>&label=<label>&reference=<ref>`
- `solana:<api-url>` (POST request schema for SPL tokens)

```typescript
// Generate a unique reference keypair per order
import { Keypair } from '@solana/web3.js';

function buildSolanaPayUrl(order: PendingOrder): string {
  const ref = Keypair.generate().publicKey.toBase58();
  // Persist ref → orderId in D1 before returning URL
  const params = new URLSearchParams({
    amount: (Number(order.expectedLamports) / 1e9).toFixed(9),
    label:  'example project Payment',
    message: `Order ${order.orderId}`,
    reference: ref,
  });
  return `solana:${order.recipientAddress}?${params}`;
}
```

| Wallet       | Deep-link scheme    | Universal link                  |
|--------------|---------------------|---------------------------------|
| Phantom      | `phantom://`        | `https://phantom.app/ul/v1/`    |
| Solflare     | `solflare://`       | `https://solflare.com/ul/v1/`   |
| Backpack     | `backpack://`       | none (app-store link)           |
| Mobile wallet adapter | Custom scheme via `wallet-standard` | — |

For best conversion, attempt to open the Solana Pay URI directly:
```typescript
window.location.href = solanaPayUri;
// After 2 s, if still on the page, show a QR code fallback
setTimeout(() => setShowQR(true), 2000);
```

Wallets redirect back using the `redirect_url` field in the request
schema POST response. Return the example project callback URL there so users
land back in the app after signing:
```json
{ "redirect_url": "https://example.com/checkout/solana-return?order=<id>" }
```
The return page polls `/api/order/<id>/status` (backed by D1) until
`verified` or times out at 60 seconds.

## Confirmed vs Finalized

Helius enhanced webhooks fire on `confirmed` commitment by default
(≈ 0.4 s, but not rollback-safe). For payment amounts above a
threshold, require `finalized` (≈ 32 slots, ~13 s):

```typescript
// At webhook creation time via Helius API
{
  "webhookType": "enhanced",
  "txnStatus": "success",    // filter out failed txns
  "commitment": "finalized"  // "confirmed" or "finalized"
}
```

Recommended thresholds:
| Order value | Commitment    | Typical latency |
|-------------|---------------|-----------------|
| < $50       | confirmed     | ~400 ms         |
| $50–$500    | confirmed     | ~400 ms + reconcile at finalize |
| > $500      | finalized     | ~13 s           |

For mid-range orders, provision access at `confirmed` but hold
irreversible actions (payouts, NFT mints) until a second Helius
webhook fires at `finalized`.

## Anti-patterns

- Trusting `evt.type === 'TRANSFER'` alone without checking
  `nativeTransfers` or `tokenTransfers` — some programs emit
  `TRANSFER` for internal bookkeeping not representing value.
- Deriving expected amount from the webhook payload itself — always
  load the expected amount from your D1 order record, never from
  the incoming event.
- Using a hardcoded recipient address string comparison with
  mixed base58 capitalisation — always normalise via
  `new PublicKey(addr).toBase58()` before comparing.
- Opening the deep link inside a React Native WebView — embedded
  WebViews cannot hand off to the system wallet; open via
  `Linking.openURL` in native code or the real device browser.
- Setting expiry > 30 minutes — SOL price drift makes stale orders
  under-funded; 10–15 minutes is the practical maximum.

## Gotchas

- Helius retries 3 times at 1-second intervals on 5xx; a 403 halts
  retries immediately. A mis-configured `authHeader` causes permanent
  event loss with no alert.
- Token decimals vary by mint (USDC = 6, custom tokens vary);
  hard-coding 6 decimals breaks non-USDC SPL payments.
- `reference` public key must be generated per-order, not reused —
  Helius matches the address in `accountData` not a custom field.
- On devnet, `confirmed` finality can stall during validator epoch
  transitions; always test on mainnet-beta under low load for timing.
- Helius auto-disables webhooks at ≥ 95% failure rate; add a daily
  cron that GETs the webhook status endpoint and alerts on `inactive`.

## Verification checklist

- POST payload with wrong `Authorization`; assert 403 and zero D1
  rows inserted.
- Send same valid payload twice; assert second invocation returns
  200 but `provisionOrder` is never called.
- Send payload with `amount` 1 lamport below `expectedLamports`;
  assert `failed` with `amount-mismatch` in D1.
- Send payload with wrong `mint`; assert `failed` with
  `amount-mismatch`.
- Trigger a real devnet SOL transfer via Phantom mobile; confirm
  `verified` status in D1 within 2 s and access provisioned.
- Set `createdAt` to 20 minutes ago in D1 before triggering; assert
  `failed` with `expired`.

## Related

- `payments/helius-webhook-mobile-push-delivery.md`
- `payments/solana-wallet-adapter-mobile-browser.md`
- `payments/nowpayments-webhook-hmac-sha512.md`
- `payments/idempotency-keys-payment-apis.md`
- `payments/crypto-payments-nowpayments-settlement.md`

## Source URLs (verified 2026-08-22)

- https://docs.helius.dev/webhooks-and-websockets/what-are-webhooks
- https://docs.helius.dev/webhooks-and-websockets/enhanced-transactions-api/enhanced-transaction-types
- https://spl.solana.com/token
- https://docs.solanapay.com/spec
- https://github.com/solana-labs/solana-pay
- https://docs.phantom.app/developer-powertools/deeplinks-ios-and-android
- https://developers.cloudflare.com/d1/
