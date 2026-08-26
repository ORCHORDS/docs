# Dynamic PDF Attachment Generation in Workers with R2 and Transactional Email

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Customers need invoice or report PDFs attached to their transactional emails.
Generating PDFs server-side traditionally requires a Node.js process running
puppeteer or a heavy PDF library, but Cloudflare Workers have no headless browser
and limited native PDF support. The pattern below composes a PDF using the
`pdf-lib` WebAssembly-compatible library, stores the result in R2, and attaches
it to an email sent via Resend or MailChannels.

## Context

`pdf-lib` (https://pdf-lib.js.org) is a pure-JavaScript PDF creation and
modification library with no native dependencies—it runs inside Workers. For
complex invoice layouts, generate an HTML template first, then render it to PDF
via a dedicated rendering service (e.g., Browserless, Gotenberg) called over
HTTPS from the Worker. Store the generated PDF in R2 with a short-lived signed
URL for download, and attach the bytes directly to the email.

## Approach 1: pdf-lib (Simple Invoices, No External Service)

```typescript
// src/pdf-invoice.ts
import { PDFDocument, rgb, StandardFonts } from "pdf-lib";

export interface InvoiceData {
  invoiceNumber: string;
  customerName: string;
  amount: number;
  currency: string;
  lineItems: { description: string; quantity: number; unitPrice: number }[];
  issuedAt: string;
}

export async function generateInvoicePdf(data: InvoiceData): Promise<Uint8Array> {
  const pdfDoc = await PDFDocument.create();
  const page = pdfDoc.addPage([595, 842]); // A4 in points
  const font = await pdfDoc.embedFont(StandardFonts.HelveticaBold);
  const bodyFont = await pdfDoc.embedFont(StandardFonts.Helvetica);

  const { height } = page.getSize();
  let y = height - 60;

  // Header
  page.drawText("INVOICE", { x: 50, y, size: 24, font, color: rgb(0.1, 0.1, 0.6) });
  y -= 30;
  page.drawText(`Invoice #${data.invoiceNumber}`, { x: 50, y, size: 11, font: bodyFont });
  y -= 16;
  page.drawText(`Issued: ${data.issuedAt}`, { x: 50, y, size: 10, font: bodyFont });
  y -= 16;
  page.drawText(`Bill to: ${data.customerName}`, { x: 50, y, size: 10, font: bodyFont });
  y -= 30;

  // Line items header
  page.drawText("Description", { x: 50, y, size: 10, font });
  page.drawText("Qty", { x: 320, y, size: 10, font });
  page.drawText("Unit Price", { x: 380, y, size: 10, font });
  page.drawText("Total", { x: 470, y, size: 10, font });
  y -= 16;
  page.drawLine({ start: { x: 50, y }, end: { x: 545, y },
                  thickness: 0.5, color: rgb(0.4, 0.4, 0.4) });
  y -= 14;

  let subtotal = 0;
  for (const item of data.lineItems) {
    const lineTotal = item.quantity * item.unitPrice;
    subtotal += lineTotal;
    page.drawText(item.description.slice(0, 40), { x: 50, y, size: 9, font: bodyFont });
    page.drawText(String(item.quantity), { x: 320, y, size: 9, font: bodyFont });
    page.drawText(`${data.currency} ${item.unitPrice.toFixed(2)}`, { x: 380, y, size: 9, font: bodyFont });
    page.drawText(`${data.currency} ${lineTotal.toFixed(2)}`, { x: 470, y, size: 9, font: bodyFont });
    y -= 14;
  }

  y -= 10;
  page.drawText(`Total: ${data.currency} ${subtotal.toFixed(2)}`, {
    x: 400, y, size: 13, font, color: rgb(0.1, 0.1, 0.6),
  });

  return pdfDoc.save();
}
```

Install: `npm install pdf-lib` – it is ESM-compatible and runs in Workers.

## Store PDF in R2

```typescript
// src/store-pdf.ts
interface Env {
  INVOICES_R2: R2Bucket;
}

export async function storePdfInR2(
  env: Env,
  pdfBytes: Uint8Array,
  invoiceId: string
): Promise<string> {
  const key = `invoices/${invoiceId}.pdf`;
  await env.INVOICES_R2.put(key, pdfBytes, {
    httpMetadata: { contentType: "application/pdf" },
    customMetadata: { invoiceId },
  });
  return key;
}

export async function getPdfBytes(env: Env, key: string): Promise<Uint8Array | null> {
  const obj = await env.INVOICES_R2.get(key);
  if (!obj) return null;
  return new Uint8Array(await obj.arrayBuffer());
}
```

## Attach PDF and Send via Resend

```typescript
// src/send-invoice-email.ts
import { generateInvoicePdf, InvoiceData } from "./pdf-invoice";
import { storePdfInR2 } from "./store-pdf";

