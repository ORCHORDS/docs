# Workers AI Vision: Image-to-Text Models Pipeline

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You want to run image captioning, OCR, object detection, or visual question answering
directly at the edge inside a Cloudflare Worker — without provisioning GPU servers or
routing to a third-party vision API. Workers AI exposes vision models (LLaVA, LLaMA vision
variants, and others) via the standard `AI.run()` binding with multimodal input support.

## Context

Workers AI is Cloudflare's serverless inference platform, co-located with the global
edge network. Vision models accept images as base64-encoded strings or raw byte arrays
alongside a text prompt. Responses are streamed or returned as a single JSON payload.

Supported vision model categories (as of mid-2026):
- **Image-to-text / captioning**: `@cf/llava-hf/llava-1.5-7b-hf` (describe images)
- **Optical character recognition**: `@cf/microsoft/resnet-50` (classification), plus
  dedicated OCR models in preview
- **Visual QA**: LLaVA-style models accept a `messages` array with image + text turns

Pricing: Workers AI uses a "neurons" unit. Vision inference is more expensive per call
than text-only inference. Check the dashboard for current neuron rates.

---

## 1. Basic Image Captioning

```typescript
interface Env {
  AI: Ai;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Accept an image URL via query param
    const url = new URL(request.url);
    const imageUrl = url.searchParams.get('imageUrl');
    if (!imageUrl) return new Response('Missing imageUrl', { status: 400 });

    // Fetch the image and convert to a Uint8Array
    const imageRes = await fetch(imageUrl);
    if (!imageRes.ok) return new Response('Could not fetch image', { status: 502 });
    const imageBytes = new Uint8Array(await imageRes.arrayBuffer());

    const result = await env.AI.run('@cf/llava-hf/llava-1.5-7b-hf', {
      image: [...imageBytes],           // spread into plain number array
      prompt: 'Describe this image in one concise sentence.',
      max_tokens: 256,
    });

    return Response.json({ caption: result.description });
  },
};
```

`wrangler.toml` binding:

```toml
[ai]
binding = "AI"
```

---

## 2. Visual Question Answering with Chat-Style API

LLaVA and similar models support a multi-turn `messages` format. Use this for VQA,
structured data extraction from receipts, or document parsing.

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('POST only', { status: 405 });

    const { imageBase64, question } = await request.json<{
      imageBase64: string;
      question: string;
    }>();

    // Decode base64 to byte array
    const binaryStr = atob(imageBase64);
    const imageBytes = new Uint8Array(binaryStr.length);
    for (let i = 0; i < binaryStr.length; i++) {
      imageBytes[i] = binaryStr.charCodeAt(i);
    }

    const response = await env.AI.run('@cf/llava-hf/llava-1.5-7b-hf', {
      image: [...imageBytes],
      prompt: question,
      max_tokens: 512,
    });

    return Response.json({ answer: response.description });
  },
};
```

---

## 3. OCR Pipeline: Extract Text from a Receipt

Chain a vision call for text extraction with a structured parsing step.

```typescript
async function extractTextFromImage(env: Env, imageBytes: Uint8Array): Promise<string> {
  const result = await env.AI.run('@cf/llava-hf/llava-1.5-7b-hf', {
    image: [...imageBytes],
    prompt:
      'Extract all text visible in this image verbatim. ' +
      'Return only the extracted text, no commentary.',
    max_tokens: 1024,
  });
  return result.description ?? '';
}

async function parseReceiptText(env: Env, rawText: string): Promise<Record<string, string>> {
  const result = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
    messages: [
      {
        role: 'system',
        content: 'You are a receipt parser. Output valid JSON only.',
      },
      {
        role: 'user',
        content: `Parse this receipt text into JSON with keys: vendor, date, total, items.\n\n${rawText}`,
      },
    ],
    max_tokens: 512,
  });
  try {
    return JSON.parse(result.response ?? '{}');
  } catch {
    return { raw: rawText };
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const formData = await request.formData();
    const file = formData.get('receipt') as File | null;
    if (!file) return new Response('Missing receipt file', { status: 400 });

    const imageBytes = new Uint8Array(await file.arrayBuffer());
    const rawText = await extractTextFromImage(env, imageBytes);
    const parsed = await parseReceiptText(env, rawText);

    return Response.json(parsed);
  },
};
```

---

## 4. Streaming Vision Responses

For long captions or documents, stream the response back to the client.

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { imageUrl } = await request.json<{ imageUrl: string }>();
    const imgRes = await fetch(imageUrl);
    const imageBytes = new Uint8Array(await imgRes.arrayBuffer());

    const stream = await env.AI.run('@cf/llava-hf/llava-1.5-7b-hf', {
      image: [...imageBytes],
      prompt: 'Describe this image in detail, covering all visible elements.',
      max_tokens: 1024,
      stream: true,
    });

    // stream is a ReadableStream of Server-Sent Events
    return new Response(stream as ReadableStream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
      },
    });
  },
};
```

