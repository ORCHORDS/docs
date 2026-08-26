# Workers AI Silently Truncates Inputs That Exceed the Context Window

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A document-summarisation Worker was producing summaries that ignored the second half
of long documents. No error was returned by `env.AI.run()`; the response `success`
field was `true`. Users reported "the AI seems to forget what the document says after
page 3." The bug was live for six weeks before it was caught through a user complaint,
not monitoring.

---

## Context

Every Workers AI model has a **context window** measured in tokens (not bytes or
characters). When the combined token count of the system prompt + user messages
exceeds the model's limit, the inference runtime truncates the input from the end
without raising an exception. The `response` field in the result is populated with
whatever the model inferred from the truncated input, and `success` is still `true`.

As of mid-2026, commonly used models and their approximate limits:

| Model                            | Context window (tokens) |
|----------------------------------|------------------------|
| `@cf/meta/llama-3.1-8b-instruct` | 128 000                |
| `@cf/mistral/mistral-7b-instruct-v0.1` | 32 768          |
| `@cf/google/gemma-7b-it`         | 8 192                  |
| `@cf/qwen/qwen1.5-1.8b-chat`     | 32 768                 |

The application was using `gemma-7b-it` because it was the fastest model at the time
of initial development, but nobody rechecked the limit when average document length
grew from 800 words to 4 500 words over the following quarter.

---

## How the Silent Failure Manifests

```typescript
// src/summarise.ts — original broken version
import type { Ai } from "@cloudflare/workers-types";

export async function summarise(ai: Ai, documentText: string): Promise<string> {
  const response = await ai.run("@cf/google/gemma-7b-it", {
    messages: [
      {
        role: "system",
        content: "You are a concise summariser. Summarise the document provided.",
      },
      {
        role: "user",
        content: documentText, // may be 12 000+ tokens; model limit is 8 192
      },
    ],
  });

  // response.response is a non-empty string even when input was truncated.
  // There is no response.truncated flag or token-count field in the result.
  return (response as { response: string }).response;
}
```

The model receives only the first ~7 800 tokens (leaving ~400 for the system prompt
and generation), silently discards the rest, and returns a confident-sounding summary
of the truncated input.

---

## Estimating Token Count Before Inference

Workers AI does not expose a tokenisation endpoint. Use a rule-of-thumb estimate
(~4 characters per token for English prose) or a lightweight WASM tokeniser. For
safety, stay under 80 % of the model's advertised limit to leave room for the system
prompt and expected output.

```typescript
// src/tokeniser.ts
/** Rough character-based token estimator for English text (~4 chars/token). */
export function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4);
}

const MODEL_CONTEXT_LIMITS: Record<string, number> = {
  "@cf/meta/llama-3.1-8b-instruct": 128_000,
  "@cf/mistral/mistral-7b-instruct-v0.1": 32_768,
  "@cf/google/gemma-7b-it": 8_192,
  "@cf/qwen/qwen1.5-1.8b-chat": 32_768,
};

const SAFETY_FACTOR = 0.8; // use at most 80 % of context for user content

export function maxUserTokens(model: string, systemPromptTokens: number): number {
  const limit = MODEL_CONTEXT_LIMITS[model] ?? 4_096;
  return Math.floor(limit * SAFETY_FACTOR) - systemPromptTokens;
}
```

---

## Chunked Summarisation for Long Documents

When the document exceeds the safe token budget, split it into overlapping chunks,
summarise each chunk independently, then summarise the summaries (map-reduce pattern).

```typescript
// src/summarise.ts — safe version
import type { Ai } from "@cloudflare/workers-types";
import { estimateTokens, maxUserTokens } from "./tokeniser";

const MODEL = "@cf/meta/llama-3.1-8b-instruct"; // 128 k context; better for long docs

const SYSTEM_PROMPT =
  "You are a concise summariser. Summarise the text provided in 3-5 sentences.";
const SYSTEM_TOKENS = estimateTokens(SYSTEM_PROMPT);

async function summariseChunk(ai: Ai, chunk: string): Promise<string> {
  const result = await (ai.run as Function)(MODEL, {
    messages: [
      { role: "system", content: SYSTEM_PROMPT },
      { role: "user", content: chunk },
    ],
    max_tokens: 512,
  });
  return (result as { response: string }).response;
}

function splitIntoChunks(text: string, maxTokens: number): string[] {
  const chunkSize = maxTokens * 4; // characters, approx
  const overlap = Math.floor(chunkSize * 0.1); // 10 % overlap to preserve context
  const chunks: string[] = [];
  let start = 0;

  while (start < text.length) {
    const end = Math.min(start + chunkSize, text.length);
    chunks.push(text.slice(start, end));
    if (end === text.length) break;
    start = end - overlap;
  }
  return chunks;
}

export async function summarise(ai: Ai, documentText: string): Promise<string> {
  const userBudget = maxUserTokens(MODEL, SYSTEM_TOKENS);
  const docTokens = estimateTokens(documentText);

  if (docTokens <= userBudget) {
    // Document fits; summarise directly.
    return summariseChunk(ai, documentText);
  }

  // Map: summarise each chunk.
  const chunks = splitIntoChunks(documentText, userBudget);
  console.log(`Document split into ${chunks.length} chunks for summarisation.`);

  const chunkSummaries = await Promise.all(
    chunks.map((c) => summariseChunk(ai, c)),
  );

  // Reduce: if summaries still exceed budget, recurse once.
  const combined = chunkSummaries.join("\n\n");
  if (estimateTokens(combined) > userBudget) {
    return summarise(ai, combined); // one level of recursion is usually sufficient
  }

  return summariseChunk(ai, combined);
}
```

