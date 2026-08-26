# Workers AI Pipeline Chaining Multi-Model

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
A single Workers AI model call is insufficient for your use-case — you need to classify input first, then route it to a specialized model, or generate an image caption before summarising it alongside text. Chaining model calls naively leads to unreadable handler code and poor error attribution.

## Context
Cloudflare Workers AI exposes multiple model families — text generation, embedding, classification, image generation, speech-to-text — all callable from the same `env.AI` binding. Composing them into pipelines is a first-class pattern: Workers' single-thread execution model means sequential calls are straightforward, while `Promise.all()` enables parallel fan-out where models are independent. The key discipline is separating pipeline stage definitions from orchestration logic.

## Pipeline Stage Abstraction

Define each stage as a typed function with a single input and output. This keeps orchestration code readable and stages independently testable.

```typescript
// src/pipeline.ts
interface Env {
  AI: Ai;
}

// Stage 1: classify the intent of the incoming text
async function classifyIntent(
  env: Env,
  text: string
): Promise<"support" | "sales" | "general"> {
  const result = await env.AI.run("@cf/huggingface/distilbert-sst-2-int8", {
    text,
  });

  // Map sentiment/label output to business intent (simplified example)
  // For a real classifier use a zero-shot model or fine-tuned intent classifier
  const label = result.label?.toLowerCase() ?? "general";
  if (label.includes("pos")) return "sales";
  if (label.includes("neg")) return "support";
  return "general";
}

// Stage 2: route to a specialized prompt based on intent
function buildSystemPrompt(intent: "support" | "sales" | "general"): string {
  const prompts = {
    support: "You are a customer support agent. Be empathetic and solution-focused.",
    sales:   "You are a sales assistant. Highlight product benefits and guide toward purchase.",
    general: "You are a helpful assistant. Be concise and accurate.",
  };
  return prompts[intent];
}

// Stage 3: generate a response with the appropriate persona
async function generateResponse(
  env: Env,
  systemPrompt: string,
  userMessage: string,
  maxTokens = 512
): Promise<string> {
  const result = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user",   content: userMessage },
    ],
    max_tokens: maxTokens,
    temperature: 0.3,
  });
  return result.response ?? "";
}

// Stage 4: embed the response for logging / similarity dedup
async function embedText(env: Env, text: string): Promise<number[]> {
  const result = await env.AI.run("@cf/baai/bge-base-en-v1.5", {
    text: [text],
  });
  return result.data[0];
}

export { classifyIntent, buildSystemPrompt, generateResponse, embedText };
```

## Sequential Pipeline Orchestration

Wire stages together with explicit data flow. Log stage outputs for debugging.

```typescript
// src/index.ts
import {
  classifyIntent, buildSystemPrompt, generateResponse, embedText
} from "./pipeline";

interface Env {
  AI:        Ai;
  VECTORIZE: VectorizeIndex;
}

interface PipelineResult {
  intent:    string;
  response:  string;
  durationMs: { classify: number; generate: number; embed: number };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { message } = await request.json<{ message: string }>();

    const t0 = Date.now();
    const intent = await classifyIntent(env, message);
    const classifyMs = Date.now() - t0;

    const systemPrompt = buildSystemPrompt(intent);

    const t1 = Date.now();
    const response = await generateResponse(env, systemPrompt, message);
    const generateMs = Date.now() - t1;

    const t2 = Date.now();
    const embedding = await embedText(env, response);
    const embedMs = Date.now() - t2;

    // Async: upsert response embedding for dedup/analytics (don't await on hot path)
    const logId = crypto.randomUUID();
    // env.VECTORIZE.upsert([{ id: logId, values: embedding, metadata: { intent } }]);

    const result: PipelineResult = {
      intent,
      response,
      durationMs: { classify: classifyMs, generate: generateMs, embed: embedMs },
    };

    return Response.json(result);
  },
};
```

## Parallel Fan-out for Independent Stages

When stages do not depend on each other's output, run them in parallel to minimise wall-clock latency.

```typescript
// Example: enrich an article with both a summary and keyword tags simultaneously
async function enrichArticle(
  env: Env,
  articleText: string
): Promise<{ summary: string; keywords: string[]; embedding: number[] }> {
  const summaryPromise = env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [
      { role: "system", content: "Summarise the article in 2-3 sentences." },
      { role: "user",   content: articleText },
    ],
    max_tokens: 200,
    temperature: 0.2,
  });

  const keywordsPromise = env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [
      { role: "system", content: 'Extract 5-10 keywords as a JSON array of strings. Return ONLY the JSON array.' },
      { role: "user",   content: articleText },
    ],
    max_tokens: 100,
    temperature: 0,
    response_format: { type: "json_object" },
  });

  const embeddingPromise = env.AI.run("@cf/baai/bge-base-en-v1.5", {
    text: [articleText.slice(0, 2000)], // embed a prefix for cost control
  });

  const [summaryResult, keywordsResult, embeddingResult] = await Promise.all([
    summaryPromise, keywordsPromise, embeddingPromise,
  ]);

  let keywords: string[] = [];
  try {
    const parsed = JSON.parse(keywordsResult.response ?? "[]");
    keywords = Array.isArray(parsed) ? parsed : (parsed.keywords ?? []);
  } catch {
    keywords = [];
  }

  return {
    summary:   summaryResult.response ?? "",
    keywords,
    embedding: embeddingResult.data[0],
  };
}
```

