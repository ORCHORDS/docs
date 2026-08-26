# Invoice PDF Generation and Storage in R2 via Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

After a payment is confirmed, your platform must generate a branded PDF invoice, store it durably, and return a time-limited download link to the customer. Generating PDFs on demand inside a Worker keeps infrastructure simple—no Lambda, no separate PDF microservice. The generated file is stored in R2 and a signed URL is returned; the D1 `invoices` table tracks generation status so you can requeue failures and avoid duplicate generation.

---

## Context

Workers support `@react-pdf/renderer` compiled into a Workers-compatible bundle (no DOM dependency). The renderer's `pdf()` function returns a `ReadableStream<Uint8Array>` which can be piped directly to R2's `put()` method. Order data is fetched from D1 before rendering. The R2 bucket is private; download links are generated with `bucket.createSignedUrl()` using a 1-hour expiry. The `invoices` D1 table records `status` (`generating`, `ready`, `failed`) and the R2 object key, enabling idempotent regeneration and admin requeue flows. Invoice generation is triggered by the `checkout.session.completed` webhook (or equivalent) via a `waitUntil` call so the webhook response returns immediately.

---

## Section 1 — D1 Schema

```sql
CREATE TABLE IF NOT EXISTS orders (
  id           TEXT PRIMARY KEY,
  customer_email TEXT,
  amount_cents INTEGER NOT NULL,
  currency     TEXT    NOT NULL DEFAULT 'usd',
  status       TEXT    NOT NULL DEFAULT 'pending',
  completed_at TEXT
);

CREATE TABLE IF NOT EXISTS order_items (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id    TEXT    NOT NULL REFERENCES orders(id),
  description TEXT    NOT NULL,
  quantity    INTEGER NOT NULL,
  unit_price  INTEGER NOT NULL  -- in cents
);

CREATE TABLE IF NOT EXISTS invoices (
  id           TEXT PRIMARY KEY,        -- UUID
  order_id     TEXT NOT NULL UNIQUE REFERENCES orders(id),
  status       TEXT NOT NULL DEFAULT 'generating',  -- generating | ready | failed
  r2_key       TEXT,                    -- set when ready
  generated_at TEXT,
  error        TEXT                     -- last error message if failed
);

CREATE INDEX IF NOT EXISTS idx_invoices_order ON invoices(order_id);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
```

```bash
wrangler d1 create invoice-db
wrangler d1 execute invoice-db --file schema.sql
```

---

## Section 2 — Worker Implementation