---

## Alerting on Suspiciously Short Outputs

Add a heuristic check: if the output is shorter than 10 % of the input length for
documents over a certain size, it is likely a truncation or a refusal.

```typescript
// src/summarise.ts (additions)
export function validateSummary(
  input: string,
  summary: string,
  minOutputChars = 100,
): void {
  if (summary.length < minOutputChars) {
    throw new Error(
      `Summary suspiciously short (${summary.length} chars) for input of ` +
        `${input.length} chars. Possible context truncation.`,
    );
  }

  const ratio = summary.length / input.length;
  if (input.length > 2_000 && ratio > 0.9) {
    // Output nearly as long as input — model may have repeated the document.
    console.warn(`Summary/input ratio unusually high: ${ratio.toFixed(2)}`);
  }
}
```

---

## Choosing the Right Model for Long Documents

```typescript
// src/model-selector.ts
export function selectModel(estimatedInputTokens: number): string {
  if (estimatedInputTokens <= 6_000) return "@cf/google/gemma-7b-it"; // fastest
  if (estimatedInputTokens <= 28_000) return "@cf/mistral/mistral-7b-instruct-v0.1";
  return "@cf/meta/llama-3.1-8b-instruct"; // 128 k; use for large documents
}
```

Prefer automatic model selection over hardcoding a single model across all document
sizes. Re-evaluate the table above quarterly; Workers AI model offerings change.

---

## Anti-patterns

- **Hardcoding a small-context model for all input sizes** — usage patterns grow;
  the model that was "fine" at launch will fail silently as average document length
  increases.
- **Treating `success: true` as correctness** — Workers AI returns `success: true`
  as long as the inference call itself did not crash; it says nothing about input
  completeness.
- **Counting characters instead of tokens for limit checks** — English text averages
  ~4 chars/token but code, JSON, and non-Latin scripts have very different ratios.
  Use a per-model tokeniser or a conservative safety margin.
- **Infinite recursion in map-reduce** — without a base case or depth limit, the
  reduce step can recurse indefinitely if summaries are unexpectedly verbose.

---

## Gotchas

- Workers AI **does not expose token-count metadata** in the current API response
  (`input_tokens`, `output_tokens` are absent). You must estimate pre-call.
- Model context limits listed in documentation are **total context** (prompt +
  completion). If you set `max_tokens: 1024` for the response, that 1 024 is
  subtracted from the available input budget.
- `@cf/meta/llama-3.1-8b-instruct` supports up to 128 k tokens but cold-start
  latency is materially higher than smaller models — do not default to it for short
  documents.
- The Workers AI `run` method TypeScript types are generic; always cast the result
  to the expected response shape and validate it at runtime.

---

## Verification

```bash
# Smoke-test with a document known to exceed 8 192 tokens:
echo "Running long-document summarisation test..."
npx wrangler dev --test-scheduled
# Or use a unit test with Miniflare / vitest:
# expect(summary.length).toBeGreaterThan(100);
# expect(estimateTokens(summary)).toBeLessThan(600);

# Monitor output lengths in production with Workers Analytics Engine or Logpush:
# SELECT AVG(LENGTH(summary)), MIN(LENGTH(summary)) FROM inference_logs;
```

---

## Related

- `workers-ai-cold-start-latency-production-lesson.md`
- `workers-ai-rate-limit-exceeded-production-incident.md`
- `workers-ai-model-deprecation-migration-adr.md`
- `workers-ai-hallucination-moderation-false-positive-incident.md`
- `ai-rag-patterns-2026.md`

---

## Sources

- Cloudflare Workers AI model catalogue:
  https://developers.cloudflare.com/workers-ai/models/
- Internal incident #3204 (2026-05-07) — "Summariser ignores second half of docs"
- Hugging Face tokeniser docs — token/character ratios per model family
