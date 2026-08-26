# Workers AI Text-to-Speech with Audio Streaming and R2 Storage

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to generate speech from text in a Cloudflare Worker, stream the audio to the client for fast first-byte playback, persist the `.wav` file in R2 to avoid regenerating identical audio, and cache the R2 key in KV so repeat requests skip the AI call entirely.

## Context

Workers AI exposes `@cf/microsoft/speecht5-tts` for text-to-speech. The model accepts a `text` string and optional `speaker_embeddings` (a Float32Array or base64 string that controls speaker voice). The response is an `ArrayBuffer` containing a valid `.wav` file. Because TTS is expensive, a two-level cache — KV for key lookup, R2 for the binary blob — prevents redundant inference and keeps latency low for repeated phrases.

Required bindings in `wrangler.toml`:
- `ai` — Workers AI binding
- `R2_AUDIO` — R2 bucket for `.wav` storage
- `KV_TTS` — KV namespace for deduplication keys

## Implementation

```typescript
import { Hono } from 'hono';

type Env = {
  AI: Ai;
  R2_AUDIO: R2Bucket;
  KV_TTS: KVNamespace;
  AUDIO_SIGNED_URL_SECRET: string;
};

const app = new Hono<{ Bindings: Env }>();

// Derive a stable cache key from text + voice identifier.
async function ttsKey(text: string, voice: string): Promise<string> {
  const raw = new TextEncoder().encode(`${voice}::${text}`);
  const hashBuf = await crypto.subtle.digest('SHA-256', raw);
  const hashArr = Array.from(new Uint8Array(hashBuf));
  return 'tts/' + hashArr.map(b => b.toString(16).padStart(2, '0')).join('');
}

// Generate or retrieve TTS audio.
async function getOrGenerateAudio(
  env: Env,
  text: string,
  voice: string,
  speakerEmbeddings: number[] | undefined,
): Promise<{ r2Key: string; audioBuffer: ArrayBuffer; fromCache: boolean }> {
  const r2Key = await ttsKey(text, voice);

  // Level 1: KV lookup (fast path — no R2 GET if KV miss means we must generate).
  const kvHit = await env.KV_TTS.get(r2Key);
  if (kvHit !== null) {
    // Level 2: R2 fetch.
    const obj = await env.R2_AUDIO.get(r2Key);
    if (obj) {
      return { r2Key, audioBuffer: await obj.arrayBuffer(), fromCache: true };
    }
    // KV hit but R2 miss — stale KV entry; fall through to regenerate.
    await env.KV_TTS.delete(r2Key);
  }

  // Generate via Workers AI.
  const result = await env.AI.run('@cf/microsoft/speecht5-tts', {
    text,
    ...(speakerEmbeddings ? { speaker_embeddings: speakerEmbeddings } : {}),
  });

  // `result` is an object with an `audio` ArrayBuffer field.
  const audioBuffer: ArrayBuffer = (result as any).audio;

  // Persist to R2 with a long-lived Cache-Control header.
  await env.R2_AUDIO.put(r2Key, audioBuffer, {
    httpMetadata: {
      contentType: 'audio/wav',
      cacheControl: 'public, max-age=31536000, immutable',
    },
    customMetadata: { voice, generatedAt: new Date().toISOString() },
  });

  // Write KV key (TTL: 30 days) to short-circuit future R2 HEADs.
  await env.KV_TTS.put(r2Key, '1', { expirationTtl: 60 * 60 * 24 * 30 });

  return { r2Key, audioBuffer, fromCache: false };
}

// Issue a time-limited signed URL so clients fetch directly from R2.
async function signedR2Url(
  r2Key: string,
  secret: string,
  expiresInSeconds = 3600,
): Promise<string> {
  const expires = Math.floor(Date.now() / 1000) + expiresInSeconds;
  const payload = new TextEncoder().encode(`${r2Key}:${expires}`);
  const keyMaterial = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const sig = await crypto.subtle.sign('HMAC', keyMaterial, payload);
  const sigHex = Array.from(new Uint8Array(sig))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
  return `https://audio.example.com/${r2Key}?expires=${expires}&sig=${sigHex}`;
}

app.post('/tts', async (c) => {
  const { text, voice = 'default', speaker_embeddings } = await c.req.json<{
    text: string;
    voice?: string;
    speaker_embeddings?: number[];
  }>();

  if (!text || text.length > 4096) {
    return c.json({ error: 'text required, max 4096 chars' }, 400);
  }

  const { r2Key, fromCache } = await getOrGenerateAudio(
    c.env, text, voice, speaker_embeddings,
  );

  const url = await signedR2Url(r2Key, c.env.AUDIO_SIGNED_URL_SECRET);

  return c.json({ url, fromCache, format: 'wav' });
});

