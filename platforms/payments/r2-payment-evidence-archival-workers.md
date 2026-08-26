# R2 Payment Evidence Archival in Cloudflare Workers

**Date:** 2026-08-23
**Author:** example.com
**Status:** production

---

## Symptom / Use-case

A chargeback dispute arrives and you need to submit PDF receipts, invoice snapshots, and shipping-confirmation screenshots as evidence to the card network within 7 calendar days. The evidence files were never stored persistently — they were rendered on demand from live database state, which has since changed. Alternatively, a compliance audit requests 7 years of payment receipts and your current solution is a pile of emails or a non-searchable S3 bucket without Workers-accessible metadata indexing.

---

## Context

Cloudflare R2 is an S3-compatible object store with zero egress fees, accessible from Workers via the `R2Bucket` binding. It is the right primitive for payment evidence because:
- Objects are immutable after write (payment receipts must not be mutated post-issue).
- R2 supports custom metadata headers, used here to store `order_id`, `customer_id`, and `document_type`.
- Workers can write to R2 during the payment confirmation flow (no separate archival job needed).
- Pre-signed R2 URLs (via the S3-compatible API or `createPresignedUrl`) let you give dispute teams time-limited access without exposing a public bucket.

Evidence object types:
- `receipt` — HTML-rendered or PDF receipt generated at payment confirmation.
- `invoice` — pre-payment invoice snapshot.
- `dispute_evidence` — screenshots, communication records uploaded by your support team.

D1 stores an evidence manifest (object key, type, order ID, upload timestamp) for fast querying without listing the bucket.

---

## 1. Wrangler Binding Setup

```toml
# wrangler.toml
[[r2_buckets]]
binding = "PAYMENT_EVIDENCE"
bucket_name = "payment-evidence-prod"
preview_bucket_name = "payment-evidence-preview"

[[d1_databases]]
binding = "DB"
database_name = "payments"
database_id = "YOUR_D1_DATABASE_ID"
```

---

## 2. D1 Evidence Manifest Schema

```sql
-- migrations/0002_evidence_manifest.sql
CREATE TABLE IF NOT EXISTS payment_evidence (
  id             TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  order_id       TEXT NOT NULL,
  customer_id    TEXT NOT NULL,
  document_type  TEXT NOT NULL CHECK(document_type IN ('receipt','invoice','dispute_evidence')),
  r2_key         TEXT NOT NULL UNIQUE,
  content_type   TEXT NOT NULL DEFAULT 'application/pdf',
  size_bytes     INTEGER,
  uploaded_at    INTEGER NOT NULL DEFAULT (UNIXEPOCH()),
  uploaded_by    TEXT              -- user ID or 'system'
);

CREATE INDEX IF NOT EXISTS idx_pe_order    ON payment_evidence (order_id);
CREATE INDEX IF NOT EXISTS idx_pe_customer ON payment_evidence (customer_id, uploaded_at);
CREATE INDEX IF NOT EXISTS idx_pe_type     ON payment_evidence (document_type, uploaded_at);
```

---

## 3. Archiving a Payment Receipt at Confirmation

