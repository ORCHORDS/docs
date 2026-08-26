# Lightning Network Payments on Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You want to accept Bitcoin Lightning Network micropayments on a Workers-hosted storefront without running your own Lightning node in the critical path. The integration targets BTCPay Server (self-hosted or BTCPay Cloud) or the LND REST API, generates a BOLT11 invoice per order, and marks the order paid once the Workers webhook endpoint receives the `InvoiceSettled` callback from BTCPay.

## Context

Lightning payments are pull-based at the protocol level but push-based from the integration's point of view: the server creates a BOLT11 invoice, the customer's wallet pays it, and the server detects settlement via a server-sent event or webhook. Workers handles invoice creation, serves the QR code data URI, and validates settlement callbacks. Because Lightning invoices expire (typically 15–60 minutes), the order session must store the invoice expiry and poll or await a webhook to gate fulfillment.

## Create a BOLT11 Invoice via BTCPay Server API

```typescript
// src/lightning.ts
export interface Env {
  BTCPAY_BASE_URL: string;   // e.g. https://btcpay.example.com
  BTCPAY_STORE_ID: string;
  BTCPAY_API_KEY: string;    // generated in BTCPay Server → Account → API Keys
  LIGHTNING_EXPIRY_SECONDS: string; // e.g. "900" (15 min)
}

export interface LightningInvoice {
  id: string;
  checkoutLink: string;
  paymentRequest: string; // BOLT11 string for QR code
  expiresAt: number;      // Unix timestamp
  amountSats: number;
}

export async function createLightningInvoice(
  orderId: string,
  amountUsd: number,  // Workers fetches BTC/USD rate and converts
  env: Env
): Promise<LightningInvoice> {
  // Fetch live BTC/USD rate (replace with your preferred oracle)
  const rateRes = await fetch(
    "https://api.coinbase.com/v2/exchange-rates?currency=BTC"
  );
  const rateData: any = await rateRes.json();
  const btcUsd = parseFloat(rateData.data.rates.USD);
  const amountBtc = amountUsd / btcUsd;
  const amountSats = Math.ceil(amountBtc * 1e8);

  const body = {
    amount: amountSats.toString(),
    currency: "SATS",
    orderId,
    itemDesc: `Order ${orderId}`,
    notificationURL: `${env.BTCPAY_BASE_URL}/webhook/lightning`,
    checkout: {
      expirationMinutes: Math.ceil(parseInt(env.LIGHTNING_EXPIRY_SECONDS) / 60),
      monitoringMinutes: 60,
    },
  };

  const res = await fetch(
    `${env.BTCPAY_BASE_URL}/api/v1/stores/${env.BTCPAY_STORE_ID}/invoices`,
    {
      method: "POST",
      headers: {
        Authorization: `token ${env.BTCPAY_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    }
  );

  if (!res.ok) {
    throw new Error(`BTCPay invoice creation failed ${res.status}: ${await res.text()}`);
  }

  const invoice: any = await res.json();

  // Fetch the Lightning payment method to get the BOLT11 string
  const pmRes = await fetch(
    `${env.BTCPAY_BASE_URL}/api/v1/stores/${env.BTCPAY_STORE_ID}/invoices/${invoice.id}/payment-methods`,
    {
      headers: { Authorization: `token ${env.BTCPAY_API_KEY}` },
    }
  );
  const methods: any[] = await pmRes.json();
  const ln = methods.find((m) => m.paymentMethodId === "BTC-LN");

  return {
    id: invoice.id,
    checkoutLink: invoice.checkoutLink,
    paymentRequest: ln?.destination ?? "",
    expiresAt: invoice.expirationTime,
    amountSats,
  };
}
```

## Webhook Handler — Verify and Settle Order

```typescript
// src/handlers/lightning-webhook.ts
import { createHmac } from "node:crypto"; // available in Workers Node compat

export interface Env {
  BTCPAY_WEBHOOK_SECRET: string;
  DB: D1Database;
}

