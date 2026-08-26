# Workers CPU Time Limit Exceeded in Webhook Handler Incident

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom

Stripe webhook deliveries began returning HTTP 500 responses after a new "invoice finalized" handler was deployed. Stripe's dashboard showed delivery failures accumulating at a rate of ~200/min. Because Stripe retries failed webhooks, a backlog of ~40 k duplicate webhook events built up over 6 hours. The Workers error log showed: `Error: Worker exceeded CPU time limit.`

## Context

The `invoice.finalized` event triggers PDF invoice generation. The new handler used a pure-JavaScript PDF library (`jsPDF`) to render a multi-page invoice with embedded font data inside the Worker. On the first cold start the library parsed and registered embedded Base64 font files totaling ~1.8 MB. The Workers free-tier CPU time limit is 10 ms (Paid: 30 s); the Paid plan was in use with a 30 s wall-clock limit, but the CPU time consumed by the PDF generation exceeded 30 s of active CPU (not wall-clock) for invoices with more than ~15 line items.

---

## Root Cause: CPU-Intensive Work Cannot Run Inside a Worker Synchronously

Cloudflare Workers enforce a CPU time limit (not just wall-clock). Pure JS computation — PDF rendering, image encoding, complex template expansion — consumes CPU proportional to the work, with no way to yield. A Worker that exceeds the limit is terminated and returns a 1102 error internally mapped to a 500 by the runtime.

```typescript
// BEFORE — CPU-intensive PDF generation inside the Worker fetch handler
import jsPDF from "jspdf";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const event = await request.json<Stripe.Event>();
    if (event.type !== "invoice.finalized") {
      return new Response("ok");
    }

    const invoice = event.data.object as Stripe.Invoice;

    // This block burns > 30 s CPU for large invoices
    const doc = new jsPDF();
    for (const line of invoice.lines.data) {
      doc.text(`${line.description} — ${line.amount}`, 10, doc.lastAutoTable?.finalY ?? 10);
    }
    const pdfBytes = doc.output("arraybuffer");

    await env.BUCKET.put(`invoices/${invoice.id}.pdf`, pdfBytes);
    return new Response("ok");
  },
};
```

## Fix Step 1: Offload CPU Work to a Durable Object or Queue

Move the PDF generation out of the webhook handler. The handler's job is to acknowledge Stripe quickly and enqueue the work.

```typescript
// src/webhooks/stripe.ts  — fast ack, offload to queue
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const rawBody = await request.text();

    // Verify Stripe signature first (cheap, ~1 ms CPU)
    const sig = request.headers.get("stripe-signature") ?? "";
    const event = verifyStripeSignature(rawBody, sig, env.STRIPE_WEBHOOK_SECRET);
    if (!event) {
      return new Response("Unauthorized", { status: 401 });
    }

    if (event.type === "invoice.finalized") {
      // Enqueue for async processing — Worker returns 200 immediately
      await env.INVOICE_PDF_QUEUE.send({
        invoiceId: (event.data.object as { id: string }).id,
        attemptedAt: Date.now(),
      });
    }

    return new Response("ok"); // Stripe gets 200 within ~5 ms
  },
};
```

## Fix Step 2: Process PDFs in a Queues Consumer with Generous CPU Budget

Queues consumers run as separate Worker invocations with their own CPU clock. Break the PDF work into small awaitable chunks to avoid a single synchronous hot loop.

```typescript
// src/queues/invoice-pdf.ts
import { renderInvoicePdf } from "../lib/pdf-renderer";

export default {
  async queue(batch: MessageBatch<{ invoiceId: string }>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      try {
        const invoice = await fetchInvoiceFromStripe(msg.body.invoiceId, env);
        const pdfBytes = await renderInvoicePdf(invoice); // now async, yields between pages
        await env.BUCKET.put(`invoices/${invoice.id}.pdf`, pdfBytes);
        msg.ack();
      } catch (err) {
        console.error(JSON.stringify({ event: "pdf_render_failed", invoiceId: msg.body.invoiceId, err: String(err) }));
        msg.retry({ delaySeconds: 30 });
      }
    }
  },
};
```

## Fix Step 3: Yield Between Pages to Avoid CPU Spike

Even in a consumer, a synchronous loop over 50 pages can hit limits. Use `await scheduler.yield()` (Workers-supported) between chunks:

