# Workers AI Image-to-Text Caption Generation

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to generate natural-language captions for user-uploaded images at the edge — for alt-text automation, content indexing, or accessibility compliance — without shipping images to a remote inference API and absorbing egress costs.

## Context

Workers AI exposes `@cf/unum/uform-gen2-qwen-500m` (and `@cf/llava-hf/llava-1.5-7b-hf`) as image-to-text models. The models accept a base64-encoded image plus an optional prompt, and return a text caption. Images arrive from R2, a multipart form, or a URL fetch. Maximum input size is 10 MB per request; larger images must be resized before inference.

---

## 1. Reading an Image from R2 and Captioning It

```typescript
import { Ai } from "@cloudflare/ai";

export interface Env {
  AI: Ai;
  IMAGES: R2Bucket;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const key = url.searchParams.get("key");
    if (!key) return new Response("Missing key", { status: 400 });

    const object = await env.IMAGES.get(key);
    if (!object) return new Response("Not found", { status: 404 });

    const buffer = await object.arrayBuffer();
    const base64 = btoa(String.fromCharCode(...new Uint8Array(buffer)));

    const result = await env.AI.run("@cf/unum/uform-gen2-qwen-500m", {
      image: [...new Uint8Array(buffer)],
      prompt: "Describe this image in one clear sentence suitable for alt text.",
      max_tokens: 256,
    });

    return Response.json({ caption: result.description, key });
  },
};
```

## 2. Accepting a Multipart Upload and Captioning Inline

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("POST only", { status: 405 });
    }

    const formData = await request.formData();
    const file = formData.get("image") as File | null;
    if (!file) return new Response("No image field", { status: 400 });

    if (file.size > 10 * 1024 * 1024) {
      return new Response("Image exceeds 10 MB limit", { status: 413 });
    }

    const bytes = new Uint8Array(await file.arrayBuffer());
    const prompt = (formData.get("prompt") as string) ??
      "Write a concise, factual caption for this image.";

    const result = await env.AI.run("@cf/unum/uform-gen2-qwen-500m", {
      image: [...bytes],
      prompt,
      max_tokens: 512,
    });

    return Response.json({
      caption: result.description,
      filename: file.name,
      size: file.size,
    });
  },
};
```

## 3. Batch Captioning via Queue Consumer

```typescript
import { Ai } from "@cloudflare/ai";

export interface Env {
  AI: Ai;
  IMAGES: R2Bucket;
  CAPTIONS: KVNamespace;
  CAPTION_QUEUE: Queue;
}

interface CaptionJob {
  r2Key: string;
  prompt?: string;
}

export default {
  async queue(batch: MessageBatch<CaptionJob>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { r2Key, prompt } = msg.body;

      try {
        const obj = await env.IMAGES.get(r2Key);
        if (!obj) { msg.ack(); continue; }

        const bytes = new Uint8Array(await obj.arrayBuffer());
        const result = await env.AI.run("@cf/unum/uform-gen2-qwen-500m", {
          image: [...bytes],
          prompt: prompt ?? "Describe this image for search indexing.",
          max_tokens: 256,
        });

        await env.CAPTIONS.put(r2Key, result.description, {
          metadata: { captionedAt: new Date().toISOString() },
        });

        msg.ack();
      } catch (err) {
        // retry up to Queue's configured max_retries
        msg.retry();
      }
    }
  },
};
```

## 4. Caption with Confidence Gate — Fall Back to a Longer Prompt

```typescript
async function captionWithFallback(
  ai: Ai,
  bytes: Uint8Array,
): Promise<string> {
  const quick = await ai.run("@cf/unum/uform-gen2-qwen-500m", {
    image: [...bytes],
    prompt: "Caption this image in one sentence.",
    max_tokens: 128,
  });

  const caption = (quick.description ?? "").trim();

  // If the model returned something too short, try a richer prompt
  if (caption.split(" ").length < 5) {
    const detailed = await ai.run("@cf/unum/uform-gen2-qwen-500m", {
      image: [...bytes],
      prompt:
        "Provide a detailed description covering objects, scene, colors, and context.",
      max_tokens: 512,
    });
    return detailed.description ?? caption;
  }

  return caption;
}
```

## 5. Storing Captions Back to R2 Custom Metadata

```typescript
async function captionAndTag(
  env: Env,
  r2Key: string,
): Promise<void> {
  const obj = await env.IMAGES.get(r2Key);
  if (!obj) return;

  const bytes = new Uint8Array(await obj.arrayBuffer());
  const result = await env.AI.run("@cf/unum/uform-gen2-qwen-500m", {
    image: [...bytes],
    prompt: "One sentence alt text for web accessibility.",
    max_tokens: 200,
  });

  // Overwrite the object preserving content, adding caption metadata
  const body = await env.IMAGES.get(r2Key);
  if (!body) return;

  await env.IMAGES.put(r2Key, body.body, {
    httpMetadata: obj.httpMetadata,
    customMetadata: {
      ...(obj.customMetadata ?? {}),
      altText: result.description.slice(0, 1024),
      captionModel: "@cf/unum/uform-gen2-qwen-500m",
      captionedAt: new Date().toISOString(),
    },
  });
}
```

---

## Anti-patterns

- **Sending PNG/JPEG URLs as the `image` field** — the model expects raw bytes or a uint8 array, not a URL string. Fetch the image and convert it first.
- **Skipping the prompt** — omitting the `prompt` field often yields very generic output. Even a minimal prompt like "Describe this image." significantly improves caption quality.
- **Re-uploading the full object to update metadata** — use `put` with the original body stream; avoid downloading then re-uploading large images just to attach metadata.
- **Ignoring the 10 MB hard limit** — requests exceeding the limit return a 400 from the Workers AI binding; validate size client-side or in the Worker before inference.

## Gotchas

- `result.description` is the field containing the caption text for `uform-gen2-qwen-500m`; other models (e.g., LLaVA) return `result.response` — check the model card.
- The image array must be `number[]` (spread from `Uint8Array`), not a base64 string, when using the TypeScript binding.
- Workers AI image-to-text models do not stream; the full caption is returned synchronously once generation completes.
- EXIF rotation is not applied automatically; pre-rotate images server-side if orientation matters for captioning accuracy.

## Verification

```bash
# Upload a test image and request a caption
curl -X POST https://my-worker.workers.dev/caption \
  -F "image=@./test.jpg" \
  -F "prompt=Describe this image in one sentence."

# Expected response shape
# {"caption": "A golden retriever sits on a grassy hillside at sunset.", ...}

# Confirm KV or R2 metadata was written after batch queue job
wrangler kv key get --binding=CAPTIONS "images/photo.jpg"
```

## Related

- `workers-ai-image-classification-r2-pipeline.md`
- `workers-ai-multimodal-content-moderation-pipeline.md`
- `workers-ai-ocr-document-pipeline.md`
- `workers-ai-batch-embedding-queues-pipeline.md`

## Sources

- Cloudflare Workers AI model catalog — image-to-text models: https://developers.cloudflare.com/workers-ai/models/
- R2 object metadata API: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- Cloudflare Queues consumer API: https://developers.cloudflare.com/queues/reference/javascript-apis/
