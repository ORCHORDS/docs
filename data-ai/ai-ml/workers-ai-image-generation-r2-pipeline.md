# Workers AI Image Generation Pipeline with R2 Storage

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to generate images on-demand from text prompts inside a Cloudflare Worker, deduplicate identical prompts via D1, store the resulting PNG in R2, and serve it with a 1-year immutable cache header — while blocking harmful prompts before generation.

## Context

Workers AI's `@cf/black-forest-labs/flux-1-schnell` model accepts a `prompt` string and `num_steps` (1-8; 4 gives a good quality/speed tradeoff). It returns `{ image: string }` where `image` is a base64-encoded PNG. The generation pipeline is: moderation check → D1 deduplication lookup → generate → decode base64 → R2 put → D1 insert → return signed URL. The D1 `generated_images` table acts as an append-only log that makes the pipeline idempotent.

Required bindings:
- `AI` — Workers AI
- `R2_IMAGES` — R2 bucket
- `DB` — D1 database

## Implementation

```typescript
import { Hono } from 'hono';

type Env = { AI: Ai; R2_IMAGES: R2Bucket; DB: D1Database };

const app = new Hono<{ Bindings: Env }>();

// ── Utilities ────────────────────────────────────────────────────────────────

async function sha256Hex(input: string): Promise<string> {
  const buf = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(input),
  );
  return Array.from(new Uint8Array(buf))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}

function base64ToUint8Array(b64: string): Uint8Array {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

// ── Schema (run once) ────────────────────────────────────────────────────────
// CREATE TABLE generated_images (
//   id           TEXT PRIMARY KEY,
//   prompt_hash  TEXT NOT NULL UNIQUE,
//   r2_key       TEXT NOT NULL,
//   model        TEXT NOT NULL,
//   generated_at INTEGER NOT NULL
// );

// ── Moderation pre-check ─────────────────────────────────────────────────────

async function isSafePrompt(env: Env, prompt: string): Promise<boolean> {
  const result = await env.AI.run('@cf/huggingface/distilbert-sst-2-int8', {
    text: prompt,
  });
  // The text classifier returns [{label, score}]; this model is sentiment-based
  // and is used here as a lightweight heuristic. Replace with a dedicated
  // content-safety model if available in your account.
  const preds = result as { label: string; score: number }[];
  // Reject prompts classified as strongly NEGATIVE (score > 0.95).
  const negative = preds.find(p => p.label === 'NEGATIVE');
  return !(negative && negative.score > 0.95);
}

// ── Main generation handler ──────────────────────────────────────────────────

app.post('/generate', async (c) => {
  const { prompt, num_steps = 4 } = await c.req.json<{
    prompt: string;
    num_steps?: number;
  }>();

  if (!prompt || prompt.length > 2000) {
    return c.json({ error: 'prompt required, max 2000 chars' }, 400);
  }
  if (num_steps < 1 || num_steps > 8) {
    return c.json({ error: 'num_steps must be 1-8' }, 400);
  }

  // Step 1: Moderation.
  const safe = await isSafePrompt(c.env, prompt);
  if (!safe) {
    return c.json({ error: 'Prompt rejected by content policy.' }, 422);
  }

  // Step 2: Deduplication via D1.
  const promptHash = await sha256Hex(prompt);
  const existing = await c.env.DB.prepare(
    'SELECT r2_key FROM generated_images WHERE prompt_hash = ?',
  ).bind(promptHash).first<{ r2_key: string }>();

  if (existing) {
    return c.json({
      r2Key: existing.r2_key,
      url: `https://images.example.com/${existing.r2_key}`,
      fromCache: true,
    });
  }

  // Step 3: Generate image.
  const aiResult = await c.env.AI.run('@cf/black-forest-labs/flux-1-schnell', {
    prompt,
    num_steps,
  }) as { image: string };

  // Step 4: Decode base64 → Uint8Array.
  const imageBytes = base64ToUint8Array(aiResult.image);

  // Step 5: Store in R2.
  const imageId = crypto.randomUUID();
  const r2Key = `images/${imageId}.png`;

  await c.env.R2_IMAGES.put(r2Key, imageBytes, {
    httpMetadata: {
      contentType: 'image/png',
      // Immutable: content is keyed by prompt hash, so it never changes.
      cacheControl: 'public, max-age=31536000, immutable',
    },
    customMetadata: {
      promptHash,
      model: 'flux-1-schnell',
      generatedAt: new Date().toISOString(),
    },
  });

  // Step 6: Record in D1.
  await c.env.DB.prepare(
    'INSERT INTO generated_images (id, prompt_hash, r2_key, model, generated_at) VALUES (?, ?, ?, ?, ?)'
  ).bind(imageId, promptHash, r2Key, 'flux-1-schnell', Date.now()).run();

  return c.json({
    r2Key,
    url: `https://images.example.com/${r2Key}`,
    fromCache: false,
  });
});