```typescript
// src/lib/pdf-renderer.ts
export async function renderInvoicePdf(
  invoice: StripeInvoice,
): Promise<ArrayBuffer> {
  const chunks: Uint8Array[] = [];

  for (let i = 0; i < invoice.lines.data.length; i++) {
    const line = invoice.lines.data[i];
    chunks.push(renderLine(line, i));

    // Yield CPU every 10 lines to avoid CPU time accumulation
    if (i % 10 === 0) {
      await scheduler.yield();
    }
  }

  return assemblePages(chunks);
}
```

## Fix Step 4: Add a CPU Time Budget Monitor via Startup Timing

There is no direct CPU time API in Workers, but wall-clock duration is a reasonable proxy. Log slow executions so you can detect regressions before they exceed limits:

```typescript
// src/lib/timed-exec.ts
export async function withCpuBudget<T>(
  label: string,
  budgetMs: number,
  fn: () => Promise<T>,
): Promise<T> {
  const start = performance.now();
  try {
    return await fn();
  } finally {
    const elapsed = performance.now() - start;
    if (elapsed > budgetMs) {
      console.warn(
        JSON.stringify({
          level: "warn",
          event: "cpu_budget_exceeded",
          label,
          elapsedMs: Math.round(elapsed),
          budgetMs,
        }),
      );
    }
  }
}

// Usage
const pdfBytes = await withCpuBudget("invoice-pdf-render", 5_000, () =>
  renderInvoicePdf(invoice),
);
```

## Fix Step 5: Drain the Retry Backlog Safely

After deploying the fix, Stripe's retry queue may deliver 40 k events in a burst. Apply idempotency so duplicate webhook events do not produce duplicate PDFs:

```typescript
// src/queues/invoice-pdf.ts (idempotent guard)
async function isPdfAlreadyGenerated(env: Env, invoiceId: string): Promise<boolean> {
  const obj = await env.BUCKET.head(`invoices/${invoiceId}.pdf`);
  return obj !== null;
}

// Inside the queue consumer
if (await isPdfAlreadyGenerated(env, invoice.id)) {
  msg.ack(); // already done, skip
  continue;
}
```

---

## Anti-Patterns

- **Running CPU-intensive synchronous JS (PDF generation, image resize, crypto key derivation) directly inside a fetch handler.** The Worker's CPU budget covers the entire request; there is no way to yield mid-function in a sync call stack.
- **Using a frontend PDF library (jsPDF, pdfmake) inside a Worker.** These libraries are designed for the browser with no thought for CPU budget. Use a server-oriented streaming approach or an external renderer.
- **Treating Stripe's 200 OK SLA as optional.** Stripe begins retry backoff after the first failure. A 30 s CPU-limit kill typically returns after >5 s, which Stripe counts as a failure.
- **Not having idempotency guards when a retry backlog can build up.** Draining 40 k retries without idempotency produces 40 k duplicate PDFs in R2.

## Gotchas

- Workers Paid plan CPU limit is 30 s of active CPU per invocation (not wall-clock). A Worker sleeping on `await fetch(...)` is not consuming CPU during the wait; CPU accumulates only during synchronous computation.
- `scheduler.yield()` is only available in the Workers runtime (not Node.js); miniflare supports it in local dev.
- Queues consumers have a separate 15-minute wall-clock limit and 30 s CPU limit per message batch invocation.
- Stripe webhook signatures use HMAC-SHA256 over the raw request body. You must read the body as raw bytes before parsing JSON; `request.json()` consumes the body stream.

## Verification

1. Stripe webhook dashboard shows 0 delivery failures after deploy.
2. Retry backlog drains within 4 hours with idempotency guards active (no duplicate PDFs in R2).
3. `invoice-pdf` queue consumer wall-clock p99 < 10 s per batch of 10 invoices.
4. `withCpuBudget` warnings absent from production logs for normal invoice sizes (≤ 50 line items).
5. Workers error log shows zero `Worker exceeded CPU time limit` events.

## Related

- `workers-cpu-time-premature-optimization.md`
- `queue-consumers-must-be-idempotent.md`
- `idempotency-keys-for-all-payment-calls.md`
- `workers-subrequest-limit-fan-out-exceeded-incident.md`
- `webhook-delivery-is-not-guaranteed.md`

## Sources

- Cloudflare Workers Limits — CPU Time: https://developers.cloudflare.com/workers/platform/limits/#cpu-time
- Cloudflare Queues Consumer Configuration: https://developers.cloudflare.com/queues/configuration/configure-queues/
- `scheduler.yield()` in Workers: https://developers.cloudflare.com/workers/runtime-apis/scheduler/
- Stripe Webhook Retries: https://stripe.com/docs/webhooks#retries
