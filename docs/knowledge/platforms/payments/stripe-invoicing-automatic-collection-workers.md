# Stripe Invoicing Automatic Collection on Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You need to issue Stripe Invoices for one-off charges or milestone billing (not subscription-based) and have Stripe automatically attempt collection from the customer's default payment method, retry on failure, and call your Workers webhook so you can update order state and trigger downstream fulfilment without building your own dunning loop.

## Context

Stripe Invoices with `collection_method: "charge_automatically"` and `auto_advance: true` become `open` and then immediately attempt payment via the customer's `invoice_settings.default_payment_method`. On failure, Stripe's Smart Retries reschedule attempts; the invoice transitions through `open → paid` or `open → uncollectible`. Workers listens for `invoice.paid`, `invoice.payment_failed`, and `invoice.marked_uncollectible` events and drives the fulfilment state machine. The `Customer` object must have a saved payment method and billing email before you finalise the invoice or collection silently skips.

## Create and Finalise an Invoice

```typescript
// src/handlers/create-invoice.ts
import Stripe from "stripe";

export interface Env {
  STRIPE_SECRET_KEY: string;
  STRIPE_WEBHOOK_SECRET: string;
}

interface InvoiceLineItem {
  description: string;
  amount: number; // cents
  quantity: number;
}

export async function createAndFinaliseInvoice(
  customerId: string,
  lines: InvoiceLineItem[],
  metadata: Record<string, string>,
  env: Env
): Promise<Stripe.Invoice> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY, {
    apiVersion: "2025-04-30.basil",
    httpClient: Stripe.createFetchHttpClient(),
  });

  // 1. Create the invoice shell
  const invoice = await stripe.invoices.create({
    customer: customerId,
    collection_method: "charge_automatically",
    auto_advance: false, // we control finalisation explicitly
    metadata,
    days_until_due: 0, // for charge_automatically this is informational
  });

  // 2. Add line items
  await Promise.all(
    lines.map((line) =>
      stripe.invoiceItems.create({
        customer: customerId,
        invoice: invoice.id,
        description: line.description,
        amount: line.amount,
        currency: "usd",
        quantity: line.quantity,
      })
    )
  );

  // 3. Finalise → triggers auto_advance → Stripe attempts collection
  const finalised = await stripe.invoices.finalizeInvoice(invoice.id, {
    auto_advance: true,
  });

  return finalised;
}
```

## Webhook Handler — Drive Fulfilment State Machine

```typescript
// src/handlers/invoice-webhook.ts
import Stripe from "stripe";

export async function handleInvoiceWebhook(
  request: Request,
  env: Env & { DB: D1Database }
): Promise<Response> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY, {
    apiVersion: "2025-04-30.basil",
    httpClient: Stripe.createFetchHttpClient(),
  });

  const sig = request.headers.get("stripe-signature") ?? "";
  const rawBody = await request.text();

  let event: Stripe.Event;
  try {
    event = await stripe.webhooks.constructEventAsync(
      rawBody,
      sig,
      env.STRIPE_WEBHOOK_SECRET
    );
  } catch {
    return new Response("Invalid signature", { status: 400 });
  }

  // Idempotency: skip already-processed events
  const existing = await env.DB.prepare(
    "SELECT 1 FROM processed_events WHERE event_id = ?"
  )
    .bind(event.id)
    .first();
  if (existing) return new Response("Already processed", { status: 200 });

  const invoice = event.data.object as Stripe.Invoice;
  const orderId = invoice.metadata?.orderId ?? null;

  if (event.type === "invoice.paid") {
    await env.DB.batch([
      env.DB.prepare(
        `UPDATE orders SET payment_status = 'paid', paid_at = unixepoch(),
         stripe_invoice_id = ? WHERE id = ?`
      ).bind(invoice.id, orderId),
      env.DB.prepare(
        "INSERT INTO processed_events (event_id, processed_at) VALUES (?, unixepoch())"
      ).bind(event.id),
    ]);
    // trigger fulfilment queue here if needed
  }

  if (event.type === "invoice.payment_failed") {
    const attempt = invoice.attempt_count ?? 1;
    await env.DB.batch([
      env.DB.prepare(
        `UPDATE orders SET payment_status = 'retrying', last_attempt_at = unixepoch(),
         attempt_count = ? WHERE id = ?`
      ).bind(attempt, orderId),
      env.DB.prepare(
        "INSERT INTO processed_events (event_id, processed_at) VALUES (?, unixepoch())"
      ).bind(event.id),
    ]);
  }

  if (event.type === "invoice.marked_uncollectible") {
    await env.DB.batch([
      env.DB.prepare(
        "UPDATE orders SET payment_status = 'uncollectible' WHERE id = ?"
      ).bind(orderId),
      env.DB.prepare(
        "INSERT INTO processed_events (event_id, processed_at) VALUES (?, unixepoch())"
      ).bind(event.id),
    ]);
  }

  return new Response("OK", { status: 200 });
}
```