```typescript
// src/lib/evidence-archiver.ts
import type { Env } from '../types';

export interface ArchiveReceiptInput {
  orderId: string;
  customerId: string;
  pdfBytes: Uint8Array;   // rendered PDF blob
  issuedAt: Date;
}

/** Stores a PDF receipt in R2 and records its key in D1. Idempotent on orderId. */
export async function archiveReceipt(env: Env, input: ArchiveReceiptInput): Promise<string> {
  const { orderId, customerId, pdfBytes, issuedAt } = input;

  // Deterministic key: receipts/YYYY/MM/DD/<order_id>.pdf
  const dt = issuedAt.toISOString().slice(0, 10).replace(/-/g, '/');
  const key = `receipts/${dt}/${orderId}.pdf`;

  // Check manifest for idempotency — avoid overwriting an existing receipt
  const existing = await env.DB
    .prepare(`SELECT r2_key FROM payment_evidence WHERE r2_key = ?`)
    .bind(key)
    .first<{ r2_key: string }>();

  if (existing) return existing.r2_key; // already archived

  // Write to R2 with custom metadata
  await env.PAYMENT_EVIDENCE.put(key, pdfBytes, {
    httpMetadata: { contentType: 'application/pdf' },
    customMetadata: {
      order_id: orderId,
      customer_id: customerId,
      document_type: 'receipt',
      issued_at: issuedAt.toISOString(),
    },
  });

  // Record in D1 manifest
  await env.DB
    .prepare(
      `INSERT OR IGNORE INTO payment_evidence
         (order_id, customer_id, document_type, r2_key, content_type, size_bytes)
       VALUES (?, ?, 'receipt', ?, 'application/pdf', ?)`
    )
    .bind(orderId, customerId, key, pdfBytes.byteLength)
    .run();

  return key;
}
```

---

## 4. Serving Evidence with Signed Access

Internal dispute tooling should access evidence via short-lived signed URLs rather than making the bucket public. Workers generates these using R2's `createMultipartUpload` / `put` with the `createPresignedUrl` worker helper, or simply streams the object body directly (preferred for server-side dispute workflows).

```typescript
// src/handlers/evidence-download.ts
import type { Env } from '../types';

/** Returns the R2 object body directly — for internal/admin use only. Gate with auth. */
export async function handleEvidenceDownload(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const orderId = url.searchParams.get('order_id');
  const docType = url.searchParams.get('type') ?? 'receipt';

  if (!orderId) return Response.json({ error: 'order_id required' }, { status: 400 });

  // Validate the caller is an internal admin (replace with your auth logic)
  const authHeader = request.headers.get('Authorization');
  if (authHeader !== `Bearer ${env.INTERNAL_API_KEY}`) {
    return new Response('Unauthorized', { status: 401 });
  }

  // Look up the R2 key from the manifest
  const row = await env.DB
    .prepare(
      `SELECT r2_key, content_type FROM payment_evidence
        WHERE order_id = ? AND document_type = ?
        ORDER BY uploaded_at DESC LIMIT 1`
    )
    .bind(orderId, docType)
    .first<{ r2_key: string; content_type: string }>();

  if (!row) return Response.json({ error: 'not_found' }, { status: 404 });

  const object = await env.PAYMENT_EVIDENCE.get(row.r2_key);
  if (!object) return Response.json({ error: 'r2_object_missing' }, { status: 404 });

  return new Response(object.body, {
    headers: {
      'Content-Type': row.content_type,
      'Content-Disposition': `attachment; filename="${row.r2_key.split('/').pop()}"`,
      'Cache-Control': 'private, no-store',
    },
  });
}
```

---

## 5. Dispute Evidence Upload by Support Team

```typescript
// src/handlers/upload-evidence.ts
import type { Env } from '../types';

export async function handleDisputeEvidenceUpload(
  request: Request,
  env: Env
): Promise<Response> {
  const uploaderId = request.headers.get('X-Uploader-Id') ?? 'unknown';
  const formData = await request.formData();
  const orderId = formData.get('order_id') as string;
  const customerId = formData.get('customer_id') as string;
  const file = formData.get('file') as File | null;

  if (!orderId || !customerId || !file) {
    return Response.json({ error: 'order_id, customer_id, and file required' }, { status: 400 });
  }

  const allowedTypes = ['application/pdf', 'image/png', 'image/jpeg'];
  if (!allowedTypes.includes(file.type)) {
    return Response.json({ error: 'Unsupported file type' }, { status: 415 });
  }

  const ext = file.name.split('.').pop() ?? 'bin';
  const key = `dispute_evidence/${orderId}/${Date.now()}_${crypto.randomUUID()}.${ext}`;
  const bytes = await file.arrayBuffer();

  await env.PAYMENT_EVIDENCE.put(key, bytes, {
    httpMetadata: { contentType: file.type },
    customMetadata: { order_id: orderId, customer_id: customerId, document_type: 'dispute_evidence' },
  });

  await env.DB
    .prepare(
      `INSERT INTO payment_evidence
         (order_id, customer_id, document_type, r2_key, content_type, size_bytes, uploaded_by)
       VALUES (?, ?, 'dispute_evidence', ?, ?, ?, ?)`
    )
    .bind(orderId, customerId, key, file.type, bytes.byteLength, uploaderId)
    .run();

  return Response.json({ key }, { status: 201 });
}
```

