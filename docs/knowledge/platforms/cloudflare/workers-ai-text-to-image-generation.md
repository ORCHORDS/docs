# workers-ai-text-to-image-generation

Generate images from text prompts entirely at the edge using Workers AI
Stable Diffusion models — no external API keys, no egress fees, billed per
inference step.

**Date:** 2026-08-23
**Author:** example.com
**Status:** production

## Symptom / Use-case

You need on-demand image generation in a Worker:

- Produce OG images, avatars, or product mockups from user text
- Run Stable Diffusion without managing a GPU server or paying OpenAI/Replicate
- Keep generated images behind auth before optionally persisting them to R2
- Control image dimensions, steps, and guidance from the Worker without a
  separate inference service

## Context

Workers AI exposes Stable Diffusion models (e.g. `@cf/stabilityai/stable-diffusion-xl-base-1.0`,
`@cf/bytedance/stable-diffusion-xl-lightning`) as first-class AI bindings.
The model returns raw PNG bytes (`ReadableStream` or `ArrayBuffer`) that you
can stream directly to the client or store in R2. Unlike text models the
response is not JSON — it is a binary image blob.

Pricing is per inference step. Lightning variants (4–8 steps) are much cheaper
than the base model (20–50 steps). For real-time use cases, always prefer
Lightning; use the base model only when quality is critical and latency is
acceptable.

## Binding the AI model

```toml
# wrangler.toml
name = "image-gen-worker"
main = "src/index.ts"
compatibility_date = "2026-08-01"

[ai]
binding = "AI"
```

```typescript
// src/types.ts
export interface Env {
  AI: Ai;
  IMAGES: R2Bucket; // optional: persist results
}
```

## Generating an image and streaming it to the client

```typescript
// src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("POST a JSON body with { prompt }", { status: 405 });
    }

    const { prompt, steps = 8 } = await request.json<{
      prompt: string;
      steps?: number;
    }>();

    if (!prompt || prompt.length > 1000) {
      return new Response("Invalid prompt", { status: 400 });
    }

    // Run inference — returns a ReadableStream of PNG bytes
    const imageStream = await env.AI.run(
      "@cf/bytedance/stable-diffusion-xl-lightning",
      {
        prompt,
        num_steps: Math.min(steps, 20), // cap; Lightning peaks at 8
      }
    );

    return new Response(imageStream, {
      headers: {
        "Content-Type": "image/png",
        "Cache-Control": "private, max-age=0",
      },
    });
  },
};
```

## Persisting generated images to R2

```typescript
import { Env } from "./types";

export async function generateAndStore(
  env: Env,
  prompt: string,
  key: string
): Promise<string> {
  const imageStream = await env.AI.run(
    "@cf/bytedance/stable-diffusion-xl-lightning",
    { prompt, num_steps: 8 }
  );

  // ReadableStream → ArrayBuffer for R2 put
  const buffer = await new Response(imageStream).arrayBuffer();

  await env.IMAGES.put(key, buffer, {
    httpMetadata: { contentType: "image/png" },
    customMetadata: { prompt: prompt.slice(0, 512) },
  });

  // Return a presigned URL or a public URL depending on your R2 config
  return `https://images.example.com/${key}`;
}
```

## Caching generated images with KV or R2

Generating the same prompt twice wastes inference budget. Cache on the prompt
hash:

```typescript
import { Env } from "./types";

async function sha256Hex(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const hashBuffer = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export async function cachedGenerate(
  env: Env,
  prompt: string
): Promise<ArrayBuffer> {
  const cacheKey = `img-${await sha256Hex(prompt)}`;

  // Check R2 first
  const cached = await env.IMAGES.get(cacheKey);
  if (cached) return cached.arrayBuffer();

  // Cache miss → generate
  const stream = await env.AI.run(
    "@cf/bytedance/stable-diffusion-xl-lightning",
    { prompt, num_steps: 8 }
  );
  const buffer = await new Response(stream).arrayBuffer();

  // Store in R2 (async, do not block response)
  env.IMAGES.put(cacheKey, buffer.slice(0), {
    httpMetadata: { contentType: "image/png" },
  });

  return buffer;
}
```

## Choosing the right model

| Model | Steps | Speed | Quality | Use case |
|---|---|---|---|---|
| `stable-diffusion-xl-lightning` | 4-8 | ~1-2 s | Good | Real-time, OG images |
| `stable-diffusion-xl-base-1.0` | 20-50 | ~5-15 s | Best | Batch, high quality |
| `dreamshaper-8-lcm` | 4-8 | ~1 s | Good | Artistic styles |

Check `npx wrangler ai models` for the full current list; model availability
changes without notice.

## Anti-patterns

- **Returning the raw stream without `Content-Type: image/png`.** Browsers will
  not render the binary as an image. Always set the content type header.
- **Using base model steps (50) for real-time requests.** At 50 steps, SDXL
  takes 15+ seconds — well past the Worker 30 s CPU limit on Unbound plans.
  Use Lightning variants for synchronous responses.
- **Generating the same prompt on every request without caching.** Identical
  prompts produce identical (or near-identical) output. Cache on the prompt
  hash. Cost reduction is immediate.
- **Storing prompts verbatim in R2 keys.** Prompts can contain special
  characters that break R2 key naming. Hash the prompt and store the original
  in object metadata instead.
- **Ignoring content moderation.** Workers AI applies Cloudflare's safety
  classifier automatically, but passing user-supplied prompts directly without
  any input validation or rate limiting is a CSAM and abuse risk. Validate,
  rate-limit, and log prompt sources.

## Gotchas

- **`env.AI.run()` returns a `ReadableStream`, not an `ArrayBuffer`.** If you
  need to inspect byte length or store in R2, wrap in `new Response(stream).arrayBuffer()`.
  Consuming the stream twice (storing and streaming) requires `tee()` or buffer first.
- **Inference counts against your Workers AI token quota.** Each request is
  ~200-2000 "AI units" depending on model and steps. Monitor in the AI dashboard
  to avoid quota surprises.
- **Models are served from the nearest AI-capable PoP, not every edge node.**
  Smart Placement (`placement = { mode = "smart" }`) helps route the Worker to
  a PoP close to the AI inference cluster, reducing round-trip latency.
- **`num_steps` above the model maximum is silently clamped.** Lightning
  supports 1-8 steps; passing 20 still runs at 8. Check model docs.
- **Cold starts for AI bindings can exceed 5 s.** The first request in a fresh
  isolate loads model weights. Subsequent requests in the same isolate are fast.
  Use a warm-up cron trigger in latency-sensitive applications.

## Verification

- Deploy with `npx wrangler deploy` and POST `{ "prompt": "a red fox in snow" }`
- Confirm response `Content-Type` is `image/png` and the body is non-empty
- Check the Workers AI dashboard for token consumption after 10 requests
- Confirm cached requests (same prompt) skip inference by checking R2 for the
  hash key before and after
- Run `npx wrangler tail` during test to verify no unhandled exceptions

## Related

- `cloudflare/workers-ai-edge-inference.md`
- `cloudflare/workers-ai-vision-image-to-text.md`
- `cloudflare/r2-best-practices.md`
- `cloudflare/workers-ai-mobile-inference-latency.md`
- Workers AI models list: https://developers.cloudflare.com/workers-ai/models/
- Stable Diffusion XL Lightning: https://developers.cloudflare.com/workers-ai/models/stable-diffusion-xl-lightning/

## Sources

- https://developers.cloudflare.com/workers-ai/
- https://developers.cloudflare.com/workers-ai/models/stable-diffusion-xl-base-1-0/
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