export default app;
```

## Streaming Audio Directly to the Client

For sub-second first-byte latency, stream the `ArrayBuffer` as a chunked response instead of returning a signed URL:

```typescript
app.post('/tts/stream', async (c) => {
  const { text, voice = 'default' } = await c.req.json<{ text: string; voice?: string }>();

  const { audioBuffer } = await getOrGenerateAudio(c.env, text, voice, undefined);

  // Wrap the ArrayBuffer in a ReadableStream for streaming transfer.
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new Uint8Array(audioBuffer));
      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'audio/wav',
      'Cache-Control': 'no-store',
      'Transfer-Encoding': 'chunked',
    },
  });
});
```

## R2 Signed-URL Verification Worker

Deploy a separate Worker (or route) on `audio.example.com` that validates the HMAC before proxying the R2 object:

```typescript
export default {
  async fetch(request: Request, env: { R2_AUDIO: R2Bucket; SECRET: string }): Promise<Response> {
    const url = new URL(request.url);
    const r2Key = url.pathname.slice(1);  // strip leading '/'
    const expires = Number(url.searchParams.get('expires'));
    const sig = url.searchParams.get('sig') ?? '';

    if (Date.now() / 1000 > expires) return new Response('Link expired', { status: 410 });

    // Re-derive expected signature.
    const payload = new TextEncoder().encode(`${r2Key}:${expires}`);
    const keyMat = await crypto.subtle.importKey(
      'raw', new TextEncoder().encode(env.SECRET),
      { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'],
    );
    const expected = Array.from(new Uint8Array(await crypto.subtle.sign('HMAC', keyMat, payload)))
      .map(b => b.toString(16).padStart(2, '0')).join('');

    if (expected !== sig) return new Response('Forbidden', { status: 403 });

    const obj = await env.R2_AUDIO.get(r2Key);
    if (!obj) return new Response('Not found', { status: 404 });

    return new Response(obj.body, {
      headers: {
        'Content-Type': obj.httpMetadata?.contentType ?? 'audio/wav',
        'Cache-Control': 'private, max-age=3600',
      },
    });
  },
};
```

## Anti-patterns

- **Storing audio in KV** — KV values max out at 25 MB; `.wav` files frequently exceed this. Always use R2 for binary blobs.
- **Re-generating on every request** — Even short phrases can cost 200-400 ms of inference time. Always check KV before calling `env.AI.run`.
- **Embedding the raw audio in the JSON response** — Base64-encoding a `.wav` inflates size by ~33% and blocks streaming. Return a URL or stream the binary directly.
- **Serving R2 objects without signed URLs** — Public R2 buckets expose all stored audio; always sign or gate behind a Worker.

## Gotchas

- `speecht5-tts` returns `{ audio: ArrayBuffer }`, not a bare `ArrayBuffer`. Destructure `result.audio`.
- The generated `.wav` has a fixed 16 kHz sample rate; resample on the client if your player requires a different rate.
- KV `expirationTtl` must be at least 60 seconds; values shorter than that are rejected.
- R2 `put` is not atomic with KV `put` — a Worker crash between them leaves a KV key with no corresponding R2 object. The code above handles this stale-key case by re-generating.

## Verification

```bash
# Generate and cache a TTS clip.
curl -s -X POST https://worker.example.com/tts \
  -H 'Content-Type: application/json' \
  -d '{"text": "Hello, world!", "voice": "default"}' | jq .
# Expected: { url: "https://audio.example.com/tts/<hash>?...", fromCache: false, format: "wav" }

# Second request — should return fromCache: true and the same URL path.
curl -s -X POST https://worker.example.com/tts \
  -H 'Content-Type: application/json' \
  -d '{"text": "Hello, world!", "voice": "default"}' | jq .fromCache
# Expected: true

# Fetch the signed URL and verify it is valid WAV audio.
curl -s "$(curl -s -X POST ... | jq -r .url)" | file -
# Expected: RIFF (little-endian) data, WAVE audio
```

## Related

- `workers-ai-image-generation-r2-pipeline.md` — same R2 + D1 deduplication pattern for images
- `llm-token-streaming-backpressure-workers.md` — streaming patterns in Workers AI
- `rag-citation-grounding-vectorize-workers.md` — Vectorize + Workers AI pipeline patterns

## Sources

- [Workers AI — Speech models](https://developers.cloudflare.com/workers-ai/models/speecht5-tts/)
- [R2 — Object storage](https://developers.cloudflare.com/r2/)
- [KV — Expiration TTL](https://developers.cloudflare.com/kv/api/write-key-value-pairs/#expiring-keys)
