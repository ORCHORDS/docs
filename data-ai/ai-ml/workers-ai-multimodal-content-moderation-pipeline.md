# Workers AI Multi-modal Content Moderation Pipeline

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A UGC platform accepts posts that combine images and text captions. Running moderation on each modality in isolation misses cases where a benign image is paired with harmful text, or where text sentiment changes meaning when context from the image is added. You need a single decision that fuses both signals.

## Context

The pipeline chains three Workers AI models:

1. **Image classifier** (`@cf/microsoft/resnet-50` or a fine-tuned safety model) — detects NSFW categories in the image.
2. **Image-to-text** (`@cf/unum/uform-gen2-qwen-500m`) — generates a scene description from the image to give the text model visual context.
3. **Text classifier / LLM judge** (`@cf/meta/llama-3.1-8b-instruct`) — evaluates the combined (description + user caption) for policy violations.

The final verdict is the union of both signals: if either channel flags content, the post is held for review. Results are stored in D1 for audit.

---

## 1. Image Safety Classification

```typescript
import { Ai } from "@cloudflare/ai";

export interface Env {
  AI: Ai;
  DB: D1Database;
  IMAGES: R2Bucket;
}

interface ImageModerationResult {
  safe: boolean;
  topLabel: string;
  topScore: number;
  allScores: Array<{ label: string; score: number }>;
}

async function moderateImage(
  ai: Ai,
  imageBytes: Uint8Array,
): Promise<ImageModerationResult> {
  const result = await ai.run("@cf/microsoft/resnet-50", {
    image: [...imageBytes],
  });

  // Sort by score descending
  const sorted = result.sort((a: any, b: any) => b.score - a.score);
  const top = sorted[0];

  // Flag known unsafe labels
  const unsafeLabels = new Set(["NSFW", "violence", "gore", "hate_symbol"]);
  const safe = !unsafeLabels.has(top.label) && top.score < 0.85;

  return {
    safe,
    topLabel: top.label,
    topScore: top.score,
    allScores: sorted.slice(0, 5),
  };
}
```

## 2. Generating Visual Context via Image Captioning

```typescript
async function generateVisualContext(
  ai: Ai,
  imageBytes: Uint8Array,
): Promise<string> {
  const result = await ai.run("@cf/unum/uform-gen2-qwen-500m", {
    image: [...imageBytes],
    prompt:
      "Describe this image objectively: what objects, people, actions, and settings are present?",
    max_tokens: 200,
  });

  return result.description ?? "";
}
```

## 3. LLM-based Text + Visual Context Policy Check

```typescript
interface TextModerationResult {
  safe: boolean;
  violationCategory: string | null;
  confidence: "high" | "medium" | "low";
  reasoning: string;
}

async function moderateTextWithContext(
  ai: Ai,
  userCaption: string,
  imageDescription: string,
): Promise<TextModerationResult> {
  const systemPrompt = `You are a content moderation AI. Evaluate whether the combined image description and user caption violate content policies.
Policies: no hate speech, no graphic violence, no explicit sexual content, no harassment, no self-harm promotion.
Respond ONLY with valid JSON: {"safe": boolean, "violationCategory": string|null, "confidence": "high"|"medium"|"low", "reasoning": string}`;

  const userMessage = `Image description: ${imageDescription}
User caption: ${userCaption}`;

  const result = await ai.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: userMessage },
    ],
    max_tokens: 256,
  });

  try {
    const jsonStr = result.response.match(/\{[\s\S]*\}/)?.[0] ?? "{}";
    return JSON.parse(jsonStr) as TextModerationResult;
  } catch {
    return {
      safe: false, // fail closed on parse error
      violationCategory: "parse_error",
      confidence: "low",
      reasoning: "Failed to parse LLM response — treating as unsafe.",
    };
  }
}
```

## 4. Pipeline Orchestration with Parallel Execution

