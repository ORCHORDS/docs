# Razorpay Workers — India Payment Integration

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You are building a SaaS or e-commerce product for India and need to accept UPI, Netbanking, wallets (Paytm, PhonePe, Amazon Pay), cards, and EMI from a Cloudflare Workers backend. Razorpay is the default choice for India-first products: it handles RBI compliance, GST invoicing, and the full domestic payment stack. Common pain points include webhook signature mismatch with Workers' body parsing, confusion between `order_id` and `payment_id`, and handling `payment.failed` vs `payment.captured` state machine correctly.

## Context

Razorpay's payment flow has two mandatory server-side steps: **create an order** (returns `order_id`) and **verify the payment signature** after the client completes the checkout. The order creation must happen on your server (Workers); the frontend uses Razorpay's JS checkout to collect payment details; your backend then verifies the `razorpay_signature` that Razorpay sends post-payment. Webhook events are a secondary channel for async methods (UPI collect, Netbanking), and require HMAC-SHA256 verification using your webhook secret — distinct from your API secret.

The Razorpay Node SDK uses `crypto` built-ins not available in Workers. All calls must use raw `fetch` with HTTP Basic Auth (`key_id:key_secret`).

## 1. Environment and Auth

```typescript
export interface Env {
  RAZORPAY_KEY_ID: string;
  RAZORPAY_KEY_SECRET: string;
  RAZORPAY_WEBHOOK_SECRET: string;
  PAYMENTS_KV: KVNamespace;
}

const RP_API = "https://api.razorpay.com/v1";

function rpAuth(env: Env): string {
  const credentials = `${env.RAZORPAY_KEY_ID}:${env.RAZORPAY_KEY_SECRET}`;
  return "Basic " + btoa(credentials);
}

function rpHeaders(env: Env): HeadersInit {
  return {
    Authorization: rpAuth(env),
    "Content-Type": "application/json",
  };
}
```

## 2. Create Order

Every Razorpay payment must start with a server-side order. The amount is always in the **smallest currency unit** (paise for INR: ₹100 = `10000`).

```typescript
interface RazorpayOrderPayload {
  amount: number;      // in paise
  currency: "INR";
  receipt: string;     // your internal order/reference ID, max 40 chars
  notes?: Record<string, string>;
  partial_payment?: boolean;
}

interface RazorpayOrder {
  id: string;          // "order_XYZ..." — pass to frontend checkout
  entity: "order";
  amount: number;
  currency: string;
  receipt: string;
  status: "created" | "attempted" | "paid";
  attempts: number;
  created_at: number;
}

async function createOrder(
  env: Env,
  payload: RazorpayOrderPayload
): Promise<RazorpayOrder> {
  const res = await fetch(`${RP_API}/orders`, {
    method: "POST",
    headers: rpHeaders(env),
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json<{ error: { description: string } }>();
    throw new Error(`Razorpay order error: ${err.error.description}`);
  }

  return res.json<RazorpayOrder>();
}

// Worker route: POST /checkout/order
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "POST" && url.pathname === "/checkout/order") {
      const body = await request.json<{ amountINR: number; orderId: string }>();

      const order = await createOrder(env, {
        amount: Math.round(body.amountINR * 100), // convert ₹ to paise
        currency: "INR",
        receipt: body.orderId.slice(0, 40),
        notes: { source: "workers-edge" },
      });

      // Return order ID + key_id to the frontend — never return key_secret
      return Response.json({
        orderId: order.id,
        amount: order.amount,
        currency: order.currency,
        keyId: env.RAZORPAY_KEY_ID,
      });
    }

    return new Response("Not found", { status: 404 });
  },
};
```

## 3. Payment Signature Verification

After the client-side checkout completes, Razorpay sends three values to your success callback: `razorpay_order_id`, `razorpay_payment_id`, `razorpay_signature`. Verify the signature before fulfilling the order.

```typescript
async function verifyPaymentSignature(
  env: Env,
  orderId: string,
  paymentId: string,
  signature: string
): Promise<boolean> {
  const message = `${orderId}|${paymentId}`;
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(env.RAZORPAY_KEY_SECRET),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(message));
  const computed = Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  // Timing-safe comparison
  return crypto.timingSafeEqual(
    new TextEncoder().encode(computed),
    new TextEncoder().encode(signature)
  );
}

// Worker route: POST /checkout/verify
async function handleVerify(request: Request, env: Env): Promise<Response> {
  const body = await request.json<{
    razorpay_order_id: string;
    razorpay_payment_id: string;
    razorpay_signature: string;
    internalOrderId: string;
  }>();

  const valid = await verifyPaymentSignature(
    env,
    body.razorpay_order_id,
    body.razorpay_payment_id,
    body.razorpay_signature
  );

  if (!valid) {
    return Response.json({ success: false, error: "Invalid signature" }, { status: 400 });
  }

  // Mark order as paid in KV
  await env.PAYMENTS_KV.put(
    `rp:payment:${body.razorpay_payment_id}`,
    JSON.stringify({
      orderId: body.internalOrderId,
      razorpayOrderId: body.razorpay_order_id,
      paymentId: body.razorpay_payment_id,
      verifiedAt: Date.now(),
    }),
    { expirationTtl: 60 * 60 * 24 * 90 }
  );

  return Response.json({ success: true, paymentId: body.razorpay_payment_id });
}
```

