# Workers AI Whisper Transcription R2 Audio Pipeline

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Users upload audio files (podcasts, voice memos, meeting recordings) that your
application must transcribe. Files can be large (up to hundreds of MB), transcription
takes seconds to minutes, and you cannot block an HTTP response while waiting. You
need an async pipeline where audio lands in R2, a Queue triggers transcription via
Workers AI Whisper, and results are written back to D1.

## Context

Workers AI exposes the `@cf/openai/whisper` model for automatic speech recognition
(ASR). The model accepts a raw audio `Uint8Array` and returns a text transcript.
Because Workers have a 30-second CPU time limit on the free tier (up to 5 minutes on
paid with Smart Placement), long audio must be chunked or processed in a Queue
consumer Worker where the timeout is more generous. R2 is the natural landing zone for
binary audio blobs; Queue messages carry only the R2 object key to keep message size
small.

---

## 1. Upload Endpoint: Audio to R2

```typescript
// src/upload.ts
export async function handleUpload(req: Request, env: Env): Promise<Response> {
  const contentType = req.headers.get('Content-Type') ?? '';

  const ALLOWED_TYPES = [
    'audio/mpeg', 'audio/mp4', 'audio/wav', 'audio/webm',
    'audio/ogg', 'audio/flac', 'audio/x-m4a',
  ];

  if (!ALLOWED_TYPES.includes(contentType)) {
    return new Response('Unsupported audio type', { status: 415 });
  }

  const jobId = crypto.randomUUID();
  const r2Key = `audio/${jobId}`;

  // Stream the body directly into R2 — no buffering in Worker memory
  await env.AUDIO_BUCKET.put(r2Key, req.body, {
    httpMetadata: { contentType },
    customMetadata: {
      uploadedAt: new Date().toISOString(),
      jobId,
    },
  });

  // Record the job as "pending" in D1
  await env.DB.prepare(
    `INSERT INTO transcription_jobs (job_id, r2_key, status, created_at)
     VALUES (?, ?, 'pending', datetime('now'))`
  )
    .bind(jobId, r2Key)
    .run();

  // Enqueue for async transcription
  await env.TRANSCRIPTION_QUEUE.send({ jobId, r2Key });

  return Response.json({ jobId, status: 'pending' }, { status: 202 });
}
```

---

## 2. D1 Schema for Job Tracking

```sql
-- migrations/0001_transcription_jobs.sql
CREATE TABLE transcription_jobs (
  job_id      TEXT PRIMARY KEY,
  r2_key      TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'pending',  -- pending | processing | done | failed
  transcript  TEXT,
  error       TEXT,
  created_at  TEXT NOT NULL,
  updated_at  TEXT
);

CREATE INDEX idx_jobs_status ON transcription_jobs (status);
```

---

## 3. Queue Consumer: Transcription Worker

```typescript
// src/queue-consumer.ts
export default {
  async queue(batch: MessageBatch<{ jobId: string; r2Key: string }>, env: Env) {
    for (const msg of batch.messages) {
      const { jobId, r2Key } = msg.body;

      try {
        await transcribeJob(env, jobId, r2Key);
        msg.ack();
      } catch (err) {
        console.error(`Job ${jobId} failed:`, err);

        // Let the Queue retry automatically (up to the configured max retries)
        msg.retry({ delaySeconds: 30 });
      }
    }
  },
};

async function transcribeJob(env: Env, jobId: string, r2Key: string): Promise<void> {
  // Mark as processing
  await env.DB.prepare(
    `UPDATE transcription_jobs SET status='processing', updated_at=datetime('now') WHERE job_id=?`
  ).bind(jobId).run();

  // Fetch audio from R2
  const obj = await env.AUDIO_BUCKET.get(r2Key);
  if (!obj) throw new Error(`R2 object not found: ${r2Key}`);

  const audioBuffer = await obj.arrayBuffer();

  // Run Whisper on Workers AI
  const result = await env.AI.run('@cf/openai/whisper', {
    audio: [...new Uint8Array(audioBuffer)], // Whisper expects a number[]
  });

  const transcript = result.text ?? '';

  // Persist transcript and mark done
  await env.DB.prepare(
    `UPDATE transcription_jobs
     SET status='done', transcript=?, updated_at=datetime('now')
     WHERE job_id=?`
  ).bind(transcript, jobId).run();

  // Optional: delete the raw audio from R2 to save storage costs
  // await env.AUDIO_BUCKET.delete(r2Key);
}
```

---

## 4. Status Polling Endpoint

```typescript
// src/status.ts
export async function handleStatus(
  req: Request,
  env: Env,
  jobId: string
): Promise<Response> {
  const row = await env.DB.prepare(
    'SELECT status, transcript, error FROM transcription_jobs WHERE job_id = ?'
  )
    .bind(jobId)
    .first<{ status: string; transcript: string | null; error: string | null }>();

  if (!row) {
    return new Response('Job not found', { status: 404 });
  }

  return Response.json({
    jobId,
    status: row.status,
    transcript: row.status === 'done' ? row.transcript : null,
    error: row.status === 'failed' ? row.error : null,
  });
}
```

