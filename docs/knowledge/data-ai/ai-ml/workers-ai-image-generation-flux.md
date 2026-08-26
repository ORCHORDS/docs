# Workers AI Image Generation with Flux

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to generate images on-demand from text prompts — product mock-ups, AI avatars, banner art — without managing GPU infrastructure. Workers AI exposes `@cf/black-forest-labs/flux-1-schnell` (and Stable Diffusion variants) as a serverless endpoint. This article covers prompt engineering, returning binary PNG responses, persisting generated images to R2 with metadata, per-user rate limiting via KV, and offloading slow generations to a Queue for async delivery.

---

## Context

`flux-1-schnell` is a fast, 4-step distilled text-to-image model optimised for speed over quality. It returns raw binary PNG data. Image generation is the most GPU-intensive Workers AI workload — a single call can take 5–15 seconds depending on resolution and queue depth. For user-facing features, async generation (Queue → R2 → webhook) is almost always preferable to synchronous HTTP.

---

## Solution

```typescript
// src/index.ts
import { Ai } from '@cloudflare/ai';

export interface Env {
  AI: Ai;
  IMAGES: R2Bucket;
  RATE_LIMIT: KVNamespace;
  IMAGE_QUEUE: Queue;
}

// ── Rate limiting ─────────────────────────────────────────────────────────────
// Allow each user (identified by an API key or user ID) N generations per hour.

const RATE_LIMIT_PER_HOUR = 10;
const RATE_LIMIT_WINDOW_SECONDS = 60 * 60; // 1 hour

interface RateLimitState {
  count: number;
  window_start: number; // Unix epoch seconds
}

async function checkRateLimit(
  userId: string,
  env: Env
): Promise<{ allowed: boolean; remaining: number; resetAt: number }> {
  const key = `rate:img:${userId}`;
  const raw = await env.RATE_LIMIT.get(key, { type: 'json' }) as RateLimitState | null;
  const now = Math.floor(Date.now() / 1000);

  if (!raw || now - raw.window_start >= RATE_LIMIT_WINDOW_SECONDS) {
    // Start a fresh window.
    const state: RateLimitState = { count: 1, window_start: now };
    await env.RATE_LIMIT.put(key, JSON.stringify(state), {
      expirationTtl: RATE_LIMIT_WINDOW_SECONDS,
    });
    return {
      allowed: true,
      remaining: RATE_LIMIT_PER_HOUR - 1,
      resetAt: now + RATE_LIMIT_WINDOW_SECONDS,
    };
  }

  if (raw.count >= RATE_LIMIT_PER_HOUR) {
    return {
      allowed: false,
      remaining: 0,
      resetAt: raw.window_start + RATE_LIMIT_WINDOW_SECONDS,
    };
  }

  // Increment within the existing window.
  const updated: RateLimitState = { ...raw, count: raw.count + 1 };
  await env.RATE_LIMIT.put(key, JSON.stringify(updated), {
    expirationTtl: RATE_LIMIT_WINDOW_SECONDS - (now - raw.window_start),
  });
  return {
    allowed: true,
    remaining: RATE_LIMIT_PER_HOUR - updated.count,
    resetAt: raw.window_start + RATE_LIMIT_WINDOW_SECONDS,
  };
}

// ── Prompt engineering helpers ────────────────────────────────────────────────

interface PromptOptions {
  subject: string;
  style?: string;
  quality?: 'draft' | 'standard' | 'high';
  negativePrompt?: string;
}

function buildPrompt(opts: PromptOptions): {
  prompt: string;
  negative_prompt: string;
} {
  const qualityModifiers: Record<string, string> = {
    draft:    '',
    standard: ', sharp focus, detailed',
    high:     ', ultra-detailed, 8k resolution, professional photography, sharp focus, studio lighting',
  };
  const styleMap: Record<string, string> = {
    photorealistic: 'photorealistic, DSLR photo',
    illustration:   'digital illustration, vibrant colors',
    sketch:         'pencil sketch, hand-drawn',
    'oil-painting': 'oil painting, textured canvas',
  };

  const quality = opts.quality ?? 'standard';
  const styleSuffix = opts.style ? `, ${styleMap[opts.style] ?? opts.style}` : '';
  const qualitySuffix = qualityModifiers[quality];

  const prompt = `${opts.subject}${styleSuffix}${qualitySuffix}`;
  const negative_prompt = opts.negativePrompt ??
    'blurry, low quality, distorted, watermark, text, ugly, deformed';

  return { prompt, negative_prompt };
}

// ── Image generation ──────────────────────────────────────────────────────────

interface GenerationResult {
  imageBytes: Uint8Array;
  prompt: string;
  model: string;
  durationMs: number;
}

async function generateImage(
  promptOpts: PromptOptions,
  env: Env
): Promise<GenerationResult> {
  const { prompt, negative_prompt } = buildPrompt(promptOpts);
  const t0 = Date.now();

  // Workers AI returns raw binary for image models.
  const result = await env.AI.run(
    '@cf/black-forest-labs/flux-1-schnell',
    {
      prompt,
      negative_prompt,
      num_steps: 4,      // flux-1-schnell is a 4-step distilled model
      width:  1024,
      height: 1024,
    }
  );

  // The binding returns { image: string } where image is base64-encoded PNG.
  const b64 = (result as unknown as { image: string }).image;
  const binary = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));

  return {
    imageBytes: binary,
    prompt,
    model: '@cf/black-forest-labs/flux-1-schnell',
    durationMs: Date.now() - t0,
  };
}

// ── R2 storage ───────────────────────────────────────────────────────────────

interface R2ImageMetadata {
  userId: string;
  prompt: string;
  model: string;
  durationMs: number;
  createdAt: string;
}

async function storeImage(
  gen: GenerationResult,
  userId: string,
  env: Env
): Promise<{ key: string; url: string }> {
  const imageId = crypto.randomUUID();
  const key = `images/${userId}/${imageId}.png`;

  const metadata: R2ImageMetadata = {
    userId,
    prompt:     gen.prompt,
    model:      gen.model,
    durationMs: gen.durationMs,
    createdAt:  new Date().toISOString(),
  };

  await env.IMAGES.put(key, gen.imageBytes, {
    httpMetadata:   { contentType: 'image/png' },
    customMetadata: metadata as unknown as Record<string, string>,
  });

  // Public URL if the bucket has a custom domain; otherwise use a signed URL pattern.
  const url = `https://images.example.com/${key}`;
  return { key, url };
}