## Multimodal Pipeline: Image Caption + Text Summary

Chain image understanding with text generation. The caption from the vision model seeds the text generation prompt.

```typescript
async function captionAndSummarise(
  env: Env,
  imageBase64: string,
  articleText: string
): Promise<{ caption: string; summary: string }> {
  // Step 1: caption the image
  const captionResult = await env.AI.run(
    "@cf/llava-hf/llava-1.5-7b-hf",
    {
      image:  [...atob(imageBase64)].map((c) => c.charCodeAt(0)),
      prompt: "Describe what you see in this image in one sentence.",
      max_tokens: 100,
    }
  );

  const caption = captionResult.description ?? "";

  // Step 2: summarise article with image context injected
  const summaryResult = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [
      {
        role: "system",
        content: "You summarise articles. An image accompanies the article.",
      },
      {
        role: "user",
        content: `Image: ${caption}\n\nArticle:\n${articleText}\n\nProvide a 3-sentence summary.`,
      },
    ],
    max_tokens: 256,
    temperature: 0.3,
  });

  return { caption, summary: summaryResult.response ?? "" };
}
```

## Error Isolation per Stage

Wrap each stage in a try/catch so a failure in one stage does not silently corrupt downstream results.

```typescript
async function runStageSafely<T>(
  stageName: string,
  fn: () => Promise<T>,
  fallback: T
): Promise<T> {
  try {
    return await fn();
  } catch (err) {
    console.error(`Pipeline stage "${stageName}" failed:`, err instanceof Error ? err.message : err);
    return fallback;
  }
}

// Usage in orchestration:
const intent = await runStageSafely("classify", () => classifyIntent(env, message), "general");
const response = await runStageSafely(
  "generate",
  () => generateResponse(env, buildSystemPrompt(intent), message),
  "I'm sorry, I couldn't process your request right now."
);
```

## Anti-patterns
- Inlining all model calls in a single fetch handler — stage isolation is impossible and latency profiling is guesswork
- Using `Promise.allSettled()` without checking rejection status — a failed embedding stage silently returns `undefined` and corrupts downstream upserts
- Passing full document text through every stage — truncate at the stage that needs it; later stages often need less context
- Awaiting stages that could run in parallel — adds unnecessary latency; map dependency graphs before sequencing
- Catching errors and swallowing them with empty strings — use explicit fallback values and log stage failures for alerting

## Gotchas
- Workers AI billing counts each model invocation independently — a 3-stage pipeline that fires 3 model calls on every request triples your inference cost
- The Workers CPU time limit (30ms for free, 30s for paid on CPU-intensive code) can be hit if you chain many sequential calls — use Durable Objects or Queues for long pipelines
- `@cf/llava-hf/llava-1.5-7b-hf` accepts raw image bytes (Uint8Array), not base64 strings — convert before passing
- Parallel `Promise.all()` calls to the same model ID compete for the same capacity pool — spreading load across model families (classify with a small model, generate with a large one) reduces contention
- `response_format: { type: "json_object" }` returns a raw JSON string in `result.response`, not a parsed object — always `JSON.parse()`

## Verification
```bash
# Test sequential pipeline
curl -X POST http://localhost:8787/ \
  -H "Content-Type: application/json" \
  -d '{"message":"My order arrived broken, I want a refund"}' \
  | jq '{ intent: .intent, durationMs: .durationMs }'

# Verify intent routing (should be "support" for above message)
# Verify stage durations are logged for latency profiling

# Test parallel enrichment endpoint
curl -X POST http://localhost:8787/enrich \
  -H "Content-Type: application/json" \
  -d '{"text":"Cloudflare announced new AI features at their developer conference..."}' \
  | jq '{ keywordCount: (.keywords | length), summaryLen: (.summary | length) }'
```

## Related
- [workers-ai-function-calling-agentic-patterns.md](workers-ai-function-calling-agentic-patterns.md)
- [workers-ai-durable-objects-stateful-sessions.md](workers-ai-durable-objects-stateful-sessions.md)
- [workers-ai-queue-batch-processing.md](workers-ai-queue-batch-processing.md)
- [llm-async-patterns.md](llm-async-patterns.md)
- [multimodal-vision-patterns.md](multimodal-vision-patterns.md)

## Sources
- Cloudflare Workers AI model catalog: https://developers.cloudflare.com/workers-ai/models/
- Workers AI LLaVA vision model: https://developers.cloudflare.com/workers-ai/models/llava-1.5-7b-hf/
- Workers execution limits: https://developers.cloudflare.com/workers/platform/limits/
