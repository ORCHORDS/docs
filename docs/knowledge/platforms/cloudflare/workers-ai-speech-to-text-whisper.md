# workers-ai-speech-to-text-whisper

Transcribe audio to text at the edge using Whisper via Workers AI — accepting
audio uploads, running inference on the nearest AI PoP, and returning structured
transcripts with word-level timestamps.

**Date:** 2026-08-23
**Author:** example.com
**Status:** production

## Symptom / Use-case

You need audio transcription without managing a Whisper GPU server:

- Transcribe voice notes, meeting recordings, or podcasts in a Worker
- Add closed captions to uploaded audio/video in a media pipeline
- Power voice-driven search or command recognition at the edge
- Run speech analytics on call recordings streamed from a telephony provider

## Context

Workers AI exposes OpenAI Whisper as `@cf/openai/whisper` and
`@cf/openai/whisper-large-v3-turbo`. The model accepts audio bytes as a
`Float32Array`, `Uint8Array`, or base64-encoded string, and returns a JSON
transcript with a `text` field and optional per-word timestamps.

Audio must be converted to raw PCM or a supported container (WAV, MP3, FLAC,
OGG) before submission. The Workers AI runtime handles decoding internally for
common formats. For very long recordings (>30 min), chunk the audio by segment
boundaries and run parallel inference with `Promise.all`.

## Binding the model

```toml
# wrangler.toml
name = "transcription-worker"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[ai]
binding = "AI"
```

```typescript
// src/types.ts
export interface Env {
  AI: Ai;
  TRANSCRIPTS: D1Database; // optional: persist results
}
```

## Basic transcription from an audio upload

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("POST an audio file", { status: 405 });
    }

    const contentType = request.headers.get("Content-Type") ?? "";
    const allowedTypes = ["audio/wav", "audio/mpeg", "audio/mp3", "audio/flac", "audio/ogg"];
    if (!allowedTypes.some((t) => contentType.startsWith(t))) {
      return new Response("Unsupported audio format", { status: 415 });
    }

    // Buffer the audio body
    const audioBuffer = await request.arrayBuffer();
    const audioBytes = new Uint8Array(audioBuffer);

    const result = await env.AI.run("@cf/openai/whisper", {
      audio: [...audioBytes], // Workers AI accepts a plain number array
    });

    return Response.json({
      text: result.text,
      wordCount: result.text.split(/\s+/).filter(Boolean).length,
    });
  },
};
```

## Getting word-level timestamps

```typescript
interface WhisperWord {
  word: string;
  start: number; // seconds from start
  end: number;
}

interface WhisperResult {
  text: string;
  words?: WhisperWord[];
}

export async function transcribeWithTimestamps(
  env: Env,
  audioBytes: Uint8Array
): Promise<WhisperResult> {
  const result = await env.AI.run("@cf/openai/whisper", {
    audio: [...audioBytes],
    // whisper-large-v3-turbo returns word timestamps by default
  }) as WhisperResult;

  return result;
}

// Usage
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const audioBuffer = await request.arrayBuffer();
    const transcript = await transcribeWithTimestamps(env, new Uint8Array(audioBuffer));

    return Response.json({
      text: transcript.text,
      words: transcript.words ?? [],
    });
  },
};
```

## Chunked transcription for long recordings

Whisper operates on 30-second windows. For recordings longer than ~30 minutes,
split into chunks and merge:

```typescript
// Approximate: split a Uint8Array of WAV PCM data into 30 s segments
// WAV PCM: 16-bit samples at 16 kHz = 32000 bytes/s
const BYTES_PER_SECOND_16K_MONO = 32000;
const CHUNK_SECONDS = 30;

