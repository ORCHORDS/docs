# Workers AI Async Audio Transcription with Queues and D1 Job Tracking

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Audio files can be large and Whisper transcription takes several seconds per minute of audio. Running inference synchronously in a fetch handler risks hitting the 30-second subrequest timeout and produces a poor UX. The solution is an async pipeline: the client POSTs metadata and receives a job ID immediately; a Queue consumer runs Whisper inference in the background; D1 tracks job state and stores the transcript for retrieval.

## Context

Cloudflare Queues decouple the upload acknowledgement from inference work. R2 holds the audio binary. D1 is the job registry: it records status (`queued → processing → complete | failed`), the R2 object key, and the final transcript. The client polls a status endpoint or uses a webhook callback. Workers AI Whisper (`@cf/openai/whisper`) runs inside the Queue consumer where subrequest limits are more relaxed and retries are automatic.

---

## 1. D1 Schema — Job Registry

```sql
-- migrations/0001_transcription_jobs.sql
CREATE TABLE IF NOT EXISTS transcription_jobs (
  job_id       TEXT PRIMARY KEY,
  r2_key       TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'queued',  -- queued | processing | complete | failed
  language     TEXT,
  transcript   TEXT,
  error_msg    TEXT,
  webhook_url  TEXT,
  created_at   INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at   INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_jobs_status ON transcription_jobs (status, created_at);
```

---

## 2. Upload Handler — Accept File, Write to R2, Enqueue Job

```typescript
// src/handlers/upload.ts
import { nanoid } from 'nanoid';
import type { Env } from '../types';

export async function handleUpload(
  request: Request,
  env: Env,
): Promise<Response> {
  const contentType = request.headers.get('Content-Type') ?? '';
  if (!contentType.startsWith('audio/') && !contentType.includes('octet-stream')) {
    return new Response('Unsupported media type', { status: 415 });
  }

  const jobId = nanoid(16);
  const r2Key = `audio/${jobId}`;
  const webhookUrl = request.headers.get('X-Webhook-Url') ?? undefined;
  const language = request.headers.get('X-Language') ?? undefined;

  // Stream body directly to R2 — avoid buffering in Worker memory
  await env.AUDIO_BUCKET.put(r2Key, request.body, {
    httpMetadata: { contentType },
  });

  // Register job in D1
  await env.DB.prepare(
    `INSERT INTO transcription_jobs (job_id, r2_key, language, webhook_url)
     VALUES (?1, ?2, ?3, ?4)`,
  )
    .bind(jobId, r2Key, language ?? null, webhookUrl ?? null)
    .run();

  // Enqueue for async processing
  await env.TRANSCRIPTION_QUEUE.send({ jobId, r2Key, language });

  return Response.json({ jobId, status: 'queued' }, { status: 202 });
}
```

---

## 3. Queue Consumer — Run Whisper Inference

```typescript
// src/consumers/transcribe.ts
import type { Env } from '../types';

interface TranscriptionMessage {
  jobId: string;
  r2Key: string;
  language?: string;
}

export async function processTranscription(
  batch: MessageBatch<TranscriptionMessage>,
  env: Env,
): Promise<void> {
  for (const msg of batch.messages) {
    const { jobId, r2Key, language } = msg.body;

    try {
      // Mark as processing
      await env.DB.prepare(
        `UPDATE transcription_jobs
         SET status = 'processing', updated_at = unixepoch()
         WHERE job_id = ?1`,
      )
        .bind(jobId)
        .run();

      // Fetch audio from R2
      const obj = await env.AUDIO_BUCKET.get(r2Key);
      if (!obj) throw new Error(`R2 object not found: ${r2Key}`);

      const audioBuffer = await obj.arrayBuffer();

      // Run Whisper
      const result = await env.AI.run('@cf/openai/whisper', {
        audio: [...new Uint8Array(audioBuffer)],
        ...(language ? { language } : {}),
      });

      const transcript = result.text ?? '';

      // Write transcript to D1
      await env.DB.prepare(
        `UPDATE transcription_jobs
         SET status = 'complete', transcript = ?2, updated_at = unixepoch()
         WHERE job_id = ?1`,
      )
        .bind(jobId, transcript)
        .run();

      // Optional: fire webhook
      const jobRow = await env.DB.prepare(
        `SELECT webhook_url FROM transcription_jobs WHERE job_id = ?1`,
      )
        .bind(jobId)
        .first<{ webhook_url: string | null }>();

      if (jobRow?.webhook_url) {
        await fetch(jobRow.webhook_url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ jobId, status: 'complete', transcript }),
        }).catch((e) => console.warn('[webhook] delivery failed:', e));
      }

      msg.ack();
    } catch (err) {
      console.error(`[transcribe] job ${jobId} failed:`, err);

      await env.DB.prepare(
        `UPDATE transcription_jobs
         SET status = 'failed', error_msg = ?2, updated_at = unixepoch()
         WHERE job_id = ?1`,
      )
        .bind(jobId, String(err))
        .run();

      // nack with retryDelay so the queue retries after 30 s
      msg.retry({ delaySeconds: 30 });
    }
  }
}
```