// ── Async generation via Queue ─────────────────────────────────────────────
// For long-running jobs, enqueue the request and return a job ID immediately.
// A Queue consumer Worker performs generation and writes to R2.

interface QueueMessage {
  jobId: string;
  userId: string;
  promptOpts: PromptOptions;
  webhookUrl?: string;
}

async function enqueueGeneration(
  userId: string,
  promptOpts: PromptOptions,
  webhookUrl: string | undefined,
  env: Env
): Promise<string> {
  const jobId = crypto.randomUUID();
  const msg: QueueMessage = { jobId, userId, promptOpts, webhookUrl };
  await env.IMAGE_QUEUE.send(msg);
  return jobId;
}

// ── Queue consumer (separate Worker export) ───────────────────────────────────

export const queue = {
  async process(
    batch: MessageBatch<QueueMessage>,
    env: Env
  ): Promise<void> {
    for (const message of batch.messages) {
      const { jobId, userId, promptOpts, webhookUrl } = message.body;
      try {
        const gen = await generateImage(promptOpts, env);
        const { key, url } = await storeImage(gen, userId, env);

        if (webhookUrl) {
          await fetch(webhookUrl, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ jobId, status: 'done', url, key }),
          });
        }
        message.ack();
      } catch (err) {
        console.error(`Job ${jobId} failed:`, err);
        // Retry up to 3 times via Queue's built-in retry mechanism.
        message.retry();
      }
    }
  },
};

// ── Synchronous request handler ───────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405 });
    }

    const userId = request.headers.get('X-User-Id') ?? 'anonymous';

    // Rate-limit check.
    const rl = await checkRateLimit(userId, env);
    if (!rl.allowed) {
      return Response.json(
        { error: 'Rate limit exceeded', reset_at: rl.resetAt },
        {
          status: 429,
          headers: {
            'X-RateLimit-Limit':     String(RATE_LIMIT_PER_HOUR),
            'X-RateLimit-Remaining': '0',
            'X-RateLimit-Reset':     String(rl.resetAt),
          },
        }
      );
    }

    const body = await request.json<{
      subject: string;
      style?: string;
      quality?: 'draft' | 'standard' | 'high';
      negative_prompt?: string;
      async?: boolean;
      webhook_url?: string;
    }>();

    if (!body.subject) {
      return Response.json({ error: 'subject is required' }, { status: 400 });
    }

    const promptOpts: PromptOptions = {
      subject:        body.subject,
      style:          body.style,
      quality:        body.quality,
      negativePrompt: body.negative_prompt,
    };

    // Async path — return job ID immediately.
    if (body.async) {
      const jobId = await enqueueGeneration(
        userId,
        promptOpts,
        body.webhook_url,
        env
      );
      return Response.json({ job_id: jobId, status: 'queued' }, { status: 202 });
    }

    // Synchronous path — generate and return binary PNG.
    const gen = await generateImage(promptOpts, env);
    const { key, url } = await storeImage(gen, userId, env);

    // Return the PNG directly; include metadata as headers.
    return new Response(gen.imageBytes, {
      headers: {
        'Content-Type':        'image/png',
        'X-Image-Key':         key,
        'X-Image-Url':         url,
        'X-Generation-Ms':     String(gen.durationMs),
        'X-RateLimit-Remaining': String(rl.remaining),
      },
    });
  },
};
```

### wrangler.toml additions

```toml
[[r2_buckets]]
binding = "IMAGES"
bucket_name = "orchords-generated-images"

