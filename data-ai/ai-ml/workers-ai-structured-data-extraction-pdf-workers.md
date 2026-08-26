# Workers AI Structured Data Extraction from PDFs

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You receive PDFs (invoices, contracts, medical forms, CVs) and need to extract structured JSON from them inside a Cloudflare Worker—without a Python server, without OCR preprocessing steps outside the edge, and without shipping a 200 MB library to a client.

## Context

Cloudflare Workers AI exposes `@cf/meta/llama-3.1-8b-instruct` and vision models that accept base64-encoded images. A PDF page rendered to a PNG (via a WASM-based renderer or uploaded as a pre-rendered image) can be passed to the vision model with a typed JSON schema prompt. The result is parsed and validated with Zod before storage. This pattern keeps the entire extraction loop inside the Workers runtime: R2 holds the PDF, a Queue triggers per-page extraction, D1 stores structured rows.

---

## 1. Architecture Overview

```
R2 (pdf-uploads)
      │  object-create event
      ▼
Queue (pdf-pages-queue)
      │
      ▼
Worker (extractor)
  ├─ fetch page image from R2 (pre-rendered PNG or WASM render)
  ├─ Workers AI vision model → raw JSON string
  ├─ Zod parse + validate
  └─ D1 INSERT structured row
```

Pre-rendering pages to PNG upstream (e.g., a separate Worker using a PDF-to-image WASM binary) is recommended because Workers AI vision models accept images, not raw PDF bytes.

---

## 2. Binding Definitions (`wrangler.toml`)

```toml
[[r2_buckets]]
binding = "PDF_BUCKET"
bucket_name = "pdf-uploads"

[[queues.consumers]]
queue = "pdf-pages-queue"
binding = "PDF_QUEUE"

[[d1_databases]]
binding = "DB"
database_name = "extractions"
database_id = "YOUR_D1_ID"

[ai]
binding = "AI"
```

---

## 3. Zod Schema for Invoice Extraction

```typescript
import { z } from "zod";

export const InvoiceSchema = z.object({
  invoice_number: z.string(),
  issue_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  due_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  vendor_name: z.string(),
  vendor_address: z.string().optional(),
  total_amount: z.number(),
  currency: z.string().length(3),
  line_items: z.array(
    z.object({
      description: z.string(),
      quantity: z.number(),
      unit_price: z.number(),
      total: z.number(),
    })
  ),
});

export type Invoice = z.infer<typeof InvoiceSchema>;
```

---

## 4. Extraction Worker

```typescript
import { InvoiceSchema } from "./schema";

interface Env {
  AI: Ai;
  PDF_BUCKET: R2Bucket;
  DB: D1Database;
  PDF_QUEUE: Queue;
}

interface PageMessage {
  pdfKey: string;
  pageKey: string; // R2 key of pre-rendered PNG
  pageNumber: number;
  documentType: "invoice" | "contract" | "cv";
}

const EXTRACTION_PROMPT = `
You are a structured data extractor. Analyze the document image and return
ONLY valid JSON matching this schema (no markdown, no explanation):
{
  "invoice_number": "string",
  "issue_date": "YYYY-MM-DD",
  "due_date": "YYYY-MM-DD or null",
  "vendor_name": "string",
  "vendor_address": "string or null",
  "total_amount": number,
  "currency": "ISO 4217 3-letter code",
  "line_items": [{ "description": "string", "quantity": number, "unit_price": number, "total": number }]
}
`;

export default {
  async queue(batch: MessageBatch<PageMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { pdfKey, pageKey, pageNumber } = msg.body;

      // Fetch pre-rendered page PNG from R2
      const obj = await env.PDF_BUCKET.get(pageKey);
      if (!obj) {
        msg.ack();
        continue;
      }

      const imageBytes = await obj.arrayBuffer();
      const base64Image = btoa(
        String.fromCharCode(...new Uint8Array(imageBytes))
      );

      // Call vision model
      const aiResponse = await env.AI.run("@cf/llava-hf/llava-1.5-7b-hf", {
        prompt: EXTRACTION_PROMPT,
        image: [...new Uint8Array(imageBytes)],
        max_tokens: 1024,
      });

      const rawText =
        typeof aiResponse === "string"
          ? aiResponse
          : (aiResponse as { response: string }).response;

      // Parse JSON, strip possible markdown fences
      const jsonStr = rawText.replace(/```json?\n?|```/g, "").trim();
      let parsed: unknown;
      try {
        parsed = JSON.parse(jsonStr);
      } catch {
        console.error(`JSON parse failure for ${pageKey}:`, rawText.slice(0, 200));
        msg.retry();
        continue;
      }

      // Validate with Zod
      const result = InvoiceSchema.safeParse(parsed);
      if (!result.success) {
        console.error(`Schema validation failed for ${pageKey}:`, result.error.flatten());
        // Store raw for human review rather than retry-looping
        await env.DB.prepare(
          `INSERT INTO extraction_failures (pdf_key, page_key, page_number, raw_json, error, created_at)
           VALUES (?, ?, ?, ?, ?, ?)`
        ).bind(pdfKey, pageKey, pageNumber, jsonStr, JSON.stringify(result.error.flatten()), Date.now()).run();
        msg.ack();
        continue;
      }

      // Persist structured data
      const inv = result.data;
      await env.DB.prepare(
        `INSERT INTO invoices (pdf_key, page_number, invoice_number, issue_date, due_date,
           vendor_name, vendor_address, total_amount, currency, line_items_json, created_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
      ).bind(
        pdfKey, pageNumber, inv.invoice_number, inv.issue_date,
        inv.due_date ?? null, inv.vendor_name, inv.vendor_address ?? null,
        inv.total_amount, inv.currency, JSON.stringify(inv.line_items), Date.now()
      ).run();

      msg.ack();
    }
  },
};
```

---

## 5. D1 Schema

```sql
CREATE TABLE IF NOT EXISTS invoices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pdf_key TEXT NOT NULL,
  page_number INTEGER NOT NULL,
  invoice_number TEXT,
  issue_date TEXT,
  due_date TEXT,
  vendor_name TEXT,
  vendor_address TEXT,
  total_amount REAL,
  currency TEXT,
  line_items_json TEXT,
  created_at INTEGER
);

