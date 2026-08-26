# Workers AI: Speech-to-Text Transcription Pipeline with R2

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

You need to transcribe audio files (call recordings, voice notes, podcast clips) uploaded by users. Files can be up to several hundred megabytes, transcription takes multiple seconds, and you want to notify downstream systems when the transcript is ready without holding open an HTTP connection.

## Context

The pipeline has three stages:

1. **Upload** — the client uploads audio to R2 via a pre-signed URL or direct `PUT`. A Workers endpoint records the job in D1.
2. **Transcription** — a Queue consumer fetches the audio from R2, calls `env.AI.run('@cf/openai/whisper', ...)`, and stores the transcript in D1.
3. **Notification** — the consumer fires a webhook (or writes to another Queue) when the transcript is complete.

`@cf/openai/whisper` accepts raw audio bytes (WAV, MP3, OGG, FLAC, MP4 audio) and returns a JSON object with `text`, `word_count`, `words` (array with timestamps), and `vtt` (WebVTT caption string).

Constraints:
- Workers AI Whisper has a 25 MB audio payload limit per invocation.
- Workers have a 128 MB memory limit — stream R2 objects rather than loading them fully into memory when possible.
- Long audio files must be chunked server-side before embedding.

## Solution

### 1. D1 schema

```sql
-- migrations/0001_transcription_jobs.sql
CREATE TABLE IF NOT EXISTS transcription_jobs (
  id            TEXT PRIMARY KEY,
  r2_key        TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'pending',
  language      TEXT,
  transcript    TEXT,
  vtt           TEXT,
  word_count    INTEGER,
  webhook_url   TEXT,
  error         TEXT,
  created_at    TEXT NOT NULL DEFAULT (datetime('now')),
  completed_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON transcription_jobs(status);
```

### 2. wrangler.toml

```toml
[[r2_buckets]]
  binding     = "AUDIO_BUCKET"
  bucket_name = "audio-uploads"

[[d1_databases]]
  binding       = "DB"
  database_name = "transcription-db"
  database_id   = "<your-d1-id>"

[[ai]]
  binding = "AI"

[[queues.producers]]
  binding = "TRANSCRIBE_QUEUE"
  queue   = "transcribe-jobs"

[[queues.consumers]]
  queue              = "transcribe-jobs"
  max_batch_size     = 1      # one audio file at a time to stay within memory
  max_batch_timeout  = 0
  max_retries        = 2
  dead_letter_queue  = "transcribe-dlq"
```

### 3. Upload endpoint

```typescript
// src/upload.ts
import { nanoid } from 'nanoid'; // bundled via npm

export interface Env {
  AUDIO_BUCKET: R2Bucket;
  DB: D1Database;
  TRANSCRIBE_QUEUE: Queue<TranscribeMessage>;
}

interface TranscribeMessage {
  jobId: string;
  r2Key: string;
  webhookUrl?: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'PUT') return new Response('Method Not Allowed', { status: 405 });

    const contentType = request.headers.get('Content-Type') ?? 'audio/wav';
    const webhookUrl = request.headers.get('X-Webhook-Url') ?? undefined;
    const jobId = nanoid();
    const r2Key = `audio/${jobId}`;

    // Stream upload directly to R2
    await env.AUDIO_BUCKET.put(r2Key, request.body, {
      httpMetadata: { contentType },
    });

    // Record job in D1
    await env.DB.prepare(
      `INSERT INTO transcription_jobs (id, r2_key, webhook_url) VALUES (?, ?, ?)`
    ).bind(jobId, r2Key, webhookUrl ?? null).run();

    // Enqueue transcription job
    await env.TRANSCRIBE_QUEUE.send({ jobId, r2Key, webhookUrl });

    return new Response(JSON.stringify({ jobId }), {
      status: 202,
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

### 4. Transcription consumer

```typescript
// src/transcribe-consumer.ts
import { Ai } from '@cloudflare/ai';

