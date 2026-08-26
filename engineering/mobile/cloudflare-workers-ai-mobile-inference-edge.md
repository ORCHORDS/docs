# Cloudflare Workers AI as Mobile Inference Backend vs On-Device ML

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

example project (example.com) needs AI-powered features — text generation, image classification, audio transcription, embedding search — on mobile devices. The question is whether to run inference on-device (Core ML / ONNX Runtime / MediaPipe) or off-load to Cloudflare Workers AI. Each approach has distinct trade-offs around latency, model freshness, bundle size, privacy, cost, and network dependency.

## Context

Cloudflare Workers AI provides a REST-style binding (`env.AI.run(model, inputs)`) that executes curated ML models on Cloudflare's GPU fleet, available in your Worker with no additional infrastructure. On mobile, the Worker becomes a thin proxy that the app calls over HTTPS — no SDK installation, no model download, no device GPU required.

On-device inference (Core ML on iOS, ONNX Runtime / TFLite / MediaPipe on Android) keeps data on the device, works offline, and avoids per-call API costs, but increases app size, requires model versioning, and is constrained by device hardware.

This article focuses on the **hybrid architecture** used by example project: Workers AI for heavy/fresh models (LLMs, Whisper transcription, CLIP embeddings), on-device for latency-critical tasks (wake-word detection, face framing, text autocomplete).

---

## 1. Workers AI Inference Endpoint

```ts
// workers/ai-proxy/src/index.ts
import { Hono } from 'hono'
import { cors } from 'hono/cors'
import { bearerAuth } from 'hono/bearer-auth'

interface Env {
  AI: Ai
  AI_CACHE: KVNamespace
}

const app = new Hono<{ Bindings: Env }>()
app.use('*', cors({ origin: 'https://example.com' }))
app.use('*', bearerAuth({ token: (token) => verifyJwt(token) }))

// Text generation (Llama 3)
app.post('/ai/generate', async (c) => {
  const { prompt, maxTokens = 512, stream = false } = await c.req.json()

  if (stream) {
    const response = await c.env.AI.run(
      '@cf/meta/llama-3.1-8b-instruct',
      { prompt, max_tokens: maxTokens, stream: true }
    )
    // Stream SSE back to the mobile client
    return new Response(response as ReadableStream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',
      },
    })
  }

  const result = await c.env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
    prompt,
    max_tokens: maxTokens,
  }) as { response: string }

  return c.json({ text: result.response })
})

// Whisper transcription
app.post('/ai/transcribe', async (c) => {
  const formData = await c.req.formData()
  const audio    = formData.get('audio') as File
  if (!audio) return c.json({ error: 'No audio file' }, 400)

  const buffer = await audio.arrayBuffer()

  const result = await c.env.AI.run('@cf/openai/whisper', {
    audio: [...new Uint8Array(buffer)],
  }) as { text: string }

  return c.json({ transcript: result.text })
})

// Text embedding for semantic search
app.post('/ai/embed', async (c) => {
  const { texts } = await c.req.json<{ texts: string[] }>()

  const cacheKey = `embed:${await hashTexts(texts)}`
  const cached = await c.env.AI_CACHE.get(cacheKey, 'json')
  if (cached) return c.json(cached)

  const result = await c.env.AI.run('@cf/baai/bge-small-en-v1.5', {
    text: texts,
  }) as { data: number[][] }

  await c.env.AI_CACHE.put(cacheKey, JSON.stringify(result), { expirationTtl: 3600 })
  return c.json(result)
})

async function hashTexts(texts: string[]): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-1', new TextEncoder().encode(texts.join('|')))
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('')
}

export default app
```

`wrangler.toml` binding:

```toml
[ai]
binding = "AI"

[[kv_namespaces]]
binding = "AI_CACHE"
id = "your-kv-namespace-id"
```

---

## 2. React Native: Streaming Text Generation

`fetch` with `ReadableStream` works in React Native's Hermes engine (RN 0.73+). For older versions, fall back to polling:

