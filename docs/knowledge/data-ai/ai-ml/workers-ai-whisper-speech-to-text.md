# Workers AI Whisper Speech-to-Text

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to transcribe audio files uploaded via a web form directly inside a Cloudflare Worker, returning text with optional word-level timestamps. Files larger than 25 MB must be chunked before inference, and completed transcripts need to be persisted in a D1 database for later retrieval.

---

## Context

`@cf/openai/whisper` is exposed through the Workers AI binding and expects audio data as a `Float32Array` sampled at 16 kHz mono. Browsers commonly upload audio as `multipart/form-data`, so the Worker must parse the form, extract the file blob, and resample if needed. Workers have a 128 MB memory cap, which means very long audio must be split into chunks before each `env.AI.run()` call. D1 is the natural store for structured transcript records because it supports full-text search via the FTS5 extension, enabling transcript search later. The Whisper model returns a JSON object with a `text` field and an optional `words` array containing per-word `start`/`end` timestamps.

---

## Section 1 — wrangler.toml

```toml
name = "whisper-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[ai]
binding = "AI"

[[d1_databases]]
binding = "DB"
database_name = "transcripts"
database_id = "<your-d1-database-id>"

[vars]
MAX_AUDIO_BYTES = "26214400"   # 25 MB in bytes
CHUNK_DURATION_SECONDS = "30" # 30-second chunks
SAMPLE_RATE = "16000"
```

## Section 2 — Worker implementation

```typescript
interface Env {
  AI: Ai;
  DB: D1Database;
  MAX_AUDIO_BYTES: string;
  CHUNK_DURATION_SECONDS: string;
  SAMPLE_RATE: string;
}

interface WhisperWord {
  word: string;
  start: number;
  end: number;
}

interface WhisperResult {
  text: string;
  words?: WhisperWord[];
}

interface TranscriptRecord {
  id: string;
  filename: string;
  text: string;
  words: WhisperWord[];
  duration_seconds: number;
  created_at: string;
}

/**
 * Convert a raw audio ArrayBuffer (PCM 16-bit LE, mono, 16 kHz) to Float32Array.
 * Real resampling requires the Web Audio API or a WASM codec;
 * here we handle the common case of 16-bit PCM directly.
 */
function pcm16ToFloat32(buffer: ArrayBuffer): Float32Array {
  const int16 = new Int16Array(buffer);
  const float32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) {
    float32[i] = int16[i] / 32768.0;
  }
  return float32;
}

/**
 * Split a Float32Array into overlapping chunks of `chunkSamples` length.
 * A 10 % overlap avoids cut-off words at boundaries.
 */
function chunkAudio(audio: Float32Array, chunkSamples: number): Float32Array[] {
  const overlap = Math.floor(chunkSamples * 0.1);
  const step = chunkSamples - overlap;
  const chunks: Float32Array[] = [];
  for (let offset = 0; offset < audio.length; offset += step) {
    chunks.push(audio.slice(offset, offset + chunkSamples));
  }
  return chunks;
}

/**
 * Merge multiple WhisperResult objects, adjusting word timestamps by chunk offset.
 */
function mergeResults(results: { result: WhisperResult; offsetSeconds: number }[]): WhisperResult {
  let fullText = '';
  const words: WhisperWord[] = [];
  for (const { result, offsetSeconds } of results) {
    if (fullText.length > 0) fullText += ' ';
    fullText += result.text.trim();
    if (result.words) {
      for (const w of result.words) {
        words.push({
          word: w.word,
          start: w.start + offsetSeconds,
          end: w.end + offsetSeconds,
        });
      }
    }
  }
  return { text: fullText, words };
}

async function saveTranscript(
  db: D1Database,
  record: TranscriptRecord
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO transcripts (id, filename, text, words, duration_seconds, created_at)
       VALUES (?, ?, ?, ?, ?, ?)`
    )
    .bind(
      record.id,
      record.filename,
      record.text,
      JSON.stringify(record.words),
      record.duration_seconds,
      record.created_at
    )
    .run();
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // GET /transcripts/:id — retrieve a stored transcript
    const match = url.pathname.match(/^\/transcripts\/([a-z0-9-]+)$/);
    if (request.method === 'GET' && match) {
      const { results } = await env.DB.prepare(
        'SELECT * FROM transcripts WHERE id = ? LIMIT 1'
      )
        .bind(match[1])
        .all<TranscriptRecord>();
      if (!results.length) return new Response('Not found', { status: 404 });
      return Response.json(results[0]);
    }

    // POST / — transcribe uploaded audio
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const contentType = request.headers.get('Content-Type') ?? '';
    if (!contentType.includes('multipart/form-data')) {
      return new Response(
        JSON.stringify({ error: 'Expected multipart/form-data' }),
        { status: 415, headers: { 'Content-Type': 'application/json' } }
      );
    }

    const formData = await request.formData();
    const file = formData.get('audio') as File | null;
    if (!file) {
      return new Response(
        JSON.stringify({ error: 'Missing `audio` field in form data' }),
        { status: 400, headers: { 'Content-Type': 'application/json' } }
      );
    }

    const maxBytes = parseInt(env.MAX_AUDIO_BYTES, 10);
    if (file.size > maxBytes * 4) {
      // Reject extremely large uploads outright (>100 MB)
      return new Response(
        JSON.stringify({ error: 'Audio file too large. Maximum size is 100 MB.' }),
        { status: 413, headers: { 'Content-Type': 'application/json' } }
      );
    }

    const rawBuffer = await file.arrayBuffer();
    const sampleRate = parseInt(env.SAMPLE_RATE, 10);
    const chunkDuration = parseInt(env.CHUNK_DURATION_SECONDS, 10);
    const chunkSamples = chunkDuration * sampleRate;

    // Convert PCM-16 → Float32 (assumes 16-bit mono 16 kHz input)
    const float32Audio = pcm16ToFloat32(rawBuffer);
    const durationSeconds = float32Audio.length / sampleRate;

    const needsChunking = rawBuffer.byteLength > maxBytes;
    let mergedResult: WhisperResult;

    if (!needsChunking) {
      mergedResult = (await env.AI.run('@cf/openai/whisper', {
        audio: [...float32Audio], // binding accepts number[]
      })) as WhisperResult;
    } else {
      const chunks = chunkAudio(float32Audio, chunkSamples);
      const chunkResults: { result: WhisperResult; offsetSeconds: number }[] = [];
      for (let i = 0; i < chunks.length; i++) {
        const offsetSeconds = i * (chunkDuration * 0.9); // account for 10 % overlap
        const result = (await env.AI.run('@cf/openai/whisper', {
          audio: [...chunks[i]],
        })) as WhisperResult;
        chunkResults.push({ result, offsetSeconds });
      }
      mergedResult = mergeResults(chunkResults);
    }

    const id = crypto.randomUUID();
    const record: TranscriptRecord = {
      id,
      filename: file.name,
      text: mergedResult.text,
      words: mergedResult.words ?? [],
      duration_seconds: Math.round(durationSeconds * 100) / 100,
      created_at: new Date().toISOString(),
    };

    await saveTranscript(env.DB, record);

    return Response.json(record, { status: 201 });
  },
};
```

## Section 3 — D1 schema and FTS5 search

```typescript
// Run once via `wrangler d1 execute transcripts --file=schema.sql`
// schema.sql:
// CREATE TABLE IF NOT EXISTS transcripts (
//   id TEXT PRIMARY KEY,
//   filename TEXT NOT NULL,
//   text TEXT NOT NULL,
//   words TEXT NOT NULL DEFAULT '[]',
//   duration_seconds REAL NOT NULL,
//   created_at TEXT NOT NULL
// );
//
// CREATE VIRTUAL TABLE IF NOT EXISTS transcripts_fts
//   USING fts5(id UNINDEXED, text, content='transcripts', content_rowid='rowid');
//
// CREATE TRIGGER IF NOT EXISTS transcripts_ai AFTER INSERT ON transcripts BEGIN
//   INSERT INTO transcripts_fts (rowid, id, text)
//   VALUES (new.rowid, new.id, new.text);
// END;

