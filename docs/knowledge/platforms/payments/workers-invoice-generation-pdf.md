# Invoice Generation and PDF Serving from Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

After a payment is captured, customers need a downloadable, legally compliant PDF invoice. Generating invoices on a traditional server adds latency and cold-start risk. You want instant, edge-generated PDFs stored in R2, accessible via short-lived signed URLs, and optionally emailed via MailChannels — all without a separate backend service.

---

## Context

The pipeline is:
1. A Stripe webhook fires `payment_intent.succeeded`.
2. A Worker fetches order records from D1, builds a structured `InvoiceData` object.
3. HTML is rendered from a template literal and converted to PDF via Cloudflare's Browser Rendering API (or stored as HTML-in-R2 as a fallback).
4. The PDF is written to R2 at `invoices/{customerId}/{invoiceId}.pdf`.
5. A signed R2 URL (1-hour TTL) is returned to the caller or embedded in an email.

---

## Solution

```typescript
// workers-invoice/src/index.ts

import { Env } from './types';
import { fetchOrderData, OrderRecord } from './data';
import { buildInvoiceHtml } from './template';
import { uploadToR2, getSignedUrl } from './storage';
import { sendInvoiceEmail } from './email';

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // POST /invoices — generate and store
    if (request.method === 'POST' && url.pathname === '/invoices') {
      return handleGenerate(request, env, ctx);
    }

    // GET /invoices/:invoiceId/download — return signed URL
    const match = url.pathname.match(/^\/invoices\/([^/]+)\/download$/);
    if (request.method === 'GET' && match) {
      return handleDownload(match[1], env);
    }

    return new Response('Not Found', { status: 404 });
  },
};

// ── Generate ──────────────────────────────────────────────────────────────────
async function handleGenerate(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
): Promise<Response> {
  const { orderId, sendEmail } = await request.json<{
    orderId: string;
    sendEmail?: boolean;
  }>();

  const order = await fetchOrderData(env.DB, orderId);
  if (!order) return new Response('Order not found', { status: 404 });

  const invoiceId = `INV-${order.id.toUpperCase()}`;
  const html = buildInvoiceHtml(invoiceId, order);

  // Convert HTML → PDF via Browser Rendering API
  const pdfBuffer = await htmlToPdf(env, html);

  // Store in R2
  const r2Key = `invoices/${order.customerId}/${invoiceId}.pdf`;
  await uploadToR2(env.INVOICES_BUCKET, r2Key, pdfBuffer);

  // Persist invoice record in D1
  await env.DB
    .prepare(
      `INSERT OR REPLACE INTO invoices
         (invoice_id, order_id, customer_id, r2_key, created_at)
       VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)`,
    )
    .bind(invoiceId, orderId, order.customerId, r2Key)
    .run();

  if (sendEmail) {
    const signedUrl = await getSignedUrl(env.INVOICES_BUCKET, r2Key, 3600);
    ctx.waitUntil(sendInvoiceEmail(env, order, invoiceId, signedUrl));
  }

  return Response.json({ invoiceId });
}

// ── Download ──────────────────────────────────────────────────────────────────
async function handleDownload(invoiceId: string, env: Env): Promise<Response> {
  const row = await env.DB
    .prepare('SELECT r2_key FROM invoices WHERE invoice_id = ?')
    .bind(invoiceId)
    .first<{ r2_key: string }>();

  if (!row) return new Response('Not found', { status: 404 });

  const signedUrl = await getSignedUrl(env.INVOICES_BUCKET, row.r2_key, 3600);
  return Response.json({ url: signedUrl, expiresInSeconds: 3600 });
}

// ── PDF via Browser Rendering ────────────────────────────────────────────────
async function htmlToPdf(env: Env, html: string): Promise<ArrayBuffer> {
  // env.BROWSER is a BrowserWorker binding (Browser Rendering API)
  const browser = await env.BROWSER.fetch(
    new Request('https://browser.rendering.internal/pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        html,
        options: { format: 'A4', printBackground: true },
      }),
    }),
  );
  if (!browser.ok) throw new Error(`PDF render failed: ${browser.status}`);
  return browser.arrayBuffer();
}
```