export async function handleLightningWebhook(
  request: Request,
  env: Env
): Promise<Response> {
  const rawBody = await request.text();
  const sigHeader = request.headers.get("BTCPay-Sig") ?? "";
  // BTCPay sends "sha256=<hex>"
  const [, receivedSig] = sigHeader.split("=");

  const expectedSig = createHmac("sha256", env.BTCPAY_WEBHOOK_SECRET)
    .update(rawBody)
    .digest("hex");

  if (receivedSig !== expectedSig) {
    return new Response("Bad signature", { status: 403 });
  }

  const event: any = JSON.parse(rawBody);

  if (event.type === "InvoiceSettled") {
    const invoiceId: string = event.invoiceId;

    await env.DB.prepare(
      `UPDATE orders
       SET payment_status = 'paid',
           paid_at        = unixepoch(),
           lightning_invoice_id = ?
       WHERE lightning_invoice_id = ?
         AND payment_status = 'pending'`
    )
      .bind(invoiceId, invoiceId)
      .run();
  }

  if (event.type === "InvoiceExpired" || event.type === "InvoiceInvalid") {
    const invoiceId: string = event.invoiceId;
    await env.DB.prepare(
      `UPDATE orders SET payment_status = 'expired' WHERE lightning_invoice_id = ?`
    )
      .bind(invoiceId)
      .run();
  }

  return new Response("OK", { status: 200 });
}
```

## Serve QR Code and Poll for Settlement

```typescript
// src/handlers/lightning-status.ts
export interface Env {
  BTCPAY_BASE_URL: string;
  BTCPAY_STORE_ID: string;
  BTCPAY_API_KEY: string;
  DB: D1Database;
}

export async function handleInvoiceStatus(
  request: Request,
  env: Env
): Promise<Response> {
  const { searchParams } = new URL(request.url);
  const invoiceId = searchParams.get("invoiceId");
  if (!invoiceId) return new Response("Missing invoiceId", { status: 400 });

  const res = await fetch(
    `${env.BTCPAY_BASE_URL}/api/v1/stores/${env.BTCPAY_STORE_ID}/invoices/${invoiceId}`,
    { headers: { Authorization: `token ${env.BTCPAY_API_KEY}` } }
  );

  if (!res.ok) return new Response("Invoice not found", { status: 404 });

  const invoice: any = await res.json();

  // Map BTCPay statuses to a simple client-facing status
  const statusMap: Record<string, string> = {
    New: "pending",
    Processing: "pending",
    Settled: "paid",
    Expired: "expired",
    Invalid: "invalid",
  };

  return new Response(
    JSON.stringify({
      status: statusMap[invoice.status] ?? "unknown",
      expiresAt: invoice.expirationTime,
    }),
    { headers: { "Content-Type": "application/json" } }
  );
}
```

## Anti-patterns

- Do not rely solely on the webhook for settlement detection in user-facing flows; clients should also poll `/api/v1/stores/{id}/invoices/{id}` on a 3-second interval so UX updates even if the webhook is delayed.
- Do not derive the satoshi amount from a stale BTC/USD rate cached longer than 60 seconds; Lightning invoices encode a fixed sat amount, so an outdated rate creates under- or over-charges.
- Do not reuse a BTCPay invoice ID as your internal order ID; BTCPay invoice IDs are not sequential and collisions are possible across stores.

## Gotchas

- BTCPay Server webhook signatures use HMAC-SHA256 with the secret you set in BTCPay → Store Settings → Webhooks, not the API key; confusing the two causes every webhook to return 403.
- Lightning invoices are non-refundable at the protocol level; implement a separate credit or on-chain refund flow for customer disputes.
- The `createHmac` import requires `nodejs_compat` in `wrangler.toml` (`compatibility_flags = ["nodejs_compat"]`) with a `compatibility_date` of 2024-09-23 or later.

## Verification

```bash
# Create a test invoice (BTCPay testnet store)
curl -X POST "$BTCPAY_BASE_URL/api/v1/stores/$BTCPAY_STORE_ID/invoices" \
  -H "Authorization: token $BTCPAY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"amount":"1000","currency":"SATS","orderId":"test-001","itemDesc":"Test order"}'

# Simulate a settled webhook locally
curl -X POST http://localhost:8787/webhook/lightning \
  -H "Content-Type: application/json" \
  -H "BTCPay-Sig: sha256=$(echo -n '{"type":"InvoiceSettled","invoiceId":"abc123"}' | openssl dgst -sha256 -hmac "$BTCPAY_WEBHOOK_SECRET" -hex | awk '{print $2}')" \
  -d '{"type":"InvoiceSettled","invoiceId":"abc123"}'
```

## Related

- `payments/crypto-payments-integration.md`
- `payments/crypto-confirmation-depth-finality.md`
- `payments/idempotency-keys-payment-apis.md`

## Sources

- https://docs.btcpayserver.org/API/Greenfield/v1/#tag/Invoices/operation/Invoices_CreateInvoice
- https://docs.btcpayserver.org/Webhooks/
- https://github.com/lightningnetwork/lnd/blob/master/docs/rest/README.md
