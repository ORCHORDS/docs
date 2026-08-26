# Multi-Modal Content Analysis: Combined Image + Text Classification in Workers AI
- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A single-modality classifier is insufficient: an image of a product is labelled
correctly by a vision model, but the user's caption "great item for parties" changes
the category from "décor" to "entertainment". Or a piece of user-generated text
looks benign until paired with its attached image, which makes the intent clear.

You need to run image classification and text analysis in parallel, then fuse the
signals into a single confident label — all inside a Cloudflare Worker.

## Context

Workers AI exposes separate image and text endpoints. Multi-modal fusion means:

1. Run image analysis via `@cf/llava-hf/llava-1.5-7b-hf` (vision-language model)
   or a purpose-built classifier (`@cf/microsoft/resnet-50`).
2. Run text analysis via a text classification or embedding model.
3. Combine scores with a weighted or learned ensemble rule.

The VLM approach (LLaVA) handles both modalities in one call — pass the image as
a base64 `image` array alongside the `prompt`. The dedicated classifier approach
(ResNet-50 + text model) is faster and cheaper but requires a fusion step.

Target latencies (p95, Workers AI):
- LLaVA single-call: 2–4 s (not suitable for real-time mobile UI blocking calls)
- ResNet-50 + text classifier parallel: 300–600 ms (mobile-viable)

---

## Section 1 — Approach A: Vision-Language Model (LLaVA) Single Call

Best for nuanced, open-ended labelling where the combined semantics matter most.

```typescript
// src/vlm-classifier.ts
export interface Env {
  AI: Ai;
}

export interface ClassificationResult {
  label: string;
  confidence: number;
  reasoning: string;
}

const CATEGORY_LABELS = [
  "entertainment",
  "home-decor",
  "outdoor-sports",
  "fashion",
  "food-beverage",
  "electronics",
  "other",
] as const;

type Category = (typeof CATEGORY_LABELS)[number];

export async function classifyWithVLM(
  env: Env,
  imageBytes: Uint8Array,
  userCaption: string,
  isMobile: boolean,
): Promise<ClassificationResult> {
  const prompt = [
    `You are a product categorisation assistant.`,
    `The user uploaded an image and wrote the caption: "${userCaption}".`,
    `Examine the image and the caption together.`,
    `Reply with exactly this JSON: {"label": "<one of: ${CATEGORY_LABELS.join(", ")}>", "confidence": <0.0-1.0>, "reasoning": "<one sentence>"}`,
    isMobile ? "Keep reasoning under 15 words." : "",
  ]
    .filter(Boolean)
    .join(" ");

  const response = await env.AI.run("@cf/llava-hf/llava-1.5-7b-hf", {
    image: Array.from(imageBytes),
    prompt,
    max_tokens: isMobile ? 80 : 150,
  });

  const raw = (response as any).description ?? "";

  try {
    const parsed = JSON.parse(extractJSON(raw));
    return {
      label:      parsed.label in Object.fromEntries(CATEGORY_LABELS.map(l => [l, 1])) ? parsed.label : "other",
      confidence: Math.min(1, Math.max(0, Number(parsed.confidence))),
      reasoning:  String(parsed.reasoning ?? ""),
    };
  } catch {
    return { label: "other", confidence: 0.3, reasoning: "Parse error" };
  }
}

function extractJSON(text: string): string {
  const match = text.match(/\{[\s\S]*\}/);
  return match ? match[0] : "{}";
}
```

---

## Section 2 — Approach B: Parallel Specialist Models with Score Fusion

Better for throughput and cost. Run ResNet-50 for the image and a text classifier
in parallel, then fuse.

