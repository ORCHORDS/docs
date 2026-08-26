# Workers AI Stable Diffusion Image Generation

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to generate images on-demand from text prompts directly inside a Cloudflare Worker without managing GPU infrastructure. The Worker must stream the PNG response to the client in real time, optionally persist the output to R2, and protect the endpoint with a KV-backed token-bucket rate limiter.

---

## Context

Cloudflare Workers AI exposes `@cf/stabilityai/stable-diffusion-xl-base-1.0` (SDXL) via the `env.AI.run()` binding. The model returns a `ReadableStream` of raw PNG bytes, so you can pipe it directly into the `Response` constructor with `Content-Type: image/png` for zero-copy streaming. Storing the image in R2 requires converting the stream to an `ArrayBuffer` first. A KV token bucket (one key per IP, TTL = window size) is the lightest way to cap generation requests without an external service. Be aware that SDXL inference in Workers AI has a ~10 s cold-start on the first request per colo; subsequent requests are faster thanks to model caching.

---

## Section 1 — wrangler.toml

```toml
name = "image-gen-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[ai]
binding = "AI"

[[kv_namespaces]]
binding = "RATE_KV"
id = "<your-kv-namespace-id>"

[[r2_buckets]]
binding = "IMAGE_BUCKET"
bucket_name = "generated-images"

[vars]
RATE_LIMIT_MAX = "5"
RATE_LIMIT_WINDOW_SECONDS = "60"
```

## Section 2 — Worker implementation

```typescript
interface Env {
  AI: Ai;
  RATE_KV: KVNamespace;
  IMAGE_BUCKET: R2Bucket;
  RATE_LIMIT_MAX: string;
  RATE_LIMIT_WINDOW_SECONDS: string;
}

interface GenerateRequest {
  prompt: string;
  negative_prompt?: string;
  num_steps?: number;
  store?: boolean;
}

async function checkRateLimit(
  kv: KVNamespace,
  ip: string,
  maxRequests: number,
  windowSeconds: number
): Promise<{ allowed: boolean; remaining: number }> {
  const key = `rl:${ip}`;
  const raw = await kv.get(key);
  const count = raw ? parseInt(raw, 10) : 0;

  if (count >= maxRequests) {
    return { allowed: false, remaining: 0 };
  }

  // Increment; set TTL only on first write so the window is fixed.
  const newCount = count + 1;
  const ttl = raw ? undefined : windowSeconds;
  await kv.put(key, String(newCount), ttl ? { expirationTtl: ttl } : undefined);

  return { allowed: true, remaining: maxRequests - newCount };
}

async function streamToArrayBuffer(stream: ReadableStream<Uint8Array>): Promise<ArrayBuffer> {
  const chunks: Uint8Array[] = [];
  const reader = stream.getReader();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (value) chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const total = chunks.reduce((acc, c) => acc + c.length, 0);
  const buf = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    buf.set(chunk, offset);
    offset += chunk.length;
  }
  return buf.buffer;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const ip = request.headers.get('CF-Connecting-IP') ?? 'unknown';
    const maxRequests = parseInt(env.RATE_LIMIT_MAX, 10);
    const windowSeconds = parseInt(env.RATE_LIMIT_WINDOW_SECONDS, 10);

    const { allowed, remaining } = await checkRateLimit(
      env.RATE_KV,
      ip,
      maxRequests,
      windowSeconds
    );

    if (!allowed) {
      return new Response(
        JSON.stringify({ error: 'Rate limit exceeded. Try again in a moment.' }),
        {
          status: 429,
          headers: {
            'Content-Type': 'application/json',
            'Retry-After': String(windowSeconds),
          },
        }
      );
    }

    let body: GenerateRequest;
    try {
      body = await request.json<GenerateRequest>();
    } catch {
      return new Response(JSON.stringify({ error: 'Invalid JSON body' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const { prompt, negative_prompt = '', num_steps = 20, store = false } = body;

    if (!prompt || prompt.trim().length === 0) {
      return new Response(JSON.stringify({ error: '`prompt` is required' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // Run SDXL — returns ReadableStream<Uint8Array>
    const imageStream = await env.AI.run('@cf/stabilityai/stable-diffusion-xl-base-1.0', {
      prompt: prompt.trim(),
      negative_prompt,
      num_steps: Math.min(Math.max(num_steps, 1), 50),
    });

    const headers: Record<string, string> = {
      'Content-Type': 'image/png',
      'X-RateLimit-Remaining': String(remaining),
      'Cache-Control': 'no-store',
    };

    if (!store) {
      return new Response(imageStream as ReadableStream, { headers });
    }

    // Persist to R2 then return the ArrayBuffer
    const buffer = await streamToArrayBuffer(imageStream as ReadableStream<Uint8Array>);
    const key = `${crypto.randomUUID()}.png`;
    await env.IMAGE_BUCKET.put(key, buffer, {
      httpMetadata: { contentType: 'image/png' },
      customMetadata: { prompt, negative_prompt, num_steps: String(num_steps) },
    });

    headers['X-R2-Key'] = key;
    return new Response(buffer, { headers });
  },
};
```

