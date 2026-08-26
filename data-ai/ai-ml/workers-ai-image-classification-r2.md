# Image Classification Pipeline with Workers AI + R2

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Images are uploaded to R2 and you need automatic classification labels — product categories, content types, safety flags — stored in D1 and cached in KV. Manual tagging does not scale. Batch processing via Queues prevents classification from blocking the upload response.

## Context

Workers AI provides `@cf/microsoft/resnet-50`, a ResNet-50 model pre-trained on ImageNet-1k. It returns up to 1000 ImageNet labels with confidence scores. For most product / content-moderation use-cases, filtering to scores above a threshold (e.g. 0.15) and mapping labels to application-specific categories is sufficient without fine-tuning.

The pipeline:
1. Client uploads image → R2 (via presigned URL or direct Worker upload).
2. R2 event notification → Queue message.
3. Queue consumer Worker → classify with ResNet-50 → store in D1, cache in KV.

## Solution

### 1. D1 schema

```sql
-- migrations/0001_classifications.sql
CREATE TABLE IF NOT EXISTS image_classifications (
  r2_key         TEXT PRIMARY KEY,
  bucket         TEXT NOT NULL,
  labels         TEXT NOT NULL,   -- JSON array of {label, score}
  top_label      TEXT,
  top_score      REAL,
  classified_at  INTEGER NOT NULL DEFAULT (unixepoch())
);
```

### 2. Upload handler — write to R2, enqueue

```typescript
// src/handlers/upload.ts
import type { R2Bucket, Queue } from '@cloudflare/workers-types';

export interface UploadEnv {
  IMAGES: R2Bucket;
  CLASSIFY_QUEUE: Queue;
}

export async function handleUpload(
  request: Request,
  env: UploadEnv,
): Promise<Response> {
  const contentType = request.headers.get('content-type') ?? 'application/octet-stream';
  const key = `uploads/${crypto.randomUUID()}`;

  // Write to R2
  await env.IMAGES.put(key, request.body, {
    httpMetadata: { contentType },
  });

  // Enqueue classification job (non-blocking)
  await env.CLASSIFY_QUEUE.send({ key, bucket: 'images' });

  return Response.json({ key, status: 'uploaded' }, { status: 201 });
}
```

### 3. Queue consumer — classify and store

```typescript
// src/handlers/classify.ts
import type {
  Ai,
  R2Bucket,
  D1Database,
  KVNamespace,
  MessageBatch,
} from '@cloudflare/workers-types';

const CONFIDENCE_THRESHOLD = 0.15;
const KV_TTL = 60 * 60 * 24; // 24 hours

interface ClassifyMessage {
  key: string;
  bucket: string;
}

interface ResNetResult {
  label: string;
  score: number;
}

export interface ClassifyEnv {
  AI: Ai;
  IMAGES: R2Bucket;
  DB: D1Database;
  CLASSIFICATION_CACHE: KVNamespace;
}

export async function handleClassifyBatch(
  batch: MessageBatch<ClassifyMessage>,
  env: ClassifyEnv,
): Promise<void> {
  for (const message of batch.messages) {
    const { key } = message.body;

    try {
      // 1. Read image from R2
      const object = await env.IMAGES.get(key);
      if (!object) {
        console.error(`R2 object not found: ${key}`);
        message.ack();
        continue;
      }

      const imageBytes = await object.arrayBuffer();

      // 2. Classify with ResNet-50
      const result = await env.AI.run('@cf/microsoft/resnet-50', {
        image: [...new Uint8Array(imageBytes)],
      });

      const allLabels = result as ResNetResult[];

      // 3. Filter by confidence threshold
      const filteredLabels = allLabels
        .filter((r) => r.score >= CONFIDENCE_THRESHOLD)
        .sort((a, b) => b.score - a.score)
        .slice(0, 10); // keep top 10

      const topLabel = filteredLabels[0]?.label ?? null;
      const topScore = filteredLabels[0]?.score ?? null;

      // 4. Persist to D1
      await env.DB.prepare(
        `INSERT INTO image_classifications
           (r2_key, bucket, labels, top_label, top_score)
         VALUES (?, ?, ?, ?, ?)
         ON CONFLICT(r2_key) DO UPDATE SET
           labels = excluded.labels,
           top_label = excluded.top_label,
           top_score = excluded.top_score,
           classified_at = unixepoch()`,
      )
        .bind(
          key,
          message.body.bucket,
          JSON.stringify(filteredLabels),
          topLabel,
          topScore,
        )
        .run();

      // 5. Cache result in KV
      await env.CLASSIFICATION_CACHE.put(
        `classify:${key}`,
        JSON.stringify({ labels: filteredLabels, topLabel, topScore }),
        { expirationTtl: KV_TTL },
      );

      message.ack();
    } catch (err) {
      console.error(`Classification failed for ${key}:`, err);
      message.retry();
    }
  }
}
```

### 4. Classification read endpoint