```typescript
// src/parallel-classifier.ts
export interface Env {
  AI: Ai;
}

// Workers AI ResNet-50 returns labels from ImageNet-1K.
// We map broad ImageNet super-categories to our domain labels.
const IMAGENET_TO_DOMAIN: Record<string, string> = {
  "jersey, T-shirt, tee shirt":     "fashion",
  "television, television system":  "electronics",
  "plate":                          "food-beverage",
  "volleyball":                     "outdoor-sports",
  "vase":                           "home-decor",
  "beer bottle":                    "food-beverage",
};

function mapImageNetToDomain(label: string): string {
  for (const [key, domain] of Object.entries(IMAGENET_TO_DOMAIN)) {
    if (label.toLowerCase().includes(key.toLowerCase().split(",")[0])) return domain;
  }
  return "other";
}

// Text zero-shot classification using Workers AI
async function classifyText(
  env: Env,
  text: string,
  labels: string[],
): Promise<{ label: string; score: number }> {
  const response = await env.AI.run("@cf/huggingface/distilbart-mnli-12-1", {
    text,
    candidate_labels: labels,
  });
  const res = response as any;
  const topIdx = (res.scores as number[]).indexOf(Math.max(...(res.scores as number[])));
  return { label: res.labels[topIdx], score: res.scores[topIdx] };
}

// Image classification with ResNet-50
async function classifyImage(
  env: Env,
  imageBytes: Uint8Array,
): Promise<{ label: string; score: number }> {
  const response = await env.AI.run("@cf/microsoft/resnet-50", {
    image: Array.from(imageBytes),
  });
  const top = (response as any)[0];  // sorted descending by score
  return {
    label: mapImageNetToDomain(top.label),
    score: top.score,
  };
}

// Weighted fusion: image signal slightly dominates for visual categories
function fuseScores(
  imageResult: { label: string; score: number },
  textResult:  { label: string; score: number },
  domainLabels: string[],
): { label: string; confidence: number } {
  const IMAGE_WEIGHT = 0.55;
  const TEXT_WEIGHT  = 0.45;

  // Build score map across all labels
  const scores: Record<string, number> = Object.fromEntries(domainLabels.map(l => [l, 0]));

  scores[imageResult.label] = (scores[imageResult.label] ?? 0) + imageResult.score * IMAGE_WEIGHT;
  scores[textResult.label]  = (scores[textResult.label]  ?? 0) + textResult.score  * TEXT_WEIGHT;

  const best = Object.entries(scores).sort(([, a], [, b]) => b - a)[0];
  return { label: best[0], confidence: Math.min(1, best[1]) };
}

const DOMAIN_LABELS = [
  "entertainment", "home-decor", "outdoor-sports",
  "fashion", "food-beverage", "electronics", "other",
];

export async function classifyParallel(
  env: Env,
  imageBytes: Uint8Array,
  caption: string,
  isMobile: boolean,
): Promise<{ label: string; confidence: number; imageLabel: string; textLabel: string }> {
  // Fire both classifiers concurrently
  const [imageResult, textResult] = await Promise.all([
    classifyImage(env, imageBytes),
    // On mobile, shorten caption to 100 chars to limit model input
    classifyText(env, isMobile ? caption.slice(0, 100) : caption, DOMAIN_LABELS),
  ]);

  const fused = fuseScores(imageResult, textResult, DOMAIN_LABELS);
  return { ...fused, imageLabel: imageResult.label, textLabel: textResult.label };
}
```

---

## Section 3 — Request Handler and Mobile Adaptation

```typescript
// src/index.ts
import { classifyWithVLM }    from "./vlm-classifier";
import { classifyParallel }   from "./parallel-classifier";

export interface Env {
  AI: Ai;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== "POST") return new Response("POST only", { status: 405 });

    const formData  = await req.formData();
    const imageFile = formData.get("image") as File | null;
    const caption   = (formData.get("caption") as string | null) ?? "";
    const strategy  = (formData.get("strategy") as string | null) ?? "parallel";

    if (!imageFile) return new Response("image required", { status: 400 });

    // Detect mobile via User-Agent to choose response size
    const ua       = req.headers.get("User-Agent") ?? "";
    const isMobile = /Mobile|Android|iPhone|iPad/.test(ua);

    // Enforce 5 MB image limit
    if (imageFile.size > 5 * 1024 * 1024) {
      return new Response("Image too large (max 5 MB)", { status: 413 });
    }

    const imageBytes = new Uint8Array(await imageFile.arrayBuffer());

    let result: Record<string, unknown>;

    if (strategy === "vlm") {
      result = await classifyWithVLM(env, imageBytes, caption, isMobile);
    } else {
      result = await classifyParallel(env, imageBytes, caption, isMobile);
    }

    // Mobile: omit intermediate labels to reduce payload size
    if (isMobile) {
      const { label, confidence } = result as any;
      return Response.json({ label, confidence });
    }

    return Response.json(result);
  },
};
```

---

## Section 4 — Confidence Thresholds and Fallback

Low-confidence results should trigger a human review queue rather than an
auto-label.