export interface Env {
  AUDIO_BUCKET: R2Bucket;
  DB: D1Database;
  AI: Ai;
}

interface TranscribeMessage {
  jobId: string;
  r2Key: string;
  webhookUrl?: string;
}

interface WhisperResult {
  text: string;
  word_count: number;
  words: Array<{ word: string; start: number; end: number }>;
  vtt: string;
}

const MAX_AUDIO_BYTES = 24 * 1024 * 1024; // 24 MB safety margin under 25 MB limit

export default {
  async queue(
    batch: MessageBatch<TranscribeMessage>,
    env: Env
  ): Promise<void> {
    // max_batch_size = 1, so exactly one message
    const msg = batch.messages[0];
    const { jobId, r2Key, webhookUrl } = msg.body;

    await updateStatus(env.DB, jobId, 'processing');

    // Fetch audio from R2
    const obj = await env.AUDIO_BUCKET.get(r2Key);
    if (!obj) {
      await failJob(env.DB, jobId, 'R2 object not found');
      msg.ack();
      return;
    }

    // Read audio bytes — enforce size cap
    const audioBuffer = await obj.arrayBuffer();
    if (audioBuffer.byteLength > MAX_AUDIO_BYTES) {
      await failJob(env.DB, jobId, `Audio file too large: ${audioBuffer.byteLength} bytes`);
      msg.ack();
      return;
    }

    // Detect language from Content-Type / filename hint
    const contentType = obj.httpMetadata?.contentType ?? 'audio/wav';

    let result: WhisperResult;
    try {
      result = await env.AI.run('@cf/openai/whisper', {
        audio: [...new Uint8Array(audioBuffer)],  // Workers AI expects number[]
      }) as WhisperResult;
    } catch (err) {
      console.error('Whisper error:', err);
      msg.retry(); // trigger Queue retry with back-off
      await updateStatus(env.DB, jobId, 'pending');
      return;
    }

    // Persist transcript
    await env.DB.prepare(
      `UPDATE transcription_jobs
         SET status = 'completed',
             transcript = ?,
             vtt = ?,
             word_count = ?,
             completed_at = datetime('now')
         WHERE id = ?`
    ).bind(result.text, result.vtt, result.word_count, jobId).run();

    // Fire webhook
    if (webhookUrl) {
      await notifyWebhook(webhookUrl, jobId, result);
    }

    msg.ack();
  },
};

async function updateStatus(db: D1Database, jobId: string, status: string): Promise<void> {
  await db.prepare('UPDATE transcription_jobs SET status = ? WHERE id = ?')
    .bind(status, jobId).run();
}

async function failJob(db: D1Database, jobId: string, error: string): Promise<void> {
  await db.prepare(
    `UPDATE transcription_jobs SET status = 'failed', error = ? WHERE id = ?`
  ).bind(error, jobId).run();
}