## Section 3 — Advanced usage / Signed R2 URLs

```typescript
// Return a pre-signed R2 URL instead of streaming bytes.
// Requires a public R2 bucket or a Workers presign helper.
async function presignR2(
  bucket: R2Bucket,
  key: string,
  expiresInSeconds: number
): Promise<string> {
  // R2 does not yet expose a native presign API in the binding;
  // use the REST API with your Account ID + R2 token.
  const accountId = (globalThis as unknown as { CF_ACCOUNT_ID?: string }).CF_ACCOUNT_ID ?? '';
  const url = `https://api.cloudflare.com/client/v4/accounts/${accountId}/r2/buckets/generated-images/objects/${key}/presigned-url`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${(globalThis as unknown as { R2_TOKEN?: string }).R2_TOKEN ?? ''}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ expiresIn: expiresInSeconds, method: 'GET' }),
  });
  if (!response.ok) throw new Error('Failed to presign R2 URL');
  const data = (await response.json()) as { result: { url: string } };
  return data.result.url;
}

// Usage inside the handler (replace the R2 put block):
// const signedUrl = await presignR2(env.IMAGE_BUCKET, key, 3600);
// return Response.json({ url: signedUrl, r2Key: key }, { headers });
```

---

## Anti-patterns

- **Returning `await env.AI.run(...)` as JSON** — The result is a binary stream, not JSON. Wrapping it in `Response.json()` will corrupt the bytes. Always use `Content-Type: image/png`.
- **Setting `num_steps` above 50** — The model caps steps internally but wastes quota tokens counting against your AI Gateway usage. Clamp client input server-side.
- **Storing directly to R2 from a stream without buffering** — `R2Bucket.put()` does not accept a `ReadableStream` with an unknown `Content-Length`; buffer to `ArrayBuffer` first.
- **Using a sliding-window rate limiter with KV** — KV TTL resets are atomic but slow (~1 ms RTT); a strict sliding window requires two KV reads. Use a fixed window (one key, fixed TTL) for simplicity.

---

## Gotchas

- SDXL streaming response is a `ReadableStream<Uint8Array>`, not a `Blob`; you must pipe or buffer before inspection.
- The `num_steps` parameter defaults to `20` in the binding; values below `10` often produce noise-heavy output.
- Workers AI deducts from your monthly neuron budget regardless of whether the downstream client closes the connection early.
- KV `expirationTtl` is only honoured if the key did not previously exist in that write call; use a conditional write pattern if you need guaranteed window resets.
- R2 `put` with large buffers (>10 MB) should use multipart upload via the S3-compatible API to avoid Worker CPU-time limits.

---

## Verification

```bash
# Deploy
npx wrangler deploy

# Generate an image (streaming)
curl -X POST https://image-gen-worker.<your-subdomain>.workers.dev \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"a serene mountain lake at sunset, photorealistic","num_steps":20}' \
  --output generated.png

file generated.png  # should report: PNG image data

# Generate and store in R2
curl -X POST https://image-gen-worker.<your-subdomain>.workers.dev \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"abstract fractal art","store":true}' \
  -D - --output stored.png
# Check X-R2-Key header in response for the object key.

# Trigger rate limit (6th request within 60 s should return 429)
for i in $(seq 1 6); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST https://image-gen-worker.<your-subdomain>.workers.dev \
    -H 'Content-Type: application/json' \
    -d '{"prompt":"test"}'
done
```

---

## Related

- `workers-ai-embeddings-vectorize-semantic-search.md`
- `workers-ai-text-classification-moderation.md`
- `workers-ai-translation-multilingual.md`

---

## Sources

- Cloudflare Workers AI Models — https://developers.cloudflare.com/workers-ai/models/
- Stable Diffusion XL on Workers AI — https://developers.cloudflare.com/workers-ai/models/stable-diffusion-xl-base-1.0/
- R2 Workers Binding API — https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- KV Namespace API — https://developers.cloudflare.com/kv/api/