```typescript
import { Document, Page, Text, View, StyleSheet, pdf } from "@react-pdf/renderer";
import React from "react";

export interface Env {
  DB: D1Database;
  INVOICE_BUCKET: R2Bucket;
  STORE_NAME: string;
  STORE_ADDRESS: string;
  SIGNED_URL_TTL_SECONDS: string; // e.g. "3600"
}

// ----- PDF template -----

const styles = StyleSheet.create({
  page: { padding: 40, fontSize: 12, fontFamily: "Helvetica" },
  header: { fontSize: 24, marginBottom: 20, color: "#1a1a2e" },
  section: { marginBottom: 12 },
  row: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 4 },
  bold: { fontFamily: "Helvetica-Bold" },
  divider: { borderBottomWidth: 1, borderBottomColor: "#cccccc", marginVertical: 8 },
  total: { flexDirection: "row", justifyContent: "space-between", marginTop: 12 },
});

interface OrderItem {
  description: string;
  quantity: number;
  unit_price: number;
}

interface OrderData {
  id: string;
  customer_email: string;
  amount_cents: number;
  currency: string;
  completed_at: string;
  items: OrderItem[];
}

function InvoiceDocument({ order, storeName, storeAddress }: {
  order: OrderData;
  storeName: string;
  storeAddress: string;
}) {
  const total = (order.amount_cents / 100).toFixed(2);
  return (
    <Document>
      <Page size="A4" style={styles.page}>
        <Text style={styles.header}>Invoice</Text>

        <View style={styles.section}>
          <Text style={styles.bold}>{storeName}</Text>
          <Text>{storeAddress}</Text>
        </View>

        <View style={styles.section}>
          <Text style={styles.bold}>Bill To</Text>
          <Text>{order.customer_email}</Text>
        </View>

        <View style={styles.section}>
          <Text>Order ID: {order.id}</Text>
          <Text>Date: {new Date(order.completed_at).toLocaleDateString()}</Text>
        </View>

        <View style={styles.divider} />

        {order.items.map((item, i) => (
          <View key={i} style={styles.row}>
            <Text>{item.description} x{item.quantity}</Text>
            <Text>
              {order.currency.toUpperCase()}{" "}
              {((item.unit_price * item.quantity) / 100).toFixed(2)}
            </Text>
          </View>
        ))}

        <View style={styles.divider} />

        <View style={styles.total}>
          <Text style={styles.bold}>Total</Text>
          <Text style={styles.bold}>
            {order.currency.toUpperCase()} {total}
          </Text>
        </View>
      </Page>
    </Document>
  );
}

// ----- D1 helpers -----

async function fetchOrderData(db: D1Database, orderId: string): Promise<OrderData | null> {
  const order = await db
    .prepare("SELECT * FROM orders WHERE id = ?")
    .bind(orderId)
    .first<Omit<OrderData, "items">>();
  if (!order) return null;

  const { results: items } = await db
    .prepare("SELECT description, quantity, unit_price FROM order_items WHERE order_id = ?")
    .bind(orderId)
    .all<OrderItem>();

  return { ...order, items: items ?? [] };
}

async function upsertInvoiceRecord(
  db: D1Database,
  invoiceId: string,
  orderId: string,
  status: "generating" | "ready" | "failed",
  r2Key?: string,
  error?: string
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO invoices (id, order_id, status, r2_key, generated_at, error)
       VALUES (?, ?, ?, ?, ?, ?)
       ON CONFLICT(order_id) DO UPDATE SET
         status = excluded.status,
         r2_key = excluded.r2_key,
         generated_at = excluded.generated_at,
         error = excluded.error`
    )
    .bind(
      invoiceId,
      orderId,
      status,
      r2Key ?? null,
      status === "ready" ? new Date().toISOString() : null,
      error ?? null
    )
    .run();
}

// ----- Core generation -----

async function generateAndStoreInvoice(
  orderId: string,
  env: Env
): Promise<string> {
  const order = await fetchOrderData(env.DB, orderId);
  if (!order) throw new Error(`Order not found: ${orderId}`);

  const invoiceId = crypto.randomUUID();
  const r2Key = `invoices/${order.id}/${invoiceId}.pdf`;

  await upsertInvoiceRecord(env.DB, invoiceId, orderId, "generating");

  try {
    const element = React.createElement(InvoiceDocument, {
      order,
      storeName: env.STORE_NAME,
      storeAddress: env.STORE_ADDRESS,
    });

    const pdfBuffer = await pdf(element).toBuffer();

    await env.INVOICE_BUCKET.put(r2Key, pdfBuffer, {
      httpMetadata: { contentType: "application/pdf" },
      customMetadata: { orderId, invoiceId },
    });

    await upsertInvoiceRecord(env.DB, invoiceId, orderId, "ready", r2Key);
    return r2Key;
  } catch (err) {
    const msg = err instanceof Error ? err.message : "PDF generation failed";
    await upsertInvoiceRecord(env.DB, invoiceId, orderId, "failed", undefined, msg);
    throw err;
  }
}

async function getSignedUrl(bucket: R2Bucket, r2Key: string, ttl: number): Promise<string> {
  return bucket.createSignedUrl(r2Key, { expiresIn: ttl });
}