async function notifyWebhook(
  url: string,
  jobId: string,
  result: WhisperResult
): Promise<void> {
  try {
    await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        event: 'transcription.completed',
        jobId,
        transcript: result.text,
        wordCount: result.word_count,
        vtt: result.vtt,
      }),
      signal: AbortSignal.timeout(10_000),
    });
  } catch (err) {
    console.error('Webhook delivery failed:', err);
    // Not fatal — transcript is already persisted in D1
  }
}
```

### 5. Chunked audio processing for large files

When audio exceeds 24 MB, split it into chunks before enqueueing:

```typescript
// Pseudo-code: split audio in 20 MB chunks before upload
async function chunkAndEnqueue(
  audioBuffer: ArrayBuffer,
  env: Env,
  baseJobId: string,
  webhookUrl?: string
): Promise<string[]> {
  const CHUNK = 20 * 1024 * 1024;
  const chunks = [];
  const jobIds: string[] = [];

  for (let offset = 0; offset < audioBuffer.byteLength; offset += CHUNK) {
    const slice = audioBuffer.slice(offset, offset + CHUNK);
    const chunkId = `${baseJobId}-chunk-${chunks.length}`;
    const r2Key = `audio/${chunkId}`;

    await env.AUDIO_BUCKET.put(r2Key, slice);
    await env.DB.prepare(
      `INSERT INTO transcription_jobs (id, r2_key, webhook_url) VALUES (?, ?, ?)`
    ).bind(chunkId, r2Key, webhookUrl ?? null).run();
    await env.TRANSCRIBE_QUEUE.send({ jobId: chunkId, r2Key, webhookUrl });

    jobIds.push(chunkId);
  }

  return jobIds; // caller merges transcripts in order
}
```

### 6. Status polling endpoint

```typescript
async function statusHandler(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const jobId = url.pathname.split('/').pop();
  if (!jobId) return new Response('Not Found', { status: 404 });

  const job = await env.DB.prepare(
    `SELECT id, status, transcript, vtt, word_count, error, completed_at FROM transcription_jobs WHERE id = ?`
  ).bind(jobId).first();

  if (!job) return new Response('Not Found', { status: 404 });

  return new Response(JSON.stringify(job), {
    headers: { 'Content-Type': 'application/json' },
  });
}
```

## Implementation Details

- Whisper on Workers AI auto-detects the source language. The `language` field in the response (when present) is an ISO 639-1 code; store it for downstream filtering.
- The `words` array in the result contains precise `start` / `end` timestamps in seconds — useful for generating caption overlays.
- R2 `get()` returns `null` for non-existent keys; always null-check before reading `arrayBuffer()`.
- `AbortSignal.timeout()` is available in the Workers runtime from 2024 onwards — no need for `Promise.race` patterns.
- `max_batch_size = 1` is critical: a single Whisper inference can consume close to the 128 MB Worker memory limit for large audio files.

## Anti-patterns

- **Inline audio bytes in the Queue message body**: Queue messages are capped at 128 KB. Always store audio in R2 and pass only the key.
- **Loading audio with `await obj.text()`**: returns a UTF-8 string — corrupt for binary audio data. Use `arrayBuffer()` only.
- **Firing webhooks synchronously before ack**: if the webhook call hangs, the Queue message timer expires and re-delivers, causing duplicate transcription jobs. Ack first, fire webhook after, or use `ctx.waitUntil`.
- **Ignoring file size before calling Whisper**: the AI binding throws a hard error for payloads above 25 MB; validate early.

## Gotchas

- Whisper's `audio` input must be a `number[]` (plain JS array of unsigned bytes), not a `Uint8Array`. Use `[...new Uint8Array(buffer)]`.
- The `vtt` field may be absent when the audio has no detectable speech; always handle `undefined`.
- R2 objects are not automatically deleted after transcription. Add a lifecycle rule or explicit `env.AUDIO_BUCKET.delete(r2Key)` after the transcript is persisted to avoid storage costs.
- Whisper performs best on audio sampled at 16 kHz mono; stereo 48 kHz files are transcribed correctly but with higher latency.

## Verification

```bash
# Upload a test WAV file
curl -X PUT https://<worker>.workers.dev/upload \
  -H 'Content-Type: audio/wav' \
  -H 'X-Webhook-Url: https://webhook.site/<your-id>' \
  --data-binary @test.wav

# Response: {"jobId": "abc123"}

# Poll status
curl https://<worker>.workers.dev/status/abc123
# {"status":"completed","transcript":"Hello, this is a test.", ...}
```

## Related

- `documentation/categories/ai-ml/workers-ai-multimodal-image-analysis.md` — similar R2-backed async analysis pattern.
- `documentation/categories/ai-ml/workers-ai-batch-embedding-pipeline.md` — embed transcripts for semantic search.

## Sources

- Cloudflare Workers AI Whisper model: https://developers.cloudflare.com/workers-ai/models/whisper/
- R2 Workers API: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- Cloudflare Queues: https://developers.cloudflare.com/queues/