CREATE TABLE IF NOT EXISTS extraction_failures (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pdf_key TEXT NOT NULL,
  page_key TEXT NOT NULL,
  page_number INTEGER NOT NULL,
  raw_json TEXT,
  error TEXT,
  created_at INTEGER
);
```

---

## Anti-patterns

- **Passing raw PDF bytes to the vision model** — vision models expect image tensors, not PDF binary. Pre-render pages to PNG/JPEG first.
- **Parsing AI output without stripping markdown fences** — models often wrap JSON in ` ```json ` blocks even when instructed not to.
- **Retrying Zod validation failures indefinitely** — schema mismatches usually mean the page had unexpected layout. Log to `extraction_failures` for human review instead.
- **Storing the base64 string in D1** — store only the R2 key reference; base64 of even a single page PNG inflates row size by 33%.

---

## Gotchas

- `@cf/llava-hf/llava-1.5-7b-hf` accepts an `image` field as `number[]` (Uint8Array spread), not a base64 string. Check model card for the exact input contract per model.
- Workers AI vision models have a context window limit; dense multi-column invoices may need page splitting into quadrants.
- Queue `maxRetries` defaults to 3. Set it low (2) for extraction jobs to avoid burning AI tokens on consistently malformed inputs.
- D1 `TEXT` columns storing JSON (like `line_items_json`) must be queried with `json_extract()` in SQLite; index on extracted values via generated columns if you filter frequently.

---

## Verification

```typescript
// Smoke test: upload a known invoice PNG, trigger queue manually, query D1
const rows = await env.DB.prepare(
  "SELECT * FROM invoices WHERE pdf_key = ? ORDER BY created_at DESC LIMIT 1"
).bind("test-invoice.pdf").all();

console.assert(rows.results.length === 1, "Extraction should produce one row");
console.assert(rows.results[0].currency === "USD", "Currency should parse correctly");
```

Run `wrangler d1 execute --command "SELECT COUNT(*) FROM extraction_failures"` after a batch to monitor failure rates. Keep failures < 5% of pages.

---

## Related

- `workers-ai-ocr-document-pipeline.md`
- `workers-ai-entity-extraction-structured-output-d1.md`
- `workers-ai-json-schema-constrained-generation.md`
- `llm-structured-output-json-mode.md`
- `workers-ai-queue-batch-processing.md`

---

## Sources

- Cloudflare Workers AI model catalog: https://developers.cloudflare.com/workers-ai/models/
- Cloudflare Queues docs: https://developers.cloudflare.com/queues/
- Zod documentation: https://zod.dev
- LLaVA model card: https://huggingface.co/llava-hf/llava-1.5-7b-hf