async function transcribeLong(env: Env, pcmBytes: Uint8Array): Promise<string> {
  const chunkSize = CHUNK_SECONDS * BYTES_PER_SECOND_16K_MONO;
  const chunks: Uint8Array[] = [];

  for (let offset = 0; offset < pcmBytes.length; offset += chunkSize) {
    chunks.push(pcmBytes.slice(offset, offset + chunkSize));
  }

  // Run up to 5 chunks in parallel to stay within CPU time limits
  const CONCURRENCY = 5;
  const texts: string[] = [];

  for (let i = 0; i < chunks.length; i += CONCURRENCY) {
    const batch = chunks.slice(i, i + CONCURRENCY);
    const results = await Promise.all(
      batch.map((chunk) =>
        env.AI.run("@cf/openai/whisper", { audio: [...chunk] })
      )
    );
    for (const r of results) {
      texts.push((r as { text: string }).text.trim());
    }
  }

  return texts.join(" ");
}
```

## Persisting transcripts to D1

```typescript
export async function saveTranscript(
  env: Env,
  jobId: string,
  audioKey: string,
  text: string
): Promise<void> {
  await env.TRANSCRIPTS.prepare(
    `INSERT INTO transcripts (id, audio_key, transcript, created_at)
     VALUES (?, ?, ?, ?)`
  )
    .bind(jobId, audioKey, text, new Date().toISOString())
    .run();
}
```

## Choosing the right Whisper variant

| Model | Speed | Accuracy | Best for |
|---|---|---|---|
| `@cf/openai/whisper` | Fast | Good | Short clips, real-time |
| `@cf/openai/whisper-large-v3-turbo` | Moderate | Best | Long recordings, accuracy-critical |

Use `whisper` for real-time or interactive use cases; use `whisper-large-v3-turbo`
for batch pipelines where accuracy matters more than latency.

## Anti-patterns

- **Sending raw MP4 video bytes.** Workers AI Whisper expects audio-only streams.
  Demux the audio track first (in a Worker using WebAssembly FFmpeg or by
  pre-processing in a Queue consumer) before sending to the model.
- **Transcribing in the request handler for long recordings.** A 60-minute
  recording at 128 kbps is ~58 MB and requires multiple Whisper windows.
  Synchronous transcription will hit the Worker CPU time limit. Use Workers
  Queues: enqueue the R2 key, process in a queue consumer with longer CPU
  budget.
- **Ignoring the AI token quota.** Whisper inference consumes Workers AI units.
  At scale, add rate limiting (per-user or per-day) with KV counters before the
  AI call.
- **Returning the full audio buffer in an error response.** If validation fails,
  return only the error message — never reflect the binary upload body back to
  the client.
- **Not validating audio file size before buffering.** A 500 MB upload will OOM
  the Worker. Check `Content-Length` or enforce a max body size with a WAF rule.

## Gotchas

- **`env.AI.run()` with Whisper accepts `number[]`, not raw `Uint8Array`.**
  Spreading the array (`[...audioBytes]`) is the correct conversion. Passing
  the `Uint8Array` directly may throw a type error depending on the Workers AI
  binding version.
- **Audio resampling is not automatic.** Whisper expects 16 kHz mono PCM. WAV
  files at 44.1 kHz or stereo may be decoded differently by the runtime.
  Resample to 16 kHz mono before submission for reliable results.
- **The `text` field trims leading/trailing silence.** Short clips of pure
  silence return `text: ""` — handle the empty-string case.
- **Inference can take 5–30 s for a 30-minute recording chunk.** This exceeds
  the default 30 s Worker CPU limit on Standard plans. Use Workers Unbound, or
  break into smaller chunks processed in a Queue consumer.
- **Whisper does not return confidence scores per word in the Workers AI API.**
  The `words` array has `start`/`end` timestamps only. If you need per-word
  confidence, use a different provider or post-process with a language model.

## Verification

```bash
# Transcribe a short WAV file directly
curl -X POST https://transcribe.example.com/ \
  -H "Content-Type: audio/wav" \
  --data-binary @/path/to/sample.wav
# → {"text":"Hello this is a test recording.","wordCount":6}

# Check Workers AI usage in the dashboard
# Workers & Pages → your worker → Metrics → AI Requests

# Test empty audio handling
curl -X POST https://transcribe.example.com/ \
  -H "Content-Type: audio/wav" \
  --data-binary @/dev/null
# → {"text":"","wordCount":0} or a 400 error if you validate size first
```

## Related

- `cloudflare/workers-ai-edge-inference.md`
- `cloudflare/workers-ai-text-to-image-generation.md`
- `cloudflare/workers-ai-vision-image-to-text.md`
- `cloudflare/queues-batch-processing.md`
- `cloudflare/r2-best-practices.md`
- Whisper model page: https://developers.cloudflare.com/workers-ai/models/whisper/
- Workers AI models: https://developers.cloudflare.com/workers-ai/models/

## Sources

- https://developers.cloudflare.com/workers-ai/models/whisper/
- https://developers.cloudflare.com/workers-ai/
- https://openai.com/research/whisper