---

## 6. Evidence Manifest Query for Dispute Package

```typescript
// src/lib/dispute-package.ts
import type { Env } from '../types';

export interface EvidenceItem {
  document_type: string;
  r2_key: string;
  uploaded_at: number;
}

/** Returns all evidence items for an order, newest first. */
export async function getDisputePackage(env: Env, orderId: string): Promise<EvidenceItem[]> {
  const result = await env.DB
    .prepare(
      `SELECT document_type, r2_key, uploaded_at
         FROM payment_evidence
        WHERE order_id = ?
        ORDER BY uploaded_at DESC`
    )
    .bind(orderId)
    .all<EvidenceItem>();

  return result.results;
}
```

---

## Anti-patterns

- **Serving R2 objects via a public bucket URL** — payment receipts contain PII; require authenticated access through a Worker at all times.
- **Regenerating receipts from current database state** — by the time a chargeback arrives, the order record may have been updated. Archive the receipt at issue time to preserve the point-in-time snapshot.
- **Using R2 keys as the only index** — listing a bucket with `list()` is slow for thousands of objects. Always maintain the D1 manifest and query by `order_id` there.
- **Omitting `customMetadata`** — without metadata on the R2 object, you lose the ability to attribute orphaned objects during bucket reconciliation.

---

## Gotchas

- R2 `put()` does not return an error if the object already exists — it silently overwrites. Check the D1 manifest for idempotency before writing.
- R2 objects have a maximum single-part upload size of 5 GB, but multipart upload is required above 100 MB. PDF receipts are typically 20–200 KB; single-part is fine.
- Workers can read up to 128 MB via `object.arrayBuffer()` in a single call. For very large evidence files, stream via `object.body` directly into the response.
- R2 does not support server-side encryption key management (BYOK) as of mid-2025. If PCI DSS requires BYOK, proxy through an external KMS before writing to R2.
- `CF-Ray` ID from the Worker request can be stored in `customMetadata` for traceability — useful when correlating an audit log entry with the specific Worker invocation that created the object.

---

## Verification

```bash
# Upload a test receipt via the evidence endpoint
curl -X POST https://payment-api.workers.dev/admin/evidence/upload \
  -H 'Authorization: Bearer <INTERNAL_API_KEY>' \
  -F 'order_id=ord_001' \
  -F 'customer_id=cus_001' \
  -F 'file=@/tmp/test-receipt.pdf'

# Verify it appears in the manifest
wrangler d1 execute YOUR_DB --command \
  "SELECT order_id, document_type, r2_key, size_bytes FROM payment_evidence"

# Download via the evidence endpoint
curl -O -J -H 'Authorization: Bearer <INTERNAL_API_KEY>' \
  'https://payment-api.workers.dev/admin/evidence/download?order_id=ord_001&type=receipt'

# List objects in R2 bucket (CLI)
wrangler r2 object list payment-evidence-prod --prefix receipts/2026/
```

---

## Related

- `payment-audit-logging.md`
- `chargeback-representment-workflow.md`
- `payment-data-retention.md`
- `payment-dispute-chargeback-automation.md`
- `invoice-generation-pdf.md`

---

## Sources

- Cloudflare R2 Workers bindings: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- R2 object custom metadata: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/#r2putoptions
- Stripe dispute evidence requirements: https://stripe.com/docs/disputes/responding
- PCI DSS evidence retention (Req 10.7): https://www.pcisecuritystandards.org/document_library/