```typescript
// workers-invoice/src/data.ts

export interface OrderRecord {
  id: string;
  customerId: string;
  customerName: string;
  customerEmail: string;
  billingAddress: string;
  lineItems: LineItem[];
  subtotalCents: number;
  taxCents: number;
  totalCents: number;
  currency: string;
  paidAt: string;
}

export interface LineItem {
  description: string;
  quantity: number;
  unitCents: number;
  totalCents: number;
}

export async function fetchOrderData(
  db: D1Database,
  orderId: string,
): Promise<OrderRecord | null> {
  const order = await db
    .prepare(`SELECT * FROM orders WHERE id = ?`)
    .bind(orderId)
    .first<Omit<OrderRecord, 'lineItems'>>();

  if (!order) return null;

  const items = await db
    .prepare(`SELECT * FROM order_line_items WHERE order_id = ?`)
    .bind(orderId)
    .all<LineItem>();

  return { ...order, lineItems: items.results };
}
```

```typescript
// workers-invoice/src/template.ts

import { OrderRecord } from './data';

export function buildInvoiceHtml(invoiceId: string, order: OrderRecord): string {
  const formatMoney = (cents: number, currency: string) =>
    new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(cents / 100);

  const lineItemRows = order.lineItems
    .map(
      (item) => `
      <tr>
        <td>${escHtml(item.description)}</td>
        <td class="num">${item.quantity}</td>
        <td class="num">${formatMoney(item.unitCents, order.currency)}</td>
        <td class="num">${formatMoney(item.totalCents, order.currency)}</td>
      </tr>`,
    )
    .join('');

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <style>
    body { font-family: 'Helvetica Neue', Arial, sans-serif; color: #1a1a1a; padding: 48px; }
    h1   { font-size: 28px; margin-bottom: 4px; }
    .meta { color: #555; font-size: 13px; margin-bottom: 32px; }
    table { width: 100%; border-collapse: collapse; margin-top: 24px; }
    th { background: #f4f4f4; padding: 10px 12px; text-align: left; font-size: 12px; text-transform: uppercase; }
    td { padding: 10px 12px; border-bottom: 1px solid #e8e8e8; font-size: 14px; }
    .num { text-align: right; }
    .totals td { font-weight: 600; }
    .total-row td { font-size: 16px; color: #000; }
  </style>
</head>
<body>
  <h1>Invoice ${escHtml(invoiceId)}</h1>
  <div class="meta">
    <strong>Bill to:</strong> ${escHtml(order.customerName)} · ${escHtml(order.customerEmail)}<br/>
    ${escHtml(order.billingAddress)}<br/>
    Paid: ${new Date(order.paidAt).toLocaleDateString('en-US', { dateStyle: 'long' })}
  </div>
  <table>
    <thead><tr><th>Description</th><th class="num">Qty</th><th class="num">Unit Price</th><th class="num">Total</th></tr></thead>
    <tbody>${lineItemRows}</tbody>
    <tfoot>
      <tr class="totals"><td colspan="3">Subtotal</td><td class="num">${formatMoney(order.subtotalCents, order.currency)}</td></tr>
      <tr class="totals"><td colspan="3">Tax</td><td class="num">${formatMoney(order.taxCents, order.currency)}</td></tr>
      <tr class="totals total-row"><td colspan="3"><strong>Total</strong></td><td class="num">${formatMoney(order.totalCents, order.currency)}</td></tr>
    </tfoot>
  </table>
</body>
</html>`;
}

function escHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
```

```typescript
// workers-invoice/src/storage.ts

export async function uploadToR2(
  bucket: R2Bucket,
  key: string,
  body: ArrayBuffer,
): Promise<void> {
  await bucket.put(key, body, {
    httpMetadata: { contentType: 'application/pdf' },
    customMetadata: { uploadedAt: new Date().toISOString() },
  });
}

export async function getSignedUrl(
  bucket: R2Bucket,
  key: string,
  expiresInSeconds: number,
): Promise<string> {
  // R2 presigned URLs require the R2 REST API; Workers bindings expose
  // createSignedUrl via the compatibility flag r2_presigned_urls.
  return bucket.createSignedUrl(key, { expiresIn: expiresInSeconds });
}
```

```typescript
// workers-invoice/src/email.ts