## Void and Re-Issue an Invoice

```typescript
// src/handlers/invoice-void.ts
import Stripe from "stripe";

export async function voidAndReissue(
  invoiceId: string,
  newLines: Array<{ description: string; amount: number; quantity: number }>,
  env: Env & { DB: D1Database }
): Promise<Stripe.Invoice> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY, {
    apiVersion: "2025-04-30.basil",
    httpClient: Stripe.createFetchHttpClient(),
  });

  // Fetch original to get customer and metadata
  const original = await stripe.invoices.retrieve(invoiceId);
  if (original.status !== "open") {
    throw new Error(`Cannot void invoice in status: ${original.status}`);
  }

  await stripe.invoices.voidInvoice(invoiceId);

  // Create replacement
  return createAndFinaliseInvoice(
    original.customer as string,
    newLines,
    { ...original.metadata, reissuedFrom: invoiceId },
    env
  );
}

// Helper: manually mark uncollectible after custom retry exhaustion
export async function markUncollectible(invoiceId: string, env: Env): Promise<void> {
  const stripe = new Stripe(env.STRIPE_SECRET_KEY, {
    apiVersion: "2025-04-30.basil",
    httpClient: Stripe.createFetchHttpClient(),
  });
  await stripe.invoices.markUncollectible(invoiceId);
}
```

## Anti-patterns

- Do not set `auto_advance: true` during invoice creation and then call `finalizeInvoice`; Stripe may auto-finalise before your line items are added, sending a zero-amount invoice.
- Do not use `send_invoice` collection method when you want automatic retries; Stripe only retries card charges on `charge_automatically` invoices.
- Do not drive fulfilment from `invoice.finalized`; wait for `invoice.paid` — finalized merely means Stripe will attempt collection, not that it succeeded.

## Gotchas

- `invoice.attempt_count` is 0 on `invoice.payment_failed` when Stripe sends the event before the first attempt counter increments; always treat 0 as "attempt 1 failed".
- Voided invoices cannot be reopened; if you void and the customer pays in the meantime via an out-of-band method, the payment is not linked and reconciliation must be manual.
- The `metadata` field is not copied to `InvoiceItem` objects; store your `orderId` on the Invoice itself, not on individual line items, to reliably retrieve it from webhook events.

## Verification

```bash
# Create an invoice in test mode
stripe invoices create \
  --customer cus_test123 \
  --collection-method charge_automatically \
  --metadata '{"orderId":"order-001"}'

# Add a line item
stripe invoiceItems create \
  --customer cus_test123 \
  --invoice in_test123 \
  --amount 5000 \
  --currency usd \
  --description "Consulting fee"

# Finalize and trigger collection
stripe invoices finalize in_test123 --auto-advance

# Forward test webhook to local Worker
stripe listen --forward-to http://localhost:8787/webhooks/stripe \
  --events invoice.paid,invoice.payment_failed,invoice.marked_uncollectible
```

## Related

- `payments/stripe-dunning-management.md`
- `payments/stripe-smart-retries.md`
- `payments/stripe-webhook-idempotency-d1-event-log.md`

## Sources

- https://docs.stripe.com/invoicing/automatic-collection
- https://docs.stripe.com/api/invoices/create
- https://docs.stripe.com/billing/invoices/workflow
