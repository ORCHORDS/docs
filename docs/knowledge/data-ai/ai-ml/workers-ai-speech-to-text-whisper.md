# Workers AI Speech-to-Text with Whisper

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to transcribe audio — support call recordings, voice memos, podcast clips — without spinning up a separate GPU service. Workers AI exposes `@cf/openai/whisper` as a serverless endpoint. This article covers accepting audio uploads, passing binary audio to the model, handling word-level timestamps, language detection, storing transcriptions in D1, and streaming partial results.

---

## Context

`@cf/openai/whisper` is Cloudflare's hosted port of OpenAI's Whisper model (the `tiny` variant by default, `medium` also available). It accepts raw audio bytes (WAV, MP3, MP4, OGG, FLAC) and returns a JSON transcript with optional word-level timestamps. Audio size limit through the Workers AI binding is approximately 50 MB; for larger files use R2 pre-processing.

Whisper inference is fast (< 5 s for a 1-minute clip) but still too slow for synchronous HTTP in production — design accordingly.

---

## Solution

```typescript
// src/index.ts
import { Ai } from '@cloudflare/ai';

export interface Env {
  AI: Ai;
  DB: D1Database;
  AUDIO_BUCKET: R2Bucket; // for caching raw audio alongside transcripts
}

// ── Types ──────────────────────────────────────────────────────────────────

interface WhisperWord {
  word: string;
  start: number; // seconds
  end:   number; // seconds
}

interface WhisperResult {
  text:      string;
  words?:    WhisperWord[];
  vtt?:      string; // WebVTT subtitle string
  language?: string; // detected language code, e.g. 'en'
}

interface TranscriptionRecord {
  id:          string;
  audio_key:   string;
  transcript:  string;
  language:    string;
  word_json:   string; // JSON array of WhisperWord
  duration_s:  number;
  created_at:  string;
  source_url?: string;
}

// ── D1 schema ──────────────────────────────────────────────────────────────
// Run once: wrangler d1 execute orchords-db --command "$(cat schema.sql)"
//
// CREATE TABLE IF NOT EXISTS transcriptions (
//   id           TEXT PRIMARY KEY,
//   audio_key    TEXT NOT NULL,
//   transcript   TEXT NOT NULL,
//   language     TEXT NOT NULL DEFAULT 'unknown',
//   word_json    TEXT NOT NULL DEFAULT '[]',
//   duration_s   REAL NOT NULL DEFAULT 0,
//   created_at   TEXT NOT NULL,
//   source_url   TEXT
// );
// CREATE INDEX idx_transcriptions_audio_key ON transcriptions(audio_key);

// ── Audio ingestion ────────────────────────────────────────────────────────

async function ingestAudio(
  request: Request,
  env: Env
): Promise<{ audioBytes: Uint8Array; audioKey: string; contentType: string }> {
  const contentType = request.headers.get('Content-Type') ?? 'audio/wav';
  const arrayBuffer = await request.arrayBuffer();

  if (arrayBuffer.byteLength === 0) {
    throw new Error('Empty audio body');
  }
  if (arrayBuffer.byteLength > 50 * 1024 * 1024) {
    throw new Error('Audio exceeds 50 MB limit; pre-process via R2');
  }

  const audioBytes = new Uint8Array(arrayBuffer);
  const audioKey = `audio/${crypto.randomUUID()}`;

  // Store raw audio in R2 alongside the transcript for replay / re-transcription.
  await env.AUDIO_BUCKET.put(audioKey, audioBytes, {
    httpMetadata: { contentType },
  });

  return { audioBytes, audioKey, contentType };
}

// ── Transcription ─────────────────────────────────────────────────────────

interface TranscribeOptions {
  includeTimestamps: boolean;
  language?: string; // optional hint; omit for auto-detection
}

async function transcribeAudio(
  audioBytes: Uint8Array,
  options: TranscribeOptions,
  env: Env
): Promise<WhisperResult> {
  const t0 = Date.now();

  // Workers AI Whisper binding accepts Float32Array (PCM) or raw audio bytes.
  // For pre-encoded audio (MP3/WAV/OGG) pass the raw bytes directly.
  const result = await env.AI.run('@cf/openai/whisper', {
    audio: [...audioBytes],                   // spread to plain number[]
    ...(options.language ? { language: options.language } : {}),
  });

  const whisper = result as unknown as WhisperResult;

  console.log(
    `Transcription completed in ${Date.now() - t0} ms,`,
    `detected language: ${whisper.language ?? 'unknown'},`,
    `words: ${whisper.words?.length ?? 0}`
  );

  return whisper;
}

// ── Duration estimation ───────────────────────────────────────────────────

function estimateDuration(words: WhisperWord[] | undefined): number {
  if (!words || words.length === 0) return 0;
  return words[words.length - 1].end;
}

// ── D1 persistence ────────────────────────────────────────────────────────

async function saveTranscription(
  audioKey:  string,
  whisper:   WhisperResult,
  sourceUrl: string | undefined,
  env:       Env
): Promise<TranscriptionRecord> {
  const record: TranscriptionRecord = {
    id:         crypto.randomUUID(),
    audio_key:  audioKey,
    transcript: whisper.text,
    language:   whisper.language ?? 'unknown',
    word_json:  JSON.stringify(whisper.words ?? []),
    duration_s: estimateDuration(whisper.words),
    created_at: new Date().toISOString(),
    source_url: sourceUrl,
  };

  await env.DB.prepare(`
    INSERT INTO transcriptions
      (id, audio_key, transcript, language, word_json, duration_s, created_at, source_url)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
  `)
    .bind(
      record.id,
      record.audio_key,
      record.transcript,
      record.language,
      record.word_json,
      record.duration_s,
      record.created_at,
      record.source_url ?? null
    )
    .run();

  return record;
}

// ── Streaming helper ──────────────────────────────────────────────────────
// Whisper itself is not a streaming model, but you can push word-level
// results progressively via SSE once transcription completes.

function buildSSEStream(whisper: WhisperResult): ReadableStream {
  const encoder = new TextEncoder();
  const words = whisper.words ?? [];

  return new ReadableStream({
    async start(controller) {
      // Send each word as a discrete SSE event.
      for (const word of words) {
        const data = JSON.stringify(word);
        controller.enqueue(encoder.encode(`event: word\ndata: ${data}\n\n`));
        // Simulate real-time delivery proportional to word duration.
        // In production, remove this delay and push all words immediately.
        await new Promise((r) => setTimeout(r, 0));
      }
      // Final event: full transcript + metadata.
      const finalPayload = JSON.stringify({
        text:     whisper.text,
        language: whisper.language ?? 'unknown',
        vtt:      whisper.vtt,
      });
      controller.enqueue(
        encoder.encode(`event: transcript\ndata: ${finalPayload}\n\n`)
      );
      controller.close();
    },
  });
}

// ── Subtitle generation ───────────────────────────────────────────────────
// Convert word-level timestamps to WebVTT format if the model does not supply it.

function wordsToVTT(words: WhisperWord[]): string {
  const lines = ['WEBVTT', ''];
  const CHUNK_DURATION = 3; // seconds per subtitle cue
  let chunkStart = 0;
  let chunkWords: WhisperWord[] = [];

  const flush = () => {
    if (chunkWords.length === 0) return;
    const start = formatVTTTime(chunkWords[0].start);
    const end   = formatVTTTime(chunkWords[chunkWords.length - 1].end);
    lines.push(`${start} --> ${end}`);
    lines.push(chunkWords.map((w) => w.word).join(' '));
    lines.push('');
    chunkWords = [];
  };

  for (const w of words) {
    if (w.start - chunkStart >= CHUNK_DURATION) {
      flush();
      chunkStart = w.start;
    }
    chunkWords.push(w);
  }
  flush();

  return lines.join('\n');
}

function formatVTTTime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = (seconds % 60).toFixed(3).padStart(6, '0');
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${s}`;
}