// ----- Request handlers -----

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // GET /invoices/:orderId — return signed URL (regenerate if needed)
    if (request.method === "GET" && url.pathname.startsWith("/invoices/")) {
      const orderId = url.pathname.split("/")[2];
      if (!orderId) return new Response("Missing orderId", { status: 400 });

      const existing = await env.DB
        .prepare("SELECT * FROM invoices WHERE order_id = ?")
        .bind(orderId)
        .first<{ status: string; r2_key: string | null }>();

      if (existing?.status === "ready" && existing.r2_key) {
        const ttl = parseInt(env.SIGNED_URL_TTL_SECONDS, 10);
        const signedUrl = await getSignedUrl(env.INVOICE_BUCKET, existing.r2_key, ttl);
        return new Response(JSON.stringify({ url: signedUrl }), {
          headers: { "Content-Type": "application/json" },
        });
      }

      // Trigger generation in background, return 202
      ctx.waitUntil(
        generateAndStoreInvoice(orderId, env).catch((e) =>
          console.error("Invoice generation failed:", e)
        )
      );

      return new Response(
        JSON.stringify({ message: "Invoice generation in progress" }),
        { status: 202, headers: { "Content-Type": "application/json" } }
      );
    }

    return new Response("Not Found", { status: 404 });
  },
};
```

---

## Section 3 — wrangler.toml R2 & D1 Bindings

```toml
name = "invoice-service"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding = "DB"
database_name = "invoice-db"
database_id = "<your-d1-database-id>"

[[r2_buckets]]
binding = "INVOICE_BUCKET"
bucket_name = "invoices"
```

```bash
# Create R2 bucket
wrangler r2 bucket create invoices

# Set secrets
wrangler secret put STORE_NAME
wrangler secret put STORE_ADDRESS
wrangler secret put SIGNED_URL_TTL_SECONDS  # e.g. 3600

# Deploy
wrangler deploy

# Retrieve a test invoice
curl https://<worker>.workers.dev/invoices/<order-id>
```

---

## Anti-patterns

- **Streaming PDF directly to the HTTP response** — While possible, it bypasses storage; the customer cannot re-download the same invoice without regenerating. Always write to R2 and return a signed URL.
- **Storing signed URLs in D1** — Signed URLs expire; storing them creates stale links. Store only the R2 object key and generate a fresh signed URL on each request.
- **Not tracking `generating` status in D1** — Without an intermediate state, concurrent requests for the same invoice trigger parallel PDF generation jobs, wasting CPU and potentially writing two R2 objects for the same order.
- **Using `pdf().toBlob()`** — `Blob` is less efficient in Workers; `toBuffer()` returns a `Uint8Array`-compatible buffer that R2's `put()` accepts directly.

---

## Gotchas

- `@react-pdf/renderer` must be bundled without its optional canvas/DOM peer dependencies. Add `node_compat = true` in `wrangler.toml` only if strictly required; prefer Workers-specific bundle flags to tree-shake Node internals.
- R2's `createSignedUrl` requires the bucket to be configured without public access. Public buckets do not support signed URLs.
- The `ON CONFLICT(order_id) DO UPDATE` upsert pattern requires SQLite 3.24+. D1 runs SQLite 3.46+, so this is safe.
- Workers CPU time limit is 30 ms (free tier) or 30 seconds (paid). Complex PDFs with many pages can exceed this; test with realistic invoice sizes.
- `@react-pdf/renderer` uses a custom layout engine, not a browser. CSS grid and flex gap are not fully supported; stick to `flexDirection`, `padding`, and absolute positioning.

---

## Verification

```bash
# Confirm R2 bucket exists
wrangler r2 bucket list

# Trigger invoice generation
curl https://<worker>.workers.dev/invoices/<order-id>
# Expect 202 on first call, then poll

# Second call returns signed URL
curl https://<worker>.workers.dev/invoices/<order-id>

# Verify R2 object was stored
wrangler r2 object get invoices invoices/<order-id>/<invoice-id>.pdf --file /tmp/invoice.pdf
open /tmp/invoice.pdf

# Confirm D1 invoice record
wrangler d1 execute invoice-db \
  --command "SELECT id, order_id, status, r2_key FROM invoices ORDER BY generated_at DESC LIMIT 5"
```

---

## Related

- `stripe-checkout-session-workers-d1.md`
- `workers-paypal-webhook-verification.md`
- `workers-google-pay-token-decryption.md`

---

## Sources

- @react-pdf/renderer — https://react-pdf.org/
- Cloudflare R2 — https://developers.cloudflare.com/r2/
- Cloudflare R2 Signed URLs — https://developers.cloudflare.com/r2/api/workers/workers-api-reference/#r2bucketcreatesignedurl
- Cloudflare D1 — https://developers.cloudflare.com/d1/