interface Env {
  INVOICES_R2: R2Bucket;
  RESEND_API_KEY: string;
}

export async function sendInvoiceEmail(
  env: Env,
  invoice: InvoiceData,
  recipientEmail: string
): Promise<void> {
  const pdfBytes = await generateInvoicePdf(invoice);
  const r2Key = await storePdfInR2(env, pdfBytes, invoice.invoiceNumber);

  // Encode for Resend attachment (base64)
  const base64Pdf = btoa(String.fromCharCode(...pdfBytes));

  const payload = {
    from: "billing@example.com",
    to: recipientEmail,
    subject: `Invoice #${invoice.invoiceNumber} from example project`,
    html: `<p>Please find your invoice attached.</p>
           <p><strong>Amount: ${invoice.currency} ${invoice.amount.toFixed(2)}</strong></p>`,
    attachments: [
      {
        filename: `invoice-${invoice.invoiceNumber}.pdf`,
        content: base64Pdf,
      },
    ],
  };

  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(`Resend ${res.status}: ${await res.text()}`);
  }
}
```

## Approach 2: Gotenberg (Complex Layouts)

For pixel-perfect HTML-to-PDF conversion:

```typescript
// src/gotenberg-pdf.ts
export async function htmlToPdf(html: string, gotenbergUrl: string): Promise<Uint8Array> {
  const form = new FormData();
  form.append("files", new Blob([html], { type: "text/html" }), "index.html");

  const res = await fetch(`${gotenbergUrl}/forms/chromium/convert/html`, {
    method: "POST",
    body: form,
    headers: { "Gotenberg-Output-Filename": "output.pdf" },
  });

  if (!res.ok) throw new Error(`Gotenberg ${res.status}: ${await res.text()}`);
  return new Uint8Array(await res.arrayBuffer());
}
```

Deploy Gotenberg as a Cloudflare Container or a sidecar service accessible over
the internal network; do not call untrusted external PDF renderers with customer
invoice data.

## R2 Lifecycle / Retention

```toml
# wrangler.toml — lifecycle rules via R2 API (set programmatically)
# Invoices are retained 7 years for compliance; set no auto-delete rule.
# Temporary render cache files can have a 24h lifecycle via R2 object expiry.
```

Delete temporary render artefacts explicitly after sending:

```typescript
await env.INVOICES_R2.delete(`tmp/${invoiceId}.html`);
```

## Anti-patterns

- **Attaching PDFs larger than 10 MB** – most ESPs reject attachments over 10 MB;
  for large reports, store in R2 and include a signed download link instead of
  attaching the bytes.
- **Re-generating the PDF on every email open** – generate once, store in R2, serve
  the stored copy; re-generation wastes CPU and risks drift if data changes.
- **Calling Gotenberg over public internet** – route via a private tunnel or
  Cloudflare Zero Trust service token to prevent PDF generation abuse.

## Gotchas

- `pdf-lib` does not support font subsetting for non-Latin scripts (CJK, Arabic).
  For multilingual invoices, use Gotenberg with a full Chromium font stack.
- Resend limits attachment size to 40 MB per email; base64 expansion adds ~33%
  overhead—a 30 MB PDF exceeds the limit as base64.
- Workers CPU time limit (50 ms on the free plan, 30 s on paid) may be exceeded
  by complex PDF generation; offload to a Queue consumer Worker if needed.

## Verification

```bash
# Invoke the invoice Worker locally
wrangler dev src/send-invoice-email.ts

curl -X POST http://localhost:8787/invoice \
  -H "Content-Type: application/json" \
  -d '{
    "recipientEmail": "test@example.com",
    "invoice": {
      "invoiceNumber": "INV-0042",
      "customerName": "Acme Corp",
      "amount": 299.00,
      "currency": "USD",
      "issuedAt": "2026-08-23",
      "lineItems": [
        {"description": "Pro Plan – August 2026", "quantity": 1, "unitPrice": 299.00}
      ]
    }
  }'

# Verify PDF stored in R2
wrangler r2 object get invoices-bucket invoices/INV-0042.pdf --file /tmp/check.pdf
open /tmp/check.pdf
```

## Related

- `email-attachment-patterns.md`
- `email-attachment-scanning-r2-workers-ai.md`
- `email-transactional-template-personalization-r2-workers.md`
- `invoice-email-template.md`
- `email-archiving-compliance-retention-r2.md`

## Sources

- pdf-lib documentation: https://pdf-lib.js.org/
- Cloudflare R2 docs: https://developers.cloudflare.com/r2/
- Resend attachment API: https://resend.com/docs/api-reference/emails/send-email#body-parameters
- Gotenberg: https://gotenberg.dev/
- Cloudflare Workers limits: https://developers.cloudflare.com/workers/platform/limits/
