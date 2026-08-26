# Workers AI OCR Document Pipeline with R2

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
PDFs, scanned images, and photos of forms uploaded to R2 need text extracted for downstream search, classification, or LLM summarisation. A serverless OCR pipeline using Workers AI vision models and R2 eliminates dedicated OCR infrastructure while keeping data within Cloudflare.

## Context
Workers AI exposes vision-language models (`@cf/llava-hf/llava-1.5-7b-hf`, `@cf/unum/uform-gen2-qwen-500m`) that accept base64-encoded images and return descriptive text. For PDFs, the pipeline pre-converts pages to PNG via a Durable Object-hosted Wasm renderer (pdf.js compiled to Wasm), then feeds each page image to the vision model. Results are assembled per-document and stored back to R2 with structured JSON metadata. Queues drive the async fan-out so Workers stay within the 30-second CPU limit.

## Step 1: Upload Trigger Worker

```typescript
// upload-trigger.ts
import type { R2Bucket, Queue } from '@cloudflare/workers-types';

interface Env {
  DOCS_BUCKET: R2Bucket;
  OCR_QUEUE: Queue<OcrJob>;
}

interface OcrJob {
  docId: string;
  r2Key: string;
  mimeType: string;
  pageCount?: number;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const contentType = req.headers.get('content-type') ?? '';
    const docId = crypto.randomUUID();
    const extension = contentType.includes('pdf') ? '.pdf' : '.png';
    const r2Key = `uploads/${docId}${extension}`;
    const mimeType = contentType.split(';')[0].trim();

    // Stream upload directly to R2
    await env.DOCS_BUCKET.put(r2Key, req.body, {
      httpMetadata: { contentType: mimeType },
      customMetadata: { docId, uploadedAt: new Date().toISOString() },
    });

    // Enqueue OCR job
    await env.OCR_QUEUE.send({ docId, r2Key, mimeType });

    return Response.json({ docId, status: 'queued' }, { status: 202 });
  },
} satisfies ExportedHandler<Env>;
```

## Step 2: OCR Queue Consumer Worker

```typescript
// ocr-consumer.ts
import type {
  MessageBatch,
  R2Bucket,
  Ai,
  KVNamespace,
} from '@cloudflare/workers-types';

interface Env {
  DOCS_BUCKET: R2Bucket;
  AI: Ai;
  OCR_RESULTS: KVNamespace; // stores JSON OCR result per docId
}

interface OcrJob {
  docId: string;
  r2Key: string;
  mimeType: string;
}

interface PageResult {
  page: number;
  text: string;
  confidence: 'high' | 'medium' | 'low';
  wordCount: number;
}

interface OcrDocument {
  docId: string;
  r2Key: string;
  pages: PageResult[];
  fullText: string;
  processedAt: string;
  durationMs: number;
}

const OCR_PROMPT =
  'Extract all visible text from this image exactly as it appears. ' +
  'Preserve line breaks. Output only the extracted text, nothing else.';

export default {
  async queue(batch: MessageBatch<OcrJob>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await processOcrJob(env, msg.body);
        msg.ack();
      } catch (err) {
        console.error('OCR job failed', msg.body.docId, err);
        msg.retry();
      }
    }
  },
} satisfies ExportedHandler<Env>;

async function processOcrJob(env: Env, job: OcrJob): Promise<void> {
  const t0 = Date.now();
  const { docId, r2Key, mimeType } = job;

  const obj = await env.DOCS_BUCKET.get(r2Key);
  if (!obj) throw new Error(`R2 object not found: ${r2Key}`);

  const rawBytes = await obj.arrayBuffer();
  const pages = await extractPages(rawBytes, mimeType);

  const pageResults: PageResult[] = [];

  for (let i = 0; i < pages.length; i++) {
    const pageBase64 = arrayBufferToBase64(pages[i]);
    const text = await runVisionOcr(env.AI, pageBase64);
    pageResults.push({
      page: i + 1,
      text,
      confidence: inferConfidence(text),
      wordCount: text.split(/\s+/).filter(Boolean).length,
    });
  }

  const fullText = pageResults.map(p => p.text).join('\n\n--- PAGE BREAK ---\n\n');

  const doc: OcrDocument = {
    docId,
    r2Key,
    pages: pageResults,
    fullText,
    processedAt: new Date().toISOString(),
    durationMs: Date.now() - t0,
  };

  // Store structured result in KV (24-hour TTL; move to R2 for permanent storage)
  await env.OCR_RESULTS.put(
    `ocr:${docId}`,
    JSON.stringify(doc),
    { expirationTtl: 86400 },
  );

  // Write full OCR JSON back to R2 alongside original
  const resultKey = r2Key.replace(/\.[^.]+$/, '.ocr.json');
  await env.DOCS_BUCKET.put(resultKey, JSON.stringify(doc), {
    httpMetadata: { contentType: 'application/json' },
  });
}

async function runVisionOcr(ai: Ai, imageBase64: string): Promise<string> {
  const response = await ai.run('@cf/llava-hf/llava-1.5-7b-hf', {
    prompt: OCR_PROMPT,
    image: [...atob(imageBase64)].map(c => c.charCodeAt(0)),
    max_tokens: 2048,
  });
  // @ts-expect-error — runtime shape varies by model
  return (response?.response ?? response?.text ?? '').trim();
}

/** For single images (PNG/JPEG), return as single-page array */
async function extractPages(
  data: ArrayBuffer,
  mimeType: string,
): Promise<ArrayBuffer[]> {
  if (mimeType === 'application/pdf') {
    // PDF page splitting requires Wasm PDF renderer (e.g. pdf.js in Durable Object)
    // This stub returns the raw bytes; replace with DO call for multi-page PDFs
    return splitPdfPages(data);
  }
  return [data];
}

/** Stub — replace with actual Wasm PDF renderer Durable Object call */
function splitPdfPages(data: ArrayBuffer): ArrayBuffer[] {
  // In production: call a Durable Object that uses pdf.js Wasm to render each page to PNG
  return [data];
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function inferConfidence(text: string): 'high' | 'medium' | 'low' {
  const words = text.split(/\s+/).filter(Boolean).length;
  if (words > 20) return 'high';
  if (words > 5) return 'medium';
  return 'low';
}
```