```ts
// src/ai/useTextGeneration.ts
import { useState, useCallback } from 'react'

export function useTextGeneration() {
  const [output, setOutput] = useState('')
  const [loading, setLoading] = useState(false)

  const generate = useCallback(async (prompt: string) => {
    setOutput('')
    setLoading(true)

    const res = await fetch('https://api.example.com/ai/generate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${getToken()}`,
      },
      body: JSON.stringify({ prompt, stream: true }),
    })

    if (!res.ok || !res.body) {
      setLoading(false)
      throw new Error(`Generation failed: ${res.status}`)
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const data = line.slice(6).trim()
          if (data === '[DONE]') break
          try {
            const parsed = JSON.parse(data) as { response?: string }
            if (parsed.response) {
              setOutput(prev => prev + parsed.response)
            }
          } catch { /* ignore malformed chunks */ }
        }
      }
    } finally {
      reader.releaseLock()
      setLoading(false)
    }
  }, [])

  return { output, loading, generate }
}
```

---

## 3. Audio Transcription from React Native

```ts
// src/ai/transcribeAudio.ts
import * as FileSystem from 'expo-file-system'

export async function transcribeAudio(audioUri: string): Promise<string> {
  // Read audio as base64, convert to Blob for FormData
  const base64 = await FileSystem.readAsStringAsync(audioUri, {
    encoding: FileSystem.EncodingType.Base64,
  })

  const binaryStr = atob(base64)
  const bytes = new Uint8Array(binaryStr.length)
  for (let i = 0; i < binaryStr.length; i++) bytes[i] = binaryStr.charCodeAt(i)
  const blob = new Blob([bytes], { type: 'audio/wav' })

  const formData = new FormData()
  formData.append('audio', blob, 'recording.wav')

  const res = await fetch('https://api.example.com/ai/transcribe', {
    method: 'POST',
    headers: { Authorization: `Bearer ${getToken()}` },
    body: formData,
  })

  if (!res.ok) throw new Error(`Transcription failed: ${res.status}`)
  const { transcript } = await res.json()
  return transcript
}
```

Worker AI Whisper accepts audio up to **25 MB** as a `number[]` (Uint8Array coerced). For longer recordings, split at silence boundaries client-side and concatenate transcripts.

---

## 4. Decision Matrix: Workers AI vs On-Device

| Capability | Workers AI | On-Device |
|---|---|---|
| **Offline support** | No | Yes |
| **Latency (P50)** | 300–800 ms (cold) / 100–200 ms (warm) | 20–150 ms |
| **App size impact** | None | +10 MB (TFLite) to +2 GB (large LLM) |
| **Model freshness** | Controlled by Cloudflare / your Worker deploy | Locked to app version |
| **Privacy** | Audio/text leaves the device | Data stays on device |
| **Cost** | Per-neuron-second billing | Device CPU/GPU |
| **Supported models** | Llama 3, Mistral, Whisper, CLIP, BGE, etc. | Custom ONNX / Core ML / TFLite |
| **Suitable for example project** | Transcription, semantic search, content gen | Wake word, face framing, autocomplete |

Hybrid rule of thumb for example project:
- **< 50 ms latency required** → on-device
- **> 500 MB model size** → Workers AI (avoids app size)
- **PHI / sensitive user content** → on-device only (HIPAA boundary)
- **Model needs weekly updates** → Workers AI (redeploy Worker, no app update)

---

## 5. Cost Management and Rate Limiting

Workers AI bills per number of neurons processed. Mobile apps can generate unexpectedly high call volumes. Protect costs with a per-user rate limiter in the Worker:

```ts
// middleware: rate limit AI endpoints to 100 calls / user / hour
app.use('/ai/*', async (c, next) => {
  const userId  = c.get('userId') as string
  const hourKey = `ratelimit:ai:${userId}:${Math.floor(Date.now() / 3_600_000)}`

  const current = parseInt(await c.env.AI_CACHE.get(hourKey) ?? '0')
  if (current >= 100) {
    return c.json({ error: 'rate_limit_exceeded', retryAfter: 3600 }, 429)
  }
  await c.env.AI_CACHE.put(hourKey, String(current + 1), { expirationTtl: 7200 })
  await next()
})
```

---

## Anti-patterns

- **Streaming to the Worker and re-streaming to mobile via a single Worker response** — Cloudflare Workers support streaming, but the Workers AI response must be correctly piped without buffering. Returning `new Response(stream)` works; `c.json(await stream)` awaits and buffers the full LLM output before sending, defeating the purpose of streaming.
- **Storing AI model weights in R2 and loading in the Worker** — Workers have a 128 MB memory limit. You cannot load arbitrary model weights in a Worker runtime; use the `env.AI` binding which offloads to Cloudflare's GPU fleet.
- **Sending raw audio > 25 MB to Whisper** — the Workers AI Whisper endpoint rejects payloads above this limit. Chunk recordings at silence boundaries first.
- **Calling Workers AI from the mobile client directly** — Workers AI requires a `CF-AI-Gateway` or Workers binding; there is no public REST endpoint for mobile clients to call directly. Always proxy through your own Worker.
- **Ignoring cold-start latency** — Workers AI on a cold GPU can take 2–4 seconds for the first request after inactivity. Implement a loading state in the UI and a 5-second timeout with retry.

---

## Gotchas

- **Workers AI model IDs change**: Cloudflare occasionally retires model versions. Pin your Worker to a specific versioned model ID (`@cf/meta/llama-3.1-8b-instruct` not `@cf/meta/llama-3`). Subscribe to the Workers AI changelog.
- **`stream: true` requires Hermes 0.12+ (React Native 0.73+)**: older Hermes versions lack `ReadableStream` support. Detect with `typeof ReadableStream !== 'undefined'` and fall back to non-streaming.
- **FormData with Blob on React Native < 0.71**: `new Blob([bytes])` returns an empty blob in older RN versions. Use `react-native-blob-util` or pass the file URI directly to `FormData.append` (RN handles the multipart boundary natively for file URIs).
- **Workers AI neurons billing on error responses**: if your prompt triggers a content moderation refusal, you are still charged for the input token processing. Implement prompt validation before calling the AI binding.
- **BGE embedding dimensions**: `@cf/baai/bge-small-en-v1.5` returns 384-dimensional vectors. If you later switch to `@cf/baai/bge-large-en-v1.5` (1024-dim), all existing embeddings stored in Vectorize or D1 become incompatible. Plan embedding dimension migrations carefully.

---

## Verification

```bash
# Test text generation endpoint
curl -X POST https://api.example.com/ai/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Summarise example project in one sentence.","maxTokens":64}' | jq .