---

## 5. Chunking Large Audio Files

```typescript
// src/chunker.ts
// Whisper on Workers AI works best with files under ~25 MB.
// For larger files, split into overlapping chunks and stitch transcripts.

const CHUNK_SIZE_BYTES = 20 * 1024 * 1024; // 20 MB
const OVERLAP_BYTES = 64 * 1024;           // 64 KB overlap to avoid cutting words

export async function transcribeLargeAudio(
  ai: Ai,
  audioBuffer: ArrayBuffer
): Promise<string> {
  const bytes = new Uint8Array(audioBuffer);
  const transcripts: string[] = [];

  let offset = 0;
  while (offset < bytes.length) {
    const end = Math.min(offset + CHUNK_SIZE_BYTES, bytes.length);
    const chunk = bytes.slice(offset, end + OVERLAP_BYTES);

    const result = await ai.run('@cf/openai/whisper', {
      audio: [...chunk],
    });

    transcripts.push(result.text ?? '');
    offset = end;
  }

  // Simple join — for production use a smarter sentence-boundary stitcher
  return transcripts.join(' ').replace(/\s+/g, ' ').trim();
}
```

---

## 6. wrangler.toml Bindings

```toml
# wrangler.toml
name = "transcription-api"

[[r2_buckets]]
binding = "AUDIO_BUCKET"
bucket_name = "audio-uploads"

[[d1_databases]]
binding = "DB"
database_name = "transcription-db"
database_id = "your-d1-database-id"

[[queues.producers]]
binding = "TRANSCRIPTION_QUEUE"
queue = "transcription-queue"

[[queues.consumers]]
queue = "transcription-queue"
max_batch_size = 5
max_batch_timeout = 30
max_retries = 3
dead_letter_queue = "transcription-dlq"

[ai]
binding = "AI"
```

---

## Anti-patterns

- **Buffering large audio in Worker memory during upload** — stream directly into R2
  using `req.body` as the R2 put body; buffering risks hitting the 128 MB Worker
  memory limit.
- **Running Whisper synchronously in the upload handler** — even small files can take
  5–15 seconds; a synchronous approach blocks the response and may hit CPU limits.
- **Sending audio bytes in the Queue message** — Queue message payloads are limited to
  128 KB. Always send only the R2 key and fetch the audio inside the consumer.
- **No dead-letter queue** — without a DLQ, permanently failing jobs silently disappear;
  always configure `dead_letter_queue` and alert on DLQ depth.
- **Deleting R2 audio before the job is confirmed done** — if you delete the object
  optimistically and the D1 write fails, the audio is lost with no way to retry.

---

## Gotchas

- `@cf/openai/whisper` expects audio as a `number[]` (not `Uint8Array` directly) — use
  `[...new Uint8Array(buffer)]` to convert.
- Whisper returns `{ text: string; word_count: number; vtt: string }` — the `vtt` field
  contains WebVTT-formatted subtitles with timestamps, useful for caption generation.
- Workers AI Whisper does not currently support `language` hints via the Workers AI
  binding — language detection is automatic.
- R2 `get()` returns `null` if the object does not exist; always null-check before
  calling `.arrayBuffer()`.
- Queue consumer Workers have a separate CPU time budget from fetch-handler Workers;
  check the Cloudflare docs for the current limit on Queue consumer CPU time.
- Audio files containing silence or very low-quality audio may return empty `text`
  without an error — treat an empty transcript as a potential quality failure, not a
  success.

---

## Verification

```typescript
// Integration smoke test
async function smokeTestPipeline(env: Env) {
  // Upload a known short audio clip
  const audioBytes = new Uint8Array([/* minimal valid wav header + silence */]);
  const jobId = crypto.randomUUID();
  const r2Key = `audio/${jobId}`;

  await env.AUDIO_BUCKET.put(r2Key, audioBytes);
  await env.DB.prepare(
    `INSERT INTO transcription_jobs (job_id, r2_key, status, created_at) VALUES (?, ?, 'pending', datetime('now'))`
  ).bind(jobId, r2Key).run();

  await transcribeJob(env, jobId, r2Key);

  const row = await env.DB.prepare(
    'SELECT status FROM transcription_jobs WHERE job_id = ?'
  ).bind(jobId).first<{ status: string }>();

  console.assert(row?.status === 'done', `Expected done, got ${row?.status}`);
}
```

---

## Related

- `audio-transcription-whisper.md`
- `workers-ai-queue-batch-processing.md`
- `workers-ai-image-classification-r2-pipeline.md`
- `workers-ai-pipeline-chaining-multi-model.md`
- `llm-async-patterns.md`

---

## Sources

- Workers AI Whisper model: https://developers.cloudflare.com/workers-ai/models/whisper/
- Cloudflare R2 docs: https://developers.cloudflare.com/r2/
- Cloudflare Queues docs: https://developers.cloudflare.com/queues/
- D1 database docs: https://developers.cloudflare.com/d1/