## Step 3: Result Retrieval and Search Indexing

```typescript
// ocr-retrieve.ts
import type { KVNamespace, VectorizeIndex, Ai } from '@cloudflare/workers-types';

interface Env {
  OCR_RESULTS: KVNamespace;
  VECTORIZE: VectorizeIndex;
  AI: Ai;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const docId = url.searchParams.get('docId');
    if (!docId) return new Response('Missing docId', { status: 400 });

    const raw = await env.OCR_RESULTS.get(`ocr:${docId}`);
    if (!raw) return new Response('Not found or still processing', { status: 404 });

    const doc = JSON.parse(raw);

    // Optionally index into Vectorize for semantic search
    if (url.searchParams.get('index') === 'true') {
      await indexOcrDocument(env, docId, doc.fullText);
    }

    return Response.json(doc);
  },
} satisfies ExportedHandler<Env>;

async function indexOcrDocument(
  env: Env,
  docId: string,
  fullText: string,
): Promise<void> {
  // Chunk into 512-char segments for embedding
  const chunks: string[] = [];
  for (let i = 0; i < fullText.length; i += 512) {
    chunks.push(fullText.slice(i, i + 512));
  }

  const BATCH = 50;
  for (let i = 0; i < chunks.length; i += BATCH) {
    const slice = chunks.slice(i, i + BATCH);
    const emb = await env.AI.run('@cf/baai/bge-base-en-v1.5', { text: slice });
    const vecs = (emb as { data: number[][] }).data.map((v, j) => ({
      id: `${docId}::chunk::${i + j}`,
      values: v,
      metadata: { docId, chunkIdx: i + j, source: 'ocr' },
    }));
    await env.VECTORIZE.upsert(vecs);
  }
}
```

## wrangler.toml Configuration

```toml
name = "ocr-pipeline"
main = "src/upload-trigger.ts"
compatibility_date = "2026-01-01"

[[queues.producers]]
queue = "ocr-jobs"
binding = "OCR_QUEUE"

[[queues.consumers]]
queue = "ocr-jobs"
max_batch_size = 5
max_batch_timeout = 30
max_retries = 3
dead_letter_queue = "ocr-dlq"

[[r2_buckets]]
binding = "DOCS_BUCKET"
bucket_name = "documents"

[[kv_namespaces]]
binding = "OCR_RESULTS"
id = "<KV_ID>"

[ai]
binding = "AI"
```

## Anti-patterns

- **Awaiting OCR inline in the upload handler** — vision model inference is 2–8 seconds per page; always use Queues to decouple upload from processing.
- **Base64-encoding multi-page PDFs as a single blob** — vision models accept images, not PDFs; split each page to a separate image before passing to Workers AI.
- **Not handling `confidence: 'low'` pages** — blurry or rotated pages produce garbage text; route low-confidence pages to a human review queue or flag in metadata.
- **Storing full OCR text only in KV** — KV values cap at 25 MB; large documents exceed this; use R2 for persistence and KV as a short-lived status cache.
- **Skipping error retry on Queue consumer** — transient AI Gateway timeouts should trigger `msg.retry()`, not `msg.ack()`, to avoid silently losing documents.

## Gotchas

- Workers AI vision models return text in their own format; normalise with `.trim()` and strip any preamble the model adds (e.g. "The text in the image reads:").
- The `image` field accepts `number[]` (byte array), not a raw `ArrayBuffer` or base64 string in most Workers AI bindings — convert explicitly.
- Queue consumer CPU time is still capped at 30 s per invocation; for large documents reduce `max_batch_size` to 1 and process one document at a time.
- PDFs with digital text (not scanned) should be handled with a text-extraction library, not OCR — vision-based OCR is for rasterised/scanned content only.
- Workers AI `@cf/llava-hf/llava-1.5-7b-hf` supports images up to approximately 1024×1024 px; downscale high-resolution scans before encoding.

## Verification

```bash
# 1. Upload a PNG with visible text
curl -X POST https://<worker>/upload \
  -H 'Content-Type: image/png' \
  --data-binary @sample-form.png

# Returns: {"docId":"<uuid>","status":"queued"}

# 2. Poll for result (allow 10–30 s for Queue processing)
curl "https://<worker>/result?docId=<uuid>"

# 3. Verify full text extracted
curl "https://<worker>/result?docId=<uuid>&index=true"
# Check Vectorize index for chunk entries:
wrangler vectorize list-vectors --index-name documents --limit 5
```

## Related

- `ocr-with-llm.md`
- `workers-ai-image-classification-r2-pipeline.md`
- `workers-ai-queue-batch-processing.md`
- `workers-ai-whisper-r2-audio-pipeline.md`
- `rag-ingestion-pipeline.md`

## Sources

- https://developers.cloudflare.com/workers-ai/models/
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/r2/