```typescript
// src/handlers/result.ts
import type { D1Database, KVNamespace } from '@cloudflare/workers-types';

export interface ResultEnv {
  DB: D1Database;
  CLASSIFICATION_CACHE: KVNamespace;
}

export async function handleResult(
  key: string,
  env: ResultEnv,
): Promise<Response> {
  // Check KV cache first
  const cached = await env.CLASSIFICATION_CACHE.get(`classify:${key}`);
  if (cached) {
    return Response.json(JSON.parse(cached), {
      headers: { 'x-cache': 'HIT' },
    });
  }

  // Fall back to D1
  const row = await env.DB.prepare(
    'SELECT labels, top_label, top_score FROM image_classifications WHERE r2_key = ?',
  )
    .bind(key)
    .first<{ labels: string; top_label: string | null; top_score: number | null }>();

  if (!row) {
    return new Response('Classification pending or not found', { status: 404 });
  }

  return Response.json({
    labels: JSON.parse(row.labels),
    topLabel: row.top_label,
    topScore: row.top_score,
  }, { headers: { 'x-cache': 'MISS' } });
}
```

### 5. Worker entry + wrangler.jsonc

```typescript
// src/index.ts
import { handleUpload } from './handlers/upload';
import { handleClassifyBatch } from './handlers/classify';
import { handleResult } from './handlers/result';

export interface Env {
  AI: Ai;
  IMAGES: R2Bucket;
  DB: D1Database;
  CLASSIFY_QUEUE: Queue;
  CLASSIFICATION_CACHE: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/upload') {
      return handleUpload(request, env);
    }
    if (request.method === 'GET' && url.pathname.startsWith('/result/')) {
      const key = decodeURIComponent(url.pathname.slice('/result/'.length));
      return handleResult(key, env);
    }
    return new Response('Not found', { status: 404 });
  },

  async queue(batch: MessageBatch<{ key: string; bucket: string }>, env: Env): Promise<void> {
    await handleClassifyBatch(batch, env);
  },
};
```

```jsonc
// wrangler.jsonc
{
  "name": "image-classifier",
  "main": "src/index.ts",
  "compatibility_date": "2025-09-01",
  "ai": { "binding": "AI" },
  "r2_buckets": [{ "binding": "IMAGES", "bucket_name": "my-images" }],
  "d1_databases": [{ "binding": "DB", "database_name": "classifications", "database_id": "<id>" }],
  "queues": {
    "producers": [{ "binding": "CLASSIFY_QUEUE", "queue": "image-classify-queue" }],
    "consumers": [{ "queue": "image-classify-queue", "max_batch_size": 10, "max_batch_timeout": 5 }]
  },
  "kv_namespaces": [{ "binding": "CLASSIFICATION_CACHE", "id": "<kv-id>" }]
}
```

## Implementation Details

### ResNet-50 output format

The model returns an array of `{ label: string, score: number }` objects, sorted by score descending, covering all 1000 ImageNet classes. Common classes useful for e-commerce: `Egyptian cat`, `French bulldog`, `laptop`, `running shoe`, `backpack`.

### Confidence threshold tuning

| Threshold | Behaviour |
|---|---|
| < 0.10 | Too many spurious labels |
| 0.10–0.20 | Good recall, moderate precision |
| > 0.30 | High precision, may miss relevant labels |

Start at 0.15 and adjust based on your label distribution in production.

### Batch processing via Queues

`max_batch_size: 10` processes 10 images per consumer invocation. Each ResNet-50 call handles one image (the model is not batched). Sequential processing inside the loop is acceptable; Workers run for up to 15 minutes in Queue consumers (30s on free plan).

### ImageNet label mapping

ImageNet labels are fine-grained (e.g. `German shepherd`, `golden retriever`). Map them to your application taxonomy in a separate lookup table in D1 or a KV JSON blob.

## Anti-patterns

- **Classifying synchronously during upload**: blocks the HTTP response and wastes client time — always offload to a Queue.
- **Storing the full 1000-label array**: filter to meaningful labels before persisting; 1000 JSON rows per image bloats D1.
- **Skipping the KV cache**: D1 reads on every result request are fine at small scale but add latency; KV provides sub-millisecond reads for hot images.
- **Using resnet-50 for face recognition or OCR**: it is an object classification model; use dedicated models for those tasks.

## Gotchas

- `@cf/microsoft/resnet-50` expects image bytes as a plain `number[]` (Uint8Array spread), not a base64 string or Blob.
- Queue consumer Workers do not have access to the `request` object — bindings only.
- R2 `get()` returns `null` if the key does not exist; always null-check before calling `.arrayBuffer()`.
- KV `expirationTtl` minimum is 60 seconds; setting it lower throws an error.
- Workers AI image classification counts against your AI Workers units budget.

## Verification

```bash
# Upload
curl -X POST https://image-classifier.<account>.workers.dev/upload \
  -H 'Content-Type: image/jpeg' \
  --data-binary @shoe.jpg
# => {"key":"uploads/abc-123","status":"uploaded"}

# Wait ~2s for queue processing, then:
curl https://image-classifier.<account>.workers.dev/result/uploads%2Fabc-123
# => {"labels":[{"label":"running shoe","score":0.82},{"label":"sneaker","score":0.71}],...}

# Check D1
npx wrangler d1 execute classifications \
  --command="SELECT * FROM image_classifications LIMIT 5"
```

## Related

- `workers-ai-rag-vectorize-d1.md` — using D1 as a metadata store alongside AI
- `workers-ai-content-moderation-gateway.md` — AI-powered safety classification
- Cloudflare Queues: https://developers.cloudflare.com/queues/
- Workers AI ResNet-50: https://developers.cloudflare.com/workers-ai/models/image-classification/

## Sources

- Cloudflare Workers AI — Image Classification: https://developers.cloudflare.com/workers-ai/models/image-classification/
- Microsoft ResNet-50 model (ImageNet-1k)
- Cloudflare R2 + Queues integration guide