# Test Whisper transcription with a sample WAV
curl -X POST https://api.example.com/ai/transcribe \
  -H "Authorization: Bearer $TOKEN" \
  -F "audio=@sample.wav" | jq .

# Test embedding endpoint
curl -X POST https://api.example.com/ai/embed \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"texts":["hello world","test embedding"]}' | jq '.data | length'

# Check Workers AI usage in Cloudflare dashboard
wrangler ai models list
```

---

## Related

- `mobile-on-device-ai-foundation-models.md` — Apple Foundation Models and Android AICore (on-device path)
- `cloudflare-workers-response-streaming-mobile-buffer-limits.md` — SSE streaming buffer pitfalls on mobile
- `mobile-network-resilience-cloudflare-workers.md` — Retry strategies for AI endpoint latency spikes
- `react-native-hermes-performance-profiling.md` — Profiling Hermes JS engine during AI-heavy workloads
- `mobile-slow-network-testing.md` — Testing AI streaming on throttled connections

---

## Sources

- [Cloudflare Workers AI documentation](https://developers.cloudflare.com/workers-ai/)
- [Workers AI model catalog](https://developers.cloudflare.com/workers-ai/models/)
- [Workers AI streaming guide](https://developers.cloudflare.com/workers-ai/configuration/streaming/)
- [Whisper audio transcription limits](https://developers.cloudflare.com/workers-ai/models/whisper/)
- [BGE embedding models on Workers AI](https://developers.cloudflare.com/workers-ai/models/bge-small-en-v1.5/)
- [React Native ReadableStream support (Hermes)](https://reactnative.dev/docs/0.73/new-architecture-intro)
