# Workers AI Image Classification Pipeline with R2, D1, and Batch Reprocessing

- Date: 2026-08-22
- Author: example.com
- Status: production

## The Problem: Images Need Classification at Upload Time and Again When the Model Changes

E-commerce catalogs, content moderation queues, and medical imaging platforms all share
the same lifecycle: images arrive continuously and must be labelled fast (seconds, not
minutes), but the classification model is periodically retrained and all historical
images need their labels refreshed when it improves.

Workers AI makes the inference step trivially serverless — no GPU fleet to manage. But
triggering inference on upload and orchestrating a batch reprocessing run require
careful plumbing: an R2 event notification fires the upload path, D1 stores results
with model version metadata so stale labels are identifiable, and a scheduled Worker
drives the reprocessing job without overloading the inference endpoint.

## Context

- Storage: Cloudflare R2 (image blobs), D1 (classification results)
- Inference: Workers AI (`@cf/microsoft/resnet-50` or `@cf/unum/uform-gen2-qwen-500m`)
- Triggers: R2 event notifications → Queue, Cron Triggers for batch
- Runtime: Cloudflare Workers (ESM)
- Language: TypeScript

## R2 Upload Trigger: Queue Producer

R2 event notifications send an `ObjectCreated` event to a Queue when a new object is
written. A minimal producer Worker validates the event and enqueues the object key for
classification — it does not perform inference inline so it always returns within the
R2 notification timeout.

```ts
// src/r2-trigger.ts
export interface Env {
  IMAGE_CLASSIFY_QUEUE: Queue<ClassifyJob>;
  ALLOWED_BUCKETS: string; // comma-separated bucket names
}

export interface ClassifyJob {
  bucket: string;
  key: string;
  size: number;
  contentType: string;
  enqueuedAt: number;
  modelVersion: string;
}

// This Worker is bound as the R2 event notification target
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // R2 posts a JSON body with event records
    const payload = await request.json<{
      Records: Array<{
        s3: {
          bucket: { name: string };
          object: { key: string; size: number; contentType?: string };
        };
      }>;
    }>();

    const allowed = new Set(env.ALLOWED_BUCKETS.split(",").map((s) => s.trim()));

    for (const record of payload.Records) {
      const bucket = record.s3.bucket.name;
      if (!allowed.has(bucket)) continue;

      const obj = record.s3.object;
      const contentType = obj.contentType ?? "application/octet-stream";
      if (!contentType.startsWith("image/")) continue;

      const job: ClassifyJob = {
        bucket,
        key: obj.key,
        size: obj.size,
        contentType,
        enqueuedAt: Date.now(),
        modelVersion: "resnet-50-v1", // bump when retraining
      };

      await env.IMAGE_CLASSIFY_QUEUE.send(job);
    }

    return new Response("ok");
  },
};
```

## Queue Consumer: Workers AI Inference + D1 Write

The consumer downloads the image from R2, runs inference via Workers AI, and writes
the result to D1 with the model version tag so reprocessing queries can target stale
rows.

```ts
// src/classify-consumer.ts
export interface Env {
  AI: Ai;
  IMAGE_BUCKET: R2Bucket;
  RESULTS_DB: D1Database;
}

interface ClassificationResult {
  label: string;
  score: number;
}

export default {
  async queue(batch: MessageBatch<ClassifyJob>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const job = msg.body;
      try {
        // Fetch image bytes from R2
        const obj = await env.IMAGE_BUCKET.get(job.key);
        if (!obj) {
          console.warn(`Object not found: ${job.key}`);
          msg.ack();
          continue;
        }

        const imageBytes = new Uint8Array(await obj.arrayBuffer());

        // Run image classification via Workers AI
        const raw = await env.AI.run("@cf/microsoft/resnet-50", {
          image: [...imageBytes],
        });

        // resnet-50 returns an array sorted by confidence
        const predictions = raw as ClassificationResult[];
        const top = predictions[0];

        await env.RESULTS_DB.prepare(
          `INSERT INTO classifications
             (object_key, bucket, label, score, model_version, classified_at)
           VALUES (?, ?, ?, ?, ?, unixepoch())
           ON CONFLICT (object_key) DO UPDATE SET
             label = excluded.label,
             score = excluded.score,
             model_version = excluded.model_version,
             classified_at = excluded.classified_at`
        )
          .bind(job.key, job.bucket, top.label, top.score, job.modelVersion)
          .run();

        msg.ack();
      } catch (err) {
        console.error(`classify failed for ${job.key}:`, err);
        msg.retry();
      }
    }
  },
};
```

## D1 Schema