import { OrderRecord } from './data';

export async function sendInvoiceEmail(
  env: { MAILCHANNELS_API_KEY: string },
  order: OrderRecord,
  invoiceId: string,
  downloadUrl: string,
): Promise<void> {
  await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Auth-Token': env.MAILCHANNELS_API_KEY,
    },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: order.customerEmail, name: order.customerName }] }],
      from: { email: 'billing@example.com', name: 'Orchords Billing' },
      subject: `Your invoice ${invoiceId}`,
      content: [{
        type: 'text/html',
        value: `<p>Hi ${order.customerName},</p><p>Your invoice <strong>${invoiceId}</strong> is ready. <a >Download PDF</a> (link valid for 1 hour).</p>`,
      }],
    }),
  });
}
```

---

## Implementation Details

**wrangler.toml**:
```toml
[browser]
binding = "BROWSER"

[[r2_buckets]]
binding = "INVOICES_BUCKET"
bucket_name = "invoices"

[[d1_databases]]
binding = "DB"
database_name = "payments"
database_id   = "<D1_ID>"

[vars]
MAILCHANNELS_API_KEY = "<secret>"
```

**D1 schema**:
```sql
CREATE TABLE invoices (
  invoice_id  TEXT PRIMARY KEY,
  order_id    TEXT NOT NULL,
  customer_id TEXT NOT NULL,
  r2_key      TEXT NOT NULL,
  created_at  TEXT NOT NULL
);
CREATE INDEX idx_inv_customer ON invoices (customer_id, created_at);
```

**R2 CORS** — if customers download directly from R2 public URL, configure a CORS policy on the bucket. For signed URLs, CORS is not needed because the Worker proxies the redirect.

---

## Anti-patterns

- **Do not stream the PDF back inline** from the Worker response — R2 storage decouples generation from retrieval and allows repeated downloads without re-rendering.
- **Do not store raw HTML in R2** as a long-term invoice artifact — HTML can be altered client-side; the rendered PDF is the canonical record.
- **Do not issue permanent public R2 URLs** — pre-signed URLs with short TTL prevent unauthorised invoice sharing.
- **Do not skip idempotency** — check `SELECT invoice_id FROM invoices WHERE order_id = ?` before regenerating; a duplicate webhook must not produce a second file.

---

## Gotchas

- The Browser Rendering API is billed per render and has concurrency limits. Cache the PDF in R2 immediately; never re-render on every download request.
- `r2_presigned_urls` compatibility flag must be enabled in `wrangler.toml` (`compatibility_flags = ["r2_presigned_urls"]`) or `createSignedUrl` will throw.
- MailChannels DKIM signing requires an SPF/DKIM record for your sending domain; without it deliverability is low.
- `waitUntil` for email means the HTTP response is returned before the email is confirmed sent — implement a separate retry mechanism for email failures.

---

## Verification

```bash
# Generate an invoice
curl -X POST https://invoice-worker.example.com/invoices \
  -H 'Content-Type: application/json' \
  -d '{"orderId": "ord_abc123", "sendEmail": false}'
# → { "invoiceId": "INV-ORD_ABC123" }

# Get signed download URL
curl https://invoice-worker.example.com/invoices/INV-ORD_ABC123/download
# → { "url": "https://...", "expiresInSeconds": 3600 }

# Confirm PDF in R2
npx wrangler r2 object get invoices invoices/cus_xyz/INV-ORD_ABC123.pdf --local
```

---

## Related

- `documentation/docs/policies/payments/workers-split-payment-marketplace.md`
- `documentation/docs/policies/payments/subscription-billing.md`
- `documentation/docs/policies/payments/tax-calculation-edge.md`
- Cloudflare Browser Rendering API: https://developers.cloudflare.com/browser-rendering/
- Cloudflare R2: https://developers.cloudflare.com/r2/

---

## Sources

- https://developers.cloudflare.com/browser-rendering/
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://mailchannels.zendesk.com/hc/en-us/articles/4565898358541
- https://developers.cloudflare.com/d1/