---

## 4. Status Polling Endpoint

```typescript
// src/handlers/status.ts
import type { Env } from '../types';

export async function handleStatus(
  request: Request,
  env: Env,
): Promise<Response> {
  const url = new URL(request.url);
  const jobId = url.pathname.split('/').pop();
  if (!jobId) return new Response('Missing job ID', { status: 400 });

  const row = await env.DB.prepare(
    `SELECT status, transcript, error_msg, created_at, updated_at
     FROM transcription_jobs WHERE job_id = ?1`,
  )
    .bind(jobId)
    .first<{
      status: string;
      transcript: string | null;
      error_msg: string | null;
      created_at: number;
      updated_at: number;
    }>();

  if (!row) return new Response('Not found', { status: 404 });

  return Response.json({
    jobId,
    status: row.status,
    transcript: row.transcript,
    error: row.error_msg,
    createdAt: new Date(row.created_at * 1000).toISOString(),
    updatedAt: new Date(row.updated_at * 1000).toISOString(),
  });
}
```

---

## 5. Worker Entry Point and wrangler.toml Bindings

```typescript
// src/index.ts
import { handleUpload } from './handlers/upload';
import { handleStatus } from './handlers/status';
import { processTranscription } from './consumers/transcribe';
import type { Env } from './types';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (request.method === 'POST' && url.pathname === '/transcribe')
      return handleUpload(request, env);
    if (request.method === 'GET' && url.pathname.startsWith('/jobs/'))
      return handleStatus(request, env);
    return new Response('Not found', { status: 404 });
  },

  async queue(
    batch: MessageBatch<{ jobId: string; r2Key: string; language?: string }>,
    env: Env,
  ): Promise<void> {
    await processTranscription(batch, env);
  },
};
```

```toml
# wrangler.toml (relevant sections)
[[queues.producers]]
queue = "transcription-queue"
binding = "TRANSCRIPTION_QUEUE"

[[queues.consumers]]
queue = "transcription-queue"
max_batch_size = 5
max_batch_timeout = 30
max_retries = 3
dead_letter_queue = "transcription-dlq"

[[r2_buckets]]
binding = "AUDIO_BUCKET"
bucket_name = "audio-uploads"

[[d1_databases]]
binding = "DB"
database_name = "transcription-db"
database_id = "<DB_ID>"
```

---

## Anti-patterns

- Buffering the full audio `ArrayBuffer` in the upload fetch handler before streaming to R2 — Workers have a 128 MB memory limit; stream via `request.body` directly.
- Running Whisper in the fetch handler synchronously — inference can take 10–60 s per file; always defer to the Queue consumer.
- Storing the raw audio blob in D1 — D1 rows have a 1 MB size limit; audio belongs in R2.
- Sending `msg.ack()` before verifying the D1 write succeeded — a D1 failure after `ack()` loses the job permanently; ack only after all side effects commit.

## Gotchas

- Workers AI Whisper expects `audio` as a `number[]` (byte array), not an `ArrayBuffer` directly; spread `new Uint8Array(buffer)` as shown.
- Queue consumers in free tier are limited to 5 messages per batch; raise `max_batch_size` on paid plans for better throughput.
- Dead-letter queues do not retry automatically; build a separate DLQ consumer or alert on DLQ depth via Analytics Engine.
- Whisper's `language` field accepts ISO-639-1 codes (`en`, `fr`, `es`); passing an unsupported code silently falls back to auto-detect.

## Verification

```bash
# Upload a test file
curl -X POST https://<worker>.workers.dev/transcribe \
  -H "Content-Type: audio/mpeg" \
  --data-binary @test.mp3

# Poll status
curl https://<worker>.workers.dev/jobs/<JOB_ID>

# Watch queue consumer logs
wrangler tail --format pretty | grep "transcribe"

# Check DLQ depth
wrangler queues info transcription-dlq
```

## Related

- `workers-ai-whisper-r2-audio-pipeline.md`
- `audio-transcription-whisper.md`
- `workers-ai-queue-batch-processing.md`
- `llm-async-patterns.md`

## Sources

- Cloudflare Workers AI — Whisper model reference
- Cloudflare Queues consumer API docs
- Cloudflare R2 streaming upload guide
- D1 row size and storage limits