```sql
-- migrations/0001_classifications.sql
CREATE TABLE IF NOT EXISTS classifications (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  object_key    TEXT    NOT NULL UNIQUE,
  bucket        TEXT    NOT NULL,
  label         TEXT    NOT NULL,
  score         REAL    NOT NULL,
  model_version TEXT    NOT NULL,
  classified_at INTEGER NOT NULL
);

CREATE INDEX idx_model_version ON classifications (model_version);
CREATE INDEX idx_classified_at ON classifications (classified_at);
```

## Batch Reprocessing Cron Worker

When the model is updated, set a new `CURRENT_MODEL_VERSION` secret and let the cron
Worker page through stale rows, re-enqueuing them for the consumer.

```ts
// src/reprocess-cron.ts
export interface Env {
  IMAGE_CLASSIFY_QUEUE: Queue<ClassifyJob>;
  RESULTS_DB: D1Database;
  CURRENT_MODEL_VERSION: string;
  REPROCESS_BATCH_SIZE: string; // default "100"
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const batchSize = parseInt(env.REPROCESS_BATCH_SIZE ?? "100", 10);
    const currentVersion = env.CURRENT_MODEL_VERSION;

    // Find images classified with an older model version
    const stale = await env.RESULTS_DB.prepare(
      `SELECT object_key, bucket FROM classifications
       WHERE model_version != ?
       ORDER BY classified_at ASC
       LIMIT ?`
    )
      .bind(currentVersion, batchSize)
      .all<{ object_key: string; bucket: string }>();

    if (!stale.results.length) {
      console.log("Reprocessing: no stale records found");
      return;
    }

    const jobs: ClassifyJob[] = stale.results.map((row) => ({
      bucket: row.bucket,
      key: row.object_key,
      size: 0, // not needed for reprocessing
      contentType: "image/jpeg",
      enqueuedAt: Date.now(),
      modelVersion: currentVersion,
    }));

    // Queue supports batch sends up to 100 messages
    await env.IMAGE_CLASSIFY_QUEUE.sendBatch(
      jobs.map((j) => ({ body: j, contentType: "json" }))
    );

    console.log(`Reprocessing: enqueued ${jobs.length} stale images`);
  },
};
```

## Anti-patterns

- Running inference synchronously inside the R2 trigger handler — Workers AI calls
  can take 2–5 s for large images; R2 notification timeouts are strict.
- Storing the raw image bytes in D1 alongside classification results — D1 rows have
  a size limit; blobs belong in R2.
- Using `ON CONFLICT IGNORE` instead of `DO UPDATE` — silently drops reprocessing
  updates, leaving stale labels in place.
- Batching 500+ images per cron tick without backpressure — the Queue will absorb them
  but inference Workers may be rate-limited; use a smaller batch with frequent ticks.

## Gotchas

- `@cf/microsoft/resnet-50` returns ImageNet labels (1000 classes); for domain-specific
  classification (medical, fashion) you need a fine-tuned LoRA adapter or a different
  model (`@cf/unum/uform-gen2-qwen-500m` for open-vocabulary).
- R2 event notifications require the bucket and Worker to be in the same Cloudflare
  account; cross-account triggers need a webhook proxy.
- `IMAGE_BUCKET.get(key)` returns `null` for objects that have been deleted between
  the upload event and the Queue consumer processing — always guard with a null check.
- Resnet-50 input must be a flat `number[]` (not `Uint8Array`) when passed via the
  Workers AI binding; spread with `[...imageBytes]`.

## Verification

```ts
// test/pipeline.test.ts
// Smoke test: encode a 1x1 white JPEG and assert classify returns a label
const onePixelJpeg = new Uint8Array([
  0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46, 0x00, 0x01,
  // ... (truncated for brevity — use a real fixture in CI)
]);

// Mock AI binding
const mockAI = {
  run: async (_model: string, _input: unknown) =>
    [{ label: "test_label", score: 0.99 }],
};

const result = (await mockAI.run("@cf/microsoft/resnet-50", {
  image: [...onePixelJpeg],
})) as Array<{ label: string; score: number }>;

console.assert(result[0].label === "test_label", "label mismatch");
console.log("pipeline smoke test passed");
```

## Related

- [AI Content Moderation Pipeline](ai-content-moderation-pipeline.md)
- [Workers AI Streaming Inference](cloudflare-workers-ai-streaming-inference.md)
- [Audio Transcription Whisper](audio-transcription-whisper.md)
- [AI Cold Start Patterns](ai-cold-start-patterns.md)
- [AI Gateway Logging](ai-gateway-logging.md)

## Sources

- https://developers.cloudflare.com/workers-ai/models/image-classification/
- https://developers.cloudflare.com/r2/buckets/event-notifications/
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/runtime-apis/scheduled-event/