```typescript
export interface ReviewQueueItem {
  id: string;
  imageUrl: string;
  caption: string;
  autoLabel: string;
  confidence: number;
  createdAt: string;
}

export async function maybeQueueForReview(
  db: D1Database,
  item: ReviewQueueItem,
  confidenceThreshold = 0.65,
): Promise<boolean> {
  if (item.confidence >= confidenceThreshold) return false;  // auto-accept

  await db
    .prepare(
      `INSERT INTO review_queue (id, image_url, caption, auto_label, confidence, created_at)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6)`,
    )
    .bind(item.id, item.imageUrl, item.caption, item.autoLabel, item.confidence, item.createdAt)
    .run();

  return true;  // queued for review
}
```

Calibrate the threshold per category:

```typescript
const CATEGORY_THRESHOLDS: Record<string, number> = {
  "food-beverage":  0.70,  // high precision needed (allergen labelling)
  "electronics":    0.60,
  "other":          0.50,  // catch-all; lower bar OK
};

function thresholdForLabel(label: string): number {
  return CATEGORY_THRESHOLDS[label] ?? 0.65;
}
```

---

## Anti-patterns

- **Passing full-resolution images to Workers AI** — ResNet-50 internally resizes to
  224×224 and LLaVA to 336×336. Pre-resize on the client (especially mobile) to
  the target before upload to reduce upload bandwidth and Worker CPU time.
- **Sequential rather than parallel classifier calls** — awaiting image then text
  serially doubles latency for no benefit; always use `Promise.all`.
- **Trusting VLM JSON output without validation** — LLaVA sometimes wraps JSON in
  markdown fences or adds trailing text; always strip with a regex before parsing.
- **Hard-coding ImageNet→domain mapping** — the mapping is fragile for novel product
  categories; the parallel approach should be supplemented with a text fallback for
  unmapped ImageNet labels.
- **Returning verbose fusion debug data to mobile clients** — the `imageLabel`,
  `textLabel`, and `reasoning` fields are useful for desktop dashboards but add
  unnecessary payload bytes on mobile; gate behind a `detail` query param or UA
  check.

---

## Gotchas

- Workers AI image inputs must be passed as `number[]` (not `Uint8Array`); use
  `Array.from(imageBytes)` before passing to `run()`.
- LLaVA 1.5 7B has a tendency to refuse classification for borderline content and
  return a refusal message instead of JSON. Add a fallback that detects the word
  "sorry" or "cannot" in the response and falls back to the parallel approach.
- `@cf/huggingface/distilbart-mnli-12-1` requires `candidate_labels` as a plain
  array of strings — passing a typed `readonly` array causes a runtime error in
  some TypeScript environments; cast to `string[]`.
- The ResNet-50 model returns scores as `number` in `[0, 1]` already normalised
  across the top-5 labels returned; fusion with MNLI scores (also `[0,1]` per
  label) is numerically compatible.
- Free Workers AI tier limits: 10 000 neurons/day. Each LLaVA call burns ~15
  neurons; each ResNet-50 call ~2; plan accordingly for high-volume pipelines.

---

## Verification

```typescript
// test/classify.test.ts
import { expect, test, vi } from "vitest";
import { classifyParallel } from "../src/parallel-classifier";
import { readFileSync } from "fs";

test("fuses high-confidence image + text correctly", async () => {
  const mockAI = {
    run: vi.fn()
      .mockImplementation(async (model: string, input: any) => {
        if (model.includes("resnet")) {
          return [{ label: "jersey, T-shirt, tee shirt", score: 0.92 }];
        }
        // MNLI mock
        return {
          labels: ["fashion", "electronics", "other"],
          scores: [0.88, 0.07, 0.05],
        };
      }),
  };

  const bytes = new Uint8Array(readFileSync("test/fixtures/shirt.jpg"));
  const result = await classifyParallel(
    { AI: mockAI } as any,
    bytes,
    "Nice casual tee for weekends",
    false,
  );

  expect(result.label).toBe("fashion");
  expect(result.confidence).toBeGreaterThan(0.7);
});
```

---

## Related

- `image-analysis-patterns.md` — single-modality image analysis
- `multimodal-vision-patterns.md` — vision model patterns
- `workers-ai-text-classification-moderation.md` — text classification
- `ai-content-moderation-pipeline.md` — end-to-end moderation pipeline
- `llm-structured-output-json-mode.md` — parsing structured VLM output

---

## Sources

- Workers AI image classification: https://developers.cloudflare.com/workers-ai/models/image-classification/
- LLaVA on Workers AI: https://developers.cloudflare.com/workers-ai/models/llava-1.5-7b-hf/
- DistilBart MNLI: https://developers.cloudflare.com/workers-ai/models/distilbart-mnli-12-1/
- ImageNet class list: https://github.com/anishathalye/imagenet-simple-labels