// ── Serve from R2 ─────────────────────────────────────────────────────────────

app.get('/images/:imageId', async (c) => {
  const r2Key = `images/${c.req.param('imageId')}`;
  const obj = await c.env.R2_IMAGES.get(r2Key);
  if (!obj) return c.json({ error: 'Not found' }, 404);

  return new Response(obj.body, {
    headers: {
      'Content-Type': 'image/png',
      'Cache-Control': 'public, max-age=31536000, immutable',
      'ETag': obj.etag ?? '',
    },
  });
});

export default app;
```

## D1 Schema Migration

```sql
-- migrations/0001_generated_images.sql
CREATE TABLE IF NOT EXISTS generated_images (
  id           TEXT    PRIMARY KEY,
  prompt_hash  TEXT    NOT NULL UNIQUE,
  r2_key       TEXT    NOT NULL,
  model        TEXT    NOT NULL,
  generated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prompt_hash ON generated_images(prompt_hash);
```

```bash
npx wrangler d1 migrations apply IMAGE_DB --remote
```

## Prompt Hashing Strategy

Hash only the canonical, whitespace-normalized prompt to maximise cache hit rate:

```typescript
async function canonicalHash(prompt: string): Promise<string> {
  const canonical = prompt.trim().toLowerCase().replace(/\s+/g, ' ');
  return sha256Hex(canonical);
}
```

Include `model` in the hash if you serve multiple image models from the same endpoint, so a prompt with `flux-1-schnell` and `stable-diffusion-xl` generates separate entries.

## Anti-patterns

- **Returning the base64 PNG in the JSON response** — inflates payload by ~33%; always write to R2 and return a URL.
- **Skipping the D1 uniqueness check** — `flux-1-schnell` at 4 steps costs ~2-3 s of CPU time; deduplication pays for itself after the first repeat request.
- **Using KV for the deduplication record** — KV does not support atomic upserts; two concurrent requests for the same prompt can race. D1's `UNIQUE` constraint on `prompt_hash` provides the atomicity guarantee.
- **Generating without moderation** — always run at least a heuristic safety check before calling the image model.

## Gotchas

- `flux-1-schnell` returns `{ image: string }` (base64 PNG), not an `ArrayBuffer`. Decode with `atob` before writing to R2.
- D1 `first()` returns `null` (not `undefined`) on a miss; the truthiness check `if (existing)` handles both correctly.
- `crypto.randomUUID()` is available in the Workers runtime without import.
- The moderation model used here (`distilbert-sst-2-int8`) is a sentiment classifier repurposed as a heuristic; it will miss many harmful prompts. Use a dedicated content-safety model in production.

## Verification

```bash
# Generate an image.
curl -X POST https://worker.example.com/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "a serene mountain lake at sunrise"}' | jq .
# Expected: { r2Key: "images/<uuid>.png", url: "...", fromCache: false }

# Repeat — should hit D1 cache.
curl -X POST https://worker.example.com/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "a serene mountain lake at sunrise"}' | jq .fromCache
# Expected: true

# Fetch the image.
curl -I https://worker.example.com/images/<uuid>.png
# Expected: Content-Type: image/png, Cache-Control: public, max-age=31536000, immutable
```

## Related

- `workers-ai-text-to-speech-audio-streaming-r2.md` — same R2 storage + KV caching pattern for audio
- `rag-citation-grounding-vectorize-workers.md` — Workers AI text pipelines
- `llm-token-streaming-backpressure-workers.md` — streaming AI responses

## Sources

- [Workers AI — Flux-1-schnell](https://developers.cloudflare.com/workers-ai/models/flux-1-schnell/)
- [R2 — Workers API](https://developers.cloudflare.com/r2/api/workers/workers-api-reference/)
- [D1 — Getting started](https://developers.cloudflare.com/d1/get-started/)