[[kv_namespaces]]
binding = "RATE_LIMIT"
id      = "<rate-limit-kv-id>"

[[queues.producers]]
binding = "IMAGE_QUEUE"
queue   = "image-generation"

[[queues.consumers]]
queue             = "image-generation"
max_batch_size    = 5
max_batch_timeout = 30
max_retries       = 3
deadLetter        = "image-generation-dlq"
```

---

## Implementation Details

**Binary response**: Workers AI image models return `{ image: string }` where `image` is a base64-encoded PNG. Convert with `atob` + `Uint8Array.from`. The `image/png` `Content-Type` lets browsers render it directly.

**Resolution**: `flux-1-schnell` supports multiples of 64 up to 1360×1360. Larger resolutions increase inference time and may hit the 30-second CPU limit. Start with 1024×1024.

**num_steps**: Flux Schnell is distilled for 4 steps. More steps do not improve quality and waste time. Stable Diffusion models (`@cf/stabilityai/stable-diffusion-xl-base-1.0`) typically use 20–50 steps.

**R2 custom metadata**: Values must be strings. Cast the `R2ImageMetadata` interface accordingly.

**Queue retry**: `message.retry()` re-enqueues with exponential back-off up to `max_retries`. The DLQ catches exhausted messages for inspection.

---

## Anti-patterns

- **Returning the base64 string directly to clients**: Always decode to binary and set `Content-Type: image/png`. Base64 inflates payload size by ~33%.
- **Synchronous generation for >5 second workloads**: Workers have a 30-second wall-clock limit. Flux at 1024×1024 can hit 15 s under load — use the Queue path for production.
- **No rate limiting**: Image generation is expensive. Without rate limiting a single user can drain your Workers AI credits.
- **Storing images in KV**: KV values are limited to 25 MB and not optimised for binary blobs. Use R2.
- **Hardcoding negative prompts**: Expose `negative_prompt` as an API parameter so clients can tune quality without redeployment.

---

## Gotchas

- `flux-1-schnell` requires `num_steps: 4` specifically; other values produce degraded output.
- The Workers AI image binding type does not yet expose the raw binary directly — you must decode the base64 `image` field.
- R2 `customMetadata` values are coerced to strings; numeric fields like `durationMs` must be re-parsed on read.
- Queues in local dev (`wrangler dev`) require `--experimental-local` or remote mode to actually process messages.
- The `X-User-Id` header is unauthenticated in this example. In production, derive user identity from a verified JWT or Cloudflare Access header.

---

## Verification

```bash
# Synchronous generation — save PNG
curl -s -X POST http://localhost:8787 \
  -H 'Content-Type: application/json' \
  -H 'X-User-Id: test-user' \
  -d '{"subject": "a golden retriever on a surfboard at sunset", "quality": "standard"}' \
  --output generated.png
file generated.png  # should report: PNG image data

# Async generation
curl -s -X POST http://localhost:8787 \
  -H 'Content-Type: application/json' \
  -H 'X-User-Id: test-user' \
  -d '{"subject": "futuristic city skyline", "async": true, "webhook_url": "https://your-webhook.example.com"}' | jq .

# Rate limit test (run 11 times rapidly)
for i in $(seq 1 11); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8787 \
    -H 'Content-Type: application/json' \
    -H 'X-User-Id: rate-test-user' \
    -d '{"subject": "test"}'
done
# 11th request should return 429
```

---

## Related

- `documentation/docs/policies/ai-ml/workers-ai-prompt-caching-kv.md` — cache identical prompt results
- Cloudflare R2 docs: https://developers.cloudflare.com/r2/
- Workers Queues docs: https://developers.cloudflare.com/queues/
- Flux-1-Schnell model card: https://developers.cloudflare.com/workers-ai/models/flux-1-schnell/

---

## Sources

- Cloudflare Workers AI image generation docs (2025)
- Black Forest Labs Flux-1-Schnell model card
- Cloudflare Queues best practices guide