## 4. Webhook Verification and Processing

Razorpay sends webhook events for async methods (UPI, Netbanking) that may settle minutes after the checkout UI closes.

```typescript
async function verifyRazorpayWebhook(
  request: Request,
  secret: string
): Promise<{ valid: boolean; body: string }> {
  const body = await request.text(); // must read as text before JSON parsing
  const signature = request.headers.get("X-Razorpay-Signature") ?? "";

  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body));
  const computed = Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");

  const valid = crypto.timingSafeEqual(
    new TextEncoder().encode(computed),
    new TextEncoder().encode(signature)
  );

  return { valid, body };
}

interface RazorpayWebhookEvent {
  entity: "event";
  event:
    | "payment.captured"
    | "payment.failed"
    | "order.paid"
    | "refund.created"
    | "refund.processed";
  payload: {
    payment?: { entity: { id: string; order_id: string; amount: number; status: string } };
    order?: { entity: RazorpayOrder };
    refund?: { entity: { id: string; payment_id: string; amount: number; status: string } };
  };
}

async function handleWebhook(request: Request, env: Env): Promise<Response> {
  const { valid, body } = await verifyRazorpayWebhook(request, env.RAZORPAY_WEBHOOK_SECRET);
  if (!valid) return new Response("Unauthorized", { status: 401 });

  const event = JSON.parse(body) as RazorpayWebhookEvent;

  switch (event.event) {
    case "payment.captured": {
      const payment = event.payload.payment?.entity;
      if (payment) {
        await env.PAYMENTS_KV.put(
          `rp:captured:${payment.id}`,
          JSON.stringify({ orderId: payment.order_id, amount: payment.amount }),
          { expirationTtl: 60 * 60 * 24 * 90 }
        );
      }
      break;
    }
    case "payment.failed": {
      const payment = event.payload.payment?.entity;
      if (payment) {
        await env.PAYMENTS_KV.put(
          `rp:failed:${payment.id}`,
          JSON.stringify({ orderId: payment.order_id, status: payment.status }),
          { expirationTtl: 60 * 60 * 24 * 7 }
        );
      }
      break;
    }
  }

  return new Response("OK");
}
```

## 5. Fetch Payment Details

```typescript
interface RazorpayPayment {
  id: string;
  entity: "payment";
  amount: number;
  currency: string;
  status: "created" | "authorized" | "captured" | "refunded" | "failed";
  order_id: string;
  method: "card" | "netbanking" | "wallet" | "emi" | "upi";
  captured: boolean;
  description: string | null;
  email: string;
  contact: string;
  created_at: number;
}

async function fetchPayment(env: Env, paymentId: string): Promise<RazorpayPayment> {
  const res = await fetch(`${RP_API}/payments/${paymentId}`, {
    headers: rpHeaders(env),
  });

  if (!res.ok) throw new Error(`Failed to fetch payment ${paymentId}`);
  return res.json<RazorpayPayment>();
}
```

## Anti-patterns

- **Sending the verification to the client** — `key_secret` must never leave the Worker. Only send `key_id` to the frontend.
- **Parsing the webhook body as JSON before HMAC** — Razorpay signs the raw text body. Calling `request.json()` before verifying discards the original bytes and will cause signature mismatch on any non-canonical JSON.
- **Using `payment_id` as the primary key before verification** — before `verifyPaymentSignature` passes, the payment ID is untrusted user input. Always verify first.
- **Assuming UPI and Netbanking are synchronous** — both methods may go to `authorized` state but not `captured` for minutes. Always listen to `payment.captured` webhooks.
- **Amount confusion** — Razorpay always works in paise (₹1 = 100). A payment of `amount: 100` is one rupee, not one hundred.

## Gotchas

- Test mode key_id starts with `rzp_test_`; live starts with `rzp_live_`. Mixing them causes `BAD_REQUEST_ERROR`.
- `receipt` field is max 40 characters and must be unique per order within your account.
- Razorpay does not auto-capture authorized payments by default on some account configurations. Check your dashboard setting or explicitly call the capture API.
- The webhook secret is separate from `key_secret`. Both must be stored as Workers Secrets.
- Indian customers frequently use UPI VPAs (like `name@okaxis`) — these are entered in the Razorpay checkout and never reach your backend.

## Verification

```bash
# Create a test order
curl -u rzp_test_KEY:SECRET \
  -X POST https://api.razorpay.com/v1/orders \
  -H "Content-Type: application/json" \
  -d '{"amount":50000,"currency":"INR","receipt":"order_test_001"}'

# Expected: {"id":"order_...","status":"created","amount":50000,"currency":"INR"}

# Simulate webhook locally with wrangler dev
# Use Razorpay dashboard → Webhooks → Test button to send a test event
```

## Related

- `paytm-workers-upi-payment-flow.md` — Paytm/UPI alternative flow
- `idempotency-keys-payment-apis.md` — receipt uniqueness strategy
- `payment-state-machine-design.md` — authorized → captured transition handling
- `payment-webhook-signature-verification.md` — general pattern

## Sources

- Razorpay API reference: https://razorpay.com/docs/api/
- Orders API: https://razorpay.com/docs/api/orders/
- Payment signature verification: https://razorpay.com/docs/payments/payment-gateway/web-integration/standard/build-integration/#verify-the-payment-signature
- Webhooks: https://razorpay.com/docs/webhooks/