```typescript
interface ModerationDecision {
  postId: string;
  verdict: "approved" | "held" | "rejected";
  imageSafe: boolean;
  textSafe: boolean;
  violationCategory: string | null;
  processingMs: number;
}

async function runModerationPipeline(
  env: Env,
  postId: string,
  r2Key: string,
  userCaption: string,
): Promise<ModerationDecision> {
  const start = Date.now();

  const obj = await env.IMAGES.get(r2Key);
  if (!obj) throw new Error(`Image not found: ${r2Key}`);
  const imageBytes = new Uint8Array(await obj.arrayBuffer());

  // Run image classification and captioning in parallel
  const [imageModeration, imageDescription] = await Promise.all([
    moderateImage(env.AI, imageBytes),
    generateVisualContext(env.AI, imageBytes),
  ]);

  // Text moderation needs the image description first
  const textModeration = await moderateTextWithContext(
    env.AI,
    userCaption,
    imageDescription,
  );

  const imageSafe = imageModeration.safe;
  const textSafe = textModeration.safe;
  const overallSafe = imageSafe && textSafe;

  const verdict: "approved" | "held" | "rejected" = overallSafe
    ? "approved"
    : textModeration.confidence === "high"
    ? "rejected"
    : "held";

  const decision: ModerationDecision = {
    postId,
    verdict,
    imageSafe,
    textSafe,
    violationCategory: textModeration.violationCategory ?? null,
    processingMs: Date.now() - start,
  };

  // Write to D1 for audit trail
  await env.DB.prepare(
    `INSERT INTO moderation_log
       (post_id, verdict, image_safe, text_safe, violation_category, processing_ms, created_at)
     VALUES (?, ?, ?, ?, ?, ?, datetime('now'))`,
  )
    .bind(
      postId,
      verdict,
      imageSafe ? 1 : 0,
      textSafe ? 1 : 0,
      decision.violationCategory,
      decision.processingMs,
    )
    .run();

  return decision;
}
```

## 5. Worker Endpoint and Queue-based Async Processing

```typescript
export interface Env {
  AI: Ai;
  DB: D1Database;
  IMAGES: R2Bucket;
  MODERATION_QUEUE: Queue;
}

interface QueueJob {
  postId: string;
  r2Key: string;
  caption: string;
}

export default {
  // Synchronous path for small images where latency is acceptable
  async fetch(request: Request, env: Env): Promise<Response> {
    const { postId, r2Key, caption } =
      await request.json<QueueJob>();

    const decision = await runModerationPipeline(env, postId, r2Key, caption);
    return Response.json(decision);
  },

  // Async path via Queue for high-volume UGC
  async queue(batch: MessageBatch<QueueJob>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await runModerationPipeline(
          env,
          msg.body.postId,
          msg.body.r2Key,
          msg.body.caption,
        );
        msg.ack();
      } catch (err) {
        console.error("Moderation error", err);
        msg.retry();
      }
    }
  },
};
```

---

## Anti-patterns

- **Running all three models sequentially when image classification and captioning are independent** — always run `moderateImage` and `generateVisualContext` in parallel with `Promise.all`; this cuts pipeline latency by 40–60 %.
- **Failing open on LLM JSON parse errors** — a malformed LLM response should be treated as `safe: false` (fail closed) and logged for review, not silently approved.
- **Using only image classification for moderation** — ResNet-50 is trained on object categories, not safety labels. Use a dedicated safety model or add a second LLM pass for reliable policy enforcement.
- **Storing full image bytes in D1** — D1 is for structured records; always store images in R2 and reference the R2 key in D1 audit logs.

## Gotchas

- `@cf/microsoft/resnet-50` returns ImageNet labels (objects/scenes), not safety categories. For true NSFW detection use `@cf/lykon/dreamshaper-8-lcm` prompting or a purpose-built classifier.
- Workers AI has a concurrency limit per account; bursting dozens of parallel `Promise.all` calls across many queue messages simultaneously can hit rate limits — use `batch.messages` processing with a semaphore if volume is high.
- The image-to-text description may itself contain content from the image (e.g., text visible in the scene). Pass it to the LLM as `imageDescription` with a note that it is auto-generated, not user input, to avoid false positives on extracted text.
- D1 `INSERT` inside a queue consumer runs in a transaction-less context; use `.run()` not `.batch()` unless you need atomicity across multiple statements.

## Verification

```bash
# Test with a safe image + safe caption
curl -X POST https://my-worker.workers.dev/moderate \
  -H "Content-Type: application/json" \
  -d '{"postId":"p1","r2Key":"images/safe.jpg","caption":"Beautiful sunset at the beach"}'
# Expected: {"verdict":"approved","imageSafe":true,"textSafe":true,...}

# Check D1 audit log
wrangler d1 execute my-db \
  --command "SELECT * FROM moderation_log ORDER BY created_at DESC LIMIT 5;"
```

## Related

- `ai-content-moderation-pipeline.md`
- `workers-ai-multimodal-image-text-classification.md`
- `workers-ai-image-to-text-captioning.md`
- `workers-ai-toxicity-scoring-d1-audit-trail.md`
- `workers-ai-content-safety-classifier-pipeline.md`

## Sources

- Cloudflare Workers AI image classification models: https://developers.cloudflare.com/workers-ai/models/
- Workers AI image-to-text: https://developers.cloudflare.com/workers-ai/models/uform-gen2-qwen-500m/
- D1 Workers binding API: https://developers.cloudflare.com/d1/worker-api/
- Cloudflare Queues consumer API: https://developers.cloudflare.com/queues/reference/javascript-apis/
