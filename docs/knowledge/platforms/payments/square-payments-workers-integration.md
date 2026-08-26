# Square Payments Workers Integration

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You need to accept card payments through Square on a Cloudflare Workers-hosted storefront or API. The Square Web Payments SDK must be loaded client-side while the server-side order creation, payment confirmation, and refund lifecycle all live in a Workers service that talks to the Square Payments API v2.

## Context

Square's Payments API follows a two-step flow: create an Order (optional but recommended for item-level tax/discount support), obtain a payment `sourceId` from the client-side Web Payments SDK (a nonce), then `POST /v2/payments` to charge the card. The nonce is single-use and expires in 24 hours. Workers handles the server side; all card data flows through Square's hosted JS, keeping Workers out of PCI scope for card numbers.

## Create a Square Order and Return Payment Nonce URL

```typescript
// src/square.ts
import { createClient } from "square"; // npm: square

export interface Env {
  SQUARE_ACCESS_TOKEN: string;
  SQUARE_LOCATION_ID: string;
}

interface CartItem {
  name: string;
  quantity: number;
  basePriceMoney: { amount: bigint; currency: string };
}

export async function createSquareOrder(
  items: CartItem[],
  idempotencyKey: string,
  env: Env
): Promise<{ orderId: string; totalMoney: { amount: bigint; currency: string } }> {
  const client = createClient({ accessToken: env.SQUARE_ACCESS_TOKEN });

  const { result } = await client.ordersApi.createOrder({
    idempotencyKey,
    order: {
      locationId: env.SQUARE_LOCATION_ID,
      lineItems: items.map((item) => ({
        name: item.name,
        quantity: String(item.quantity),
        basePriceMoney: {
          amount: item.basePriceMoney.amount,
          currency: item.basePriceMoney.currency,
        },
      })),
    },
  });

  if (!result.order) throw new Error("Square order creation failed");

  return {
    orderId: result.order.id!,
    totalMoney: result.order.totalMoney!,
  };
}
```

## Confirm Payment with a Client Nonce

```typescript
// src/handlers/charge.ts
import { createClient } from "square";
import { createSquareOrder } from "../square";

export async function handleCharge(request: Request, env: Env): Promise<Response> {
  const body = await request.json<{
    sourceId: string; // nonce from Square Web Payments SDK
    items: CartItem[];
    idempotencyKey: string;
  }>();

  const { orderId, totalMoney } = await createSquareOrder(
    body.items,
    `order-${body.idempotencyKey}`,
    env
  );

  const client = createClient({ accessToken: env.SQUARE_ACCESS_TOKEN });

  const { result } = await client.paymentsApi.createPayment({
    idempotencyKey: body.idempotencyKey,
    sourceId: body.sourceId,
    amountMoney: totalMoney,
    locationId: env.SQUARE_LOCATION_ID,
    orderId,
    autocomplete: true, // capture immediately; set false for auth-only
  });

  const payment = result.payment;
  if (!payment || payment.status !== "COMPLETED") {
    return new Response(
      JSON.stringify({ error: "Payment not completed", status: payment?.status }),
      { status: 402, headers: { "Content-Type": "application/json" } }
    );
  }

  return new Response(
    JSON.stringify({ paymentId: payment.id, receiptUrl: payment.receiptUrl }),
    { status: 200, headers: { "Content-Type": "application/json" } }
  );
}
```

## Issue a Refund

```typescript
// src/handlers/refund.ts
import { createClient } from "square";

export async function handleRefund(request: Request, env: Env): Promise<Response> {
  const { paymentId, amountMoney, reason, idempotencyKey } =
    await request.json<{
      paymentId: string;
      amountMoney: { amount: bigint; currency: string };
      reason: string;
      idempotencyKey: string;
    }>();

  const client = createClient({ accessToken: env.SQUARE_ACCESS_TOKEN });

  const { result, statusCode } = await client.refundsApi.refundPayment({
    idempotencyKey,
    paymentId,
    amountMoney,
    reason,
  });

  if (statusCode !== 200 && statusCode !== 201) {
    const errors = result.errors?.map((e) => e.detail).join("; ");
    return new Response(JSON.stringify({ error: errors }), {
      status: 422,
      headers: { "Content-Type": "application/json" },
    });
  }

  return new Response(
    JSON.stringify({
      refundId: result.refund?.id,
      status: result.refund?.status,
    }),
    { status: 200, headers: { "Content-Type": "application/json" } }
  );
}
```

## Webhook Signature Verification

```typescript
// src/handlers/square-webhook.ts
import { WebhooksHelper } from "square";

export async function handleSquareWebhook(
  request: Request,
  env: Env & { SQUARE_WEBHOOK_SIGNATURE_KEY: string }
): Promise<Response> {
  const rawBody = await request.text();
  const signature = request.headers.get("x-square-hmacsha256-signature") ?? "";
  const url = new URL(request.url).toString();

  const isValid = WebhooksHelper.isValidWebhookEventSignature(
    rawBody,
    signature,
    env.SQUARE_WEBHOOK_SIGNATURE_KEY,
    url
  );

  if (!isValid) {
    return new Response("Invalid signature", { status: 403 });
  }

  const event = JSON.parse(rawBody);

  if (event.type === "payment.completed") {
    const payment = event.data.object.payment;
    // persist to D1, trigger fulfillment, etc.
    console.log("Payment completed:", payment.id);
  }

  return new Response("OK", { status: 200 });
}
```

## Anti-patterns

- Do not store the Web Payments SDK nonce server-side for later reuse; it is single-use and expires quickly.
- Do not skip the `idempotencyKey` on payment and refund calls; retrying without one creates duplicate charges.
- Do not call `createOrder` and `createPayment` in separate Workers subrequests without propagating the order ID; orphaned orders inflate Square's analytics.

## Gotchas

- Square's Node SDK uses `BigInt` for monetary amounts; serializing these to JSON requires a custom replacer (`value => value.toString()`) because `JSON.stringify` throws on `BigInt`.
- The `autocomplete: false` path creates an APPROVED (not COMPLETED) payment; you must call `completePayment` separately or the hold releases after 7 days.
- Square sandbox and production use different access tokens; the location ID is also environment-specific and must be set per-env in `wrangler.toml`.

## Verification

```bash
# Create a test payment with the Square sandbox nonce cnon:card-nonce-ok
curl -X POST https://your-worker.workers.dev/charge \
  -H "Content-Type: application/json" \
  -d '{"sourceId":"cnon:card-nonce-ok","items":[{"name":"Widget","quantity":1,"basePriceMoney":{"amount":1000,"currency":"USD"}}],"idempotencyKey":"test-001"}'

# Check the payment in the Square sandbox dashboard
open https://developer.squareup.com/console/en/sandbox-test-accounts
```

## Related

- `payments/payment-orchestration-multi-psp-routing.md`
- `payments/idempotency-keys-payment-apis.md`
- `payments/partial-refund-handling.md`

## Sources

- https://developer.squareup.com/docs/payments-api/take-payments
- https://developer.squareup.com/docs/webhooks/v2webhooks
- https://developer.squareup.com/docs/orders-api/what-it-does