// ── Request handler ───────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // GET /transcriptions/:id — retrieve stored transcript.
    if (request.method === 'GET' && url.pathname.startsWith('/transcriptions/')) {
      const id = url.pathname.split('/').pop();
      const row = await env.DB
        .prepare('SELECT * FROM transcriptions WHERE id = ?')
        .bind(id)
        .first<TranscriptionRecord>();
      if (!row) return Response.json({ error: 'Not found' }, { status: 404 });

      const accept = request.headers.get('Accept') ?? '';
      if (accept.includes('text/vtt')) {
        const words: WhisperWord[] = JSON.parse(row.word_json);
        return new Response(wordsToVTT(words), {
          headers: { 'Content-Type': 'text/vtt' },
        });
      }
      return Response.json(row);
    }

    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405 });
    }

    // POST / — transcribe uploaded audio.
    const wantsStream = url.searchParams.get('stream') === '1';
    const language    = url.searchParams.get('lang') ?? undefined;
    const sourceUrl   = url.searchParams.get('source') ?? undefined;

    let audioBytes: Uint8Array;
    let audioKey: string;
    let contentType: string;

    try {
      ({ audioBytes, audioKey, contentType } = await ingestAudio(request, env));
    } catch (err) {
      return Response.json(
        { error: err instanceof Error ? err.message : 'Ingest failed' },
        { status: 400 }
      );
    }

    const whisper = await transcribeAudio(
      audioBytes,
      { includeTimestamps: true, language },
      env
    );

    // Persist the result.
    const record = await saveTranscription(audioKey, whisper, sourceUrl, env);

    if (wantsStream) {
      return new Response(buildSSEStream(whisper), {
        headers: {
          'Content-Type':  'text/event-stream',
          'Cache-Control': 'no-cache',
          'X-Transcript-Id': record.id,
        },
      });
    }

    return Response.json({
      id:        record.id,
      transcript: whisper.text,
      language:   whisper.language ?? 'unknown',
      duration_s: record.duration_s,
      words:      whisper.words ?? [],
      vtt:        whisper.vtt ?? wordsToVTT(whisper.words ?? []),
      audio_key:  audioKey,
    });
  },
};
```

---

## Implementation Details

**Audio input format**: Workers AI Whisper accepts a `number[]` (not a `Uint8Array` directly). Spread with `[...audioBytes]`. The model auto-detects WAV, MP3, OGG, FLAC, and MP4 container formats from the file header — no explicit format parameter needed.

**Language hint vs. auto-detect**: Passing `language: 'en'` skips the ~0.5 s detection step. If your use-case is multilingual, omit the hint and use `whisper.language` from the response.

**Word timestamps**: Only available on the `medium` model variant. The `tiny` variant returns `text` only. Select the model variant by appending `-timestamped` to the model ID if/when Cloudflare exposes it; otherwise parse `words` defensively with `?? []`.

**VTT generation**: If `whisper.vtt` is populated by the model, use it directly. The `wordsToVTT` helper is a fallback for when word timestamps are available but VTT is not.

**D1 storage**: `word_json` stores the words array as a JSON string because D1 does not have a native JSON column type (unlike PostgreSQL's `jsonb`). Use `JSON.parse` on retrieval.

---

## Anti-patterns

- **Passing a `Uint8Array` directly**: The binding expects `number[]`. Use `[...audioBytes]` or `Array.from(audioBytes)`.
- **Transcribing audio > 50 MB synchronously**: Large files exceed CPU limits. Chunk audio server-side or accept an R2 object key and load in parts.
- **Storing the raw transcript without language metadata**: Transcript search and filtering without language is painful at scale. Always persist `whisper.language`.
- **Not handling missing `words` array**: The tiny model omits `words`. Guard with `?? []` everywhere.
- **Blocking the client for the full transcription duration**: For clips > 30 s, use a Queue + webhook pattern (same as the image generation article).

---

## Gotchas

- The Workers AI Whisper binding does NOT stream partial tokens — you receive the entire transcript at once. The SSE stream in this article pushes words after the fact, not in real time.
- Audio must be in a supported codec. Raw PCM `.raw` files will fail; encode to WAV first with ffmpeg before sending.
- `word.start` / `word.end` are in seconds as floating-point numbers, not milliseconds.
- Workers CPU time limit is 30 s (paid plan). A 5-minute audio clip can push this limit — test with real production audio lengths.
- The `audio` parameter type in `@cloudflare/ai` types may show as `Float32Array`; casting to `number[]` at runtime is safe.

---

## Verification

```bash
# Transcribe a local WAV file
curl -s -X POST 'http://localhost:8787' \
  -H 'Content-Type: audio/wav' \
  --data-binary @sample.wav | jq '{transcript, language, duration_s}'

# Retrieve stored transcript as WebVTT
curl -s -H 'Accept: text/vtt' \
  'http://localhost:8787/transcriptions/<id>'

# Streaming word-by-word SSE
curl -N 'http://localhost:8787?stream=1' \
  -X POST \
  -H 'Content-Type: audio/mp3' \
  --data-binary @speech.mp3

# Test language hint
curl -s -X POST 'http://localhost:8787?lang=de' \
  -H 'Content-Type: audio/wav' \
  --data-binary @german_audio.wav | jq .language
```

---

## Related

- `documentation/docs/policies/ai-ml/workers-ai-function-calling-tool-use.md` — pass transcript to an agent
- `documentation/docs/policies/ai-ml/workers-ai-image-generation-flux.md` — async Queue pattern
- Cloudflare Workers AI Whisper model: https://developers.cloudflare.com/workers-ai/models/whisper/
- D1 docs: https://developers.cloudflare.com/d1/

---

## Sources

- Cloudflare Workers AI Speech Recognition docs (2025)
- OpenAI Whisper model paper
- Cloudflare D1 best practices guide