// Search endpoint — GET /search?q=hello+world
async function handleSearch(request: Request, db: D1Database): Promise<Response> {
  const query = new URL(request.url).searchParams.get('q') ?? '';
  if (!query.trim()) {
    return new Response(JSON.stringify({ error: '`q` parameter required' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const { results } = await db
    .prepare(
      `SELECT t.id, t.filename, t.duration_seconds, t.created_at,
              snippet(transcripts_fts, 1, '<mark>', '</mark>', '...', 20) AS snippet
       FROM transcripts_fts
       JOIN transcripts t ON t.id = transcripts_fts.id
       WHERE transcripts_fts MATCH ?
       ORDER BY rank
       LIMIT 20`
    )
    .bind(query.trim())
    .all();

  return Response.json({ results });
}
```

---

## Anti-patterns

- **Passing raw MP3/AAC bytes to the model** — Whisper on Workers AI expects `Float32Array` (16 kHz mono PCM). Passing compressed audio bytes without decoding will produce garbage output or an error.
- **Uploading audio in a single Workers fetch without chunking** — Workers have a 30 s CPU limit (Unbound: 15 min wallclock). Audio longer than ~5 minutes must be chunked or processed with Durable Objects.
- **Storing raw `Float32Array` in D1** — Float32 binary data bloats D1 storage. Store only the transcript text and JSON-serialised word timestamps.
- **No overlap between chunks** — Splitting at hard boundaries silently drops words that span the cut point. Always include a 5–10 % overlap and de-duplicate the merged text.

---

## Gotchas

- The Workers AI Whisper binding accepts `audio` as a JavaScript `number[]`, not a typed array; spread the `Float32Array` with `[...float32]`.
- Whisper returns `words: undefined` when confidence is low; always guard with `?? []`.
- D1 FTS5 `MATCH` queries use SQLite's simple tokeniser by default; phrases must be quoted: `"hello world"`.
- `file.arrayBuffer()` loads the entire file into the Worker's heap; guard against OOM with a size check before calling it.
- Workers AI Whisper has a ~25 MB raw audio limit per invocation; the `MAX_AUDIO_BYTES` env var should match this limit.

---

## Verification

```bash
# Create D1 database
npx wrangler d1 create transcripts

# Apply schema (save schema.sql from the code section above)
npx wrangler d1 execute transcripts --file=schema.sql

# Deploy
npx wrangler deploy

# Transcribe a short WAV file (must be 16-bit PCM mono 16 kHz)
curl -X POST https://whisper-worker.<your-subdomain>.workers.dev \
  -F 'audio=@sample.wav' | jq .

# Retrieve a stored transcript
curl https://whisper-worker.<your-subdomain>.workers.dev/transcripts/<id>

# Full-text search
curl 'https://whisper-worker.<your-subdomain>.workers.dev/search?q=cloudflare'
```

---

## Related

- `workers-ai-embeddings-vectorize-semantic-search.md`
- `workers-ai-text-classification-moderation.md`
- `workers-ai-stable-diffusion-image-generation.md`

---

## Sources

- Workers AI Whisper model — https://developers.cloudflare.com/workers-ai/models/whisper/
- D1 Full-Text Search (FTS5) — https://developers.cloudflare.com/d1/reference/full-text-search/
- Cloudflare Workers Limits — https://developers.cloudflare.com/workers/platform/limits/