---

## 5. Caching Vision Results in KV

Vision inference is latency-heavy (~500 ms–2 s). Cache results by image URL hash to avoid
re-running the model for the same input.

```typescript
interface Env {
  AI: Ai;
  VISION_CACHE: KVNamespace;
}

async function hashUrl(url: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(url));
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const imageUrl = new URL(request.url).searchParams.get('url') ?? '';
    const cacheKey = await hashUrl(imageUrl);

    const cached = await env.VISION_CACHE.get(cacheKey);
    if (cached) return Response.json({ caption: cached, source: 'cache' });

    const imgRes = await fetch(imageUrl);
    const imageBytes = new Uint8Array(await imgRes.arrayBuffer());

    const result = await env.AI.run('@cf/llava-hf/llava-1.5-7b-hf', {
      image: [...imageBytes],
      prompt: 'Describe this image.',
      max_tokens: 256,
    });

    const caption = result.description ?? '';
    await env.VISION_CACHE.put(cacheKey, caption, { expirationTtl: 3600 });

    return Response.json({ caption, source: 'model' });
  },
};
```

---

## Anti-Patterns

- **Passing image URLs directly as strings.** Workers AI vision models require raw bytes
  (`number[]` or `Uint8Array`), not URLs. You must fetch and convert first.
- **Sending very large images without resizing.** The model input is capped; oversized
  images trigger a 413 or silent truncation. Resize to ≤1024 px on the longest side
  before encoding.
- **Ignoring neuron cost in hot paths.** Vision models consume significantly more neurons
  than text-only calls. Add caching (KV or Cache API) for repeat inputs.
- **Blocking on sequential vision + LLM calls.** Use `Promise.all` for independent
  inference tasks within the same request where possible.

---

## Gotchas

- The `image` field expects a plain `number[]` (not `Uint8Array` directly) in the current
  SDK. Spread with `[...imageBytes]` to convert.
- Model availability varies by region. Workers AI routes to the nearest PoP with GPU
  capacity; cold-start latency can be 1–3 s on first inference per PoP.
- The `description` field on the result object holds the model's text output. Some models
  return `response` instead — check the model card in the docs.
- Streaming returns SSE (text/event-stream) frames, not a single JSON blob. Parse each
  `data:` line as JSON and concatenate the `response` field.
- The `@cf/llava-hf/llava-1.5-7b-hf` model does not support multiple images in a single
  call. For multi-image workflows, run sequential or parallel `AI.run()` calls.

---

## Verification

```bash
# Test locally with Wrangler (requires Workers AI remote binding)
wrangler dev --remote

# Curl with a public image URL
curl "http://localhost:8787/?imageUrl=https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/PNG_transparency_demonstration_1.png/280px-PNG_transparency_demonstration_1.png"
# Expected: {"caption":"A checkered pattern demonstrating PNG transparency..."}
```

In production, check Workers AI metrics in the Cloudflare dashboard under
**Workers & Pages → AI → Usage** for neuron consumption and error rates.

---

## Related

- `workers-ai-2026.md`
- `workers-ai-edge-inference.md`
- `workers-ai-inference-gateway.md`
- `kv-best-practices.md`
- `ai-gateway-best-practices.md`

---

## Sources

- https://developers.cloudflare.com/workers-ai/models/
- https://developers.cloudflare.com/workers-ai/models/llava-1.5-7b-hf/
- https://developers.cloudflare.com/workers-ai/configuration/bindings/
