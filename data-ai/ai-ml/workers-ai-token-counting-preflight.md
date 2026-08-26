# Workers AI Token Counting Pre-flight

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Requests to Workers AI text-generation models fail with a context-length error, or you are paying for inference that gets truncated mid-response. You need to know token counts *before* dispatching the inference call so you can trim prompts, select the right model, or reject oversized inputs early.

## Context

Workers AI does not expose a native `/tokenize` endpoint. Token estimation must happen in the Worker itself. The two practical approaches are:

1. **Heuristic estimation** — fast, zero-latency, ±10 % accuracy using a chars-per-token ratio (≈4 chars/token for English prose).
2. **`@cf/meta/llama-tokenizer` or Tiktoken WASM** — exact token count compiled to WASM, running inside the Worker isolate (no network call, ~2–5 ms overhead).

A pre-flight check gates the inference call: if estimated tokens > `maxContextTokens − reservedOutputTokens`, reject or truncate before wasting quota.

---

## 1. Heuristic Token Estimator (Zero Dependencies)

```typescript
/**
 * Fast heuristic: 1 token ≈ 4 chars for English text.
 * Add a 15 % buffer for code, markdown, or multilingual content.
 */
export function estimateTokens(text: string, buffer = 1.15): number {
  return Math.ceil((text.length / 4) * buffer);
}

export function buildPrompt(system: string, user: string): string {
  return `<|system|>\n${system}\n<|user|>\n${user}\n<|assistant|>`;
}

interface PreflightResult {
  ok: boolean;
  estimatedTokens: number;
  maxAllowed: number;
  message?: string;
}

export function preflightCheck(
  promptText: string,
  maxContextTokens = 4096,
  reservedOutputTokens = 512,
): PreflightResult {
  const maxAllowed = maxContextTokens - reservedOutputTokens;
  const estimatedTokens = estimateTokens(promptText);

  if (estimatedTokens > maxAllowed) {
    return {
      ok: false,
      estimatedTokens,
      maxAllowed,
      message: `Prompt too long: ~${estimatedTokens} tokens exceeds limit of ${maxAllowed}.`,
    };
  }

  return { ok: true, estimatedTokens, maxAllowed };
}
```

## 2. Enforcing Pre-flight in a Worker Handler

```typescript
import { Ai } from "@cloudflare/ai";
import { buildPrompt, preflightCheck } from "./token-utils";

export interface Env {
  AI: Ai;
}

const MODEL = "@cf/meta/llama-3.1-8b-instruct";
const MAX_CONTEXT = 8192;
const RESERVED_OUTPUT = 1024;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { system, user } = await request.json<{
      system: string;
      user: string;
    }>();

    const prompt = buildPrompt(system, user);
    const preflight = preflightCheck(prompt, MAX_CONTEXT, RESERVED_OUTPUT);

    if (!preflight.ok) {
      return Response.json(
        { error: preflight.message, estimatedTokens: preflight.estimatedTokens },
        { status: 422 },
      );
    }

    const result = await env.AI.run(MODEL, {
      prompt,
      max_tokens: RESERVED_OUTPUT,
    });

    return Response.json({
      response: result.response,
      preflight: {
        estimatedTokens: preflight.estimatedTokens,
        budgetRemaining: preflight.maxAllowed - preflight.estimatedTokens,
      },
    });
  },
};
```

## 3. Dynamic Prompt Trimming When Over Budget

```typescript
export function trimToTokenBudget(
  messages: Array<{ role: string; content: string }>,
  budgetTokens: number,
): Array<{ role: string; content: string }> {
  const trimmed: Array<{ role: string; content: string }> = [];
  let usedTokens = 0;

  // Always keep system message (first entry)
  if (messages[0]?.role === "system") {
    const sysTokens = estimateTokens(messages[0].content);
    usedTokens += sysTokens;
    trimmed.push(messages[0]);
  }

  // Walk history newest-first, keeping until budget is reached
  const history = messages.slice(1).reverse();
  for (const msg of history) {
    const t = estimateTokens(msg.content);
    if (usedTokens + t > budgetTokens) break;
    usedTokens += t;
    trimmed.unshift(msg);
  }

  return trimmed;
}

// Usage in a multi-turn chat handler
async function handleChat(
  env: Env,
  messages: Array<{ role: string; content: string }>,
): Promise<string> {
  const trimmedMessages = trimToTokenBudget(messages, MAX_CONTEXT - RESERVED_OUTPUT);

  const result = await env.AI.run(MODEL, {
    messages: trimmedMessages,
    max_tokens: RESERVED_OUTPUT,
  });

  return result.response ?? "";
}
```

## 4. Model-aware Context Limits Registry

```typescript
const MODEL_CONTEXT_LIMITS: Record<string, number> = {
  "@cf/meta/llama-3.1-8b-instruct": 8192,
  "@cf/meta/llama-3.3-70b-instruct-fp8-fast": 8192,
  "@cf/mistral/mistral-7b-instruct-v0.1": 4096,
  "@cf/google/gemma-7b-it": 8192,
  "@cf/deepseek-ai/deepseek-r1-distill-qwen-32b": 32768,
};

export function getModelBudget(
  model: string,
  reservedOutput = 512,
): { maxInput: number; maxOutput: number } {
  const contextLimit = MODEL_CONTEXT_LIMITS[model] ?? 4096;
  return {
    maxInput: contextLimit - reservedOutput,
    maxOutput: reservedOutput,
  };
}

// In handler:
// const { maxInput } = getModelBudget(MODEL, RESERVED_OUTPUT);
// const preflight = preflightCheck(prompt, maxInput + RESERVED_OUTPUT, RESERVED_OUTPUT);
```

## 5. Logging Token Estimates to Analytics Engine

```typescript
export interface Env {
  AI: Ai;
  ANALYTICS: AnalyticsEngineDataset;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const body = await request.json<{ system: string; user: string }>();
    const prompt = buildPrompt(body.system, body.user);
    const { estimatedTokens } = preflightCheck(prompt, MAX_CONTEXT, RESERVED_OUTPUT);

    const start = Date.now();
    const result = await env.AI.run(MODEL, { prompt, max_tokens: RESERVED_OUTPUT });
    const latencyMs = Date.now() - start;

    env.ANALYTICS.writeDataPoint({
      blobs: [MODEL, request.headers.get("cf-ray") ?? ""],
      doubles: [estimatedTokens, latencyMs],
      indexes: [MODEL],
    });

    return Response.json({ response: result.response });
  },
};
```

---

## Anti-patterns

- **Using a fixed chars-per-token ratio for all languages** — CJK and emoji characters tokenize very differently (1 char ≈ 1–2 tokens for CJK). Apply a higher multiplier (1.5–2×) or use an exact tokenizer for non-Latin content.
- **Setting `max_tokens` without a pre-flight check** — the model may silently truncate its output when context fills up; callers interpret this as a complete response.
- **Counting raw JSON payload bytes instead of the extracted text** — JSON wrapper characters (`"`, `{`, `}`) do not appear in the prompt but inflate byte counts; extract text content first.
- **Applying the same context limit to all models** — each model family has its own context window; hardcoding 4096 will reject valid prompts for models with 32 k contexts.

## Gotchas

- Workers AI does not expose the actual token count used post-inference; heuristics are the only pre-call signal available.
- `max_tokens` in the Workers AI binding limits output tokens, not total context; an oversized input still fails with a 400 error even if `max_tokens` is small.
- WASM-based tokenizers (Tiktoken, Llama tokenizer) can be bundled into Workers but add ~1–3 MB to the bundle; ensure you are within the 10 MB Workers bundle limit.
- Prompt formatting tokens (special tokens like `<|system|>`, `[INST]`) consume tokens but are invisible in the raw text; add ~50 tokens as a formatting overhead constant.

## Verification

```bash
# Send a prompt near the limit and confirm pre-flight rejection
curl -X POST https://my-worker.workers.dev/chat \
  -H "Content-Type: application/json" \
  -d '{"system":"You are helpful.","user":"'"$(python3 -c "print('word '*2000)")"'"}'

# Expected: 422 with {"error":"Prompt too long: ~2300 tokens exceeds limit of 7680."}

# Send a valid prompt and check preflight metadata in response
curl -X POST https://my-worker.workers.dev/chat \
  -H "Content-Type: application/json" \
  -d '{"system":"Be concise.","user":"What is Cloudflare Workers AI?"}'

# Expected: 200 with preflight.estimatedTokens < 7680
```

## Related

- `llm-token-counting.md`
- `llm-context-window-cloudflare-workers.md`
- `llm-prompt-compression-kv-cache-efficiency-workers.md`
- `workers-ai-inference-parameter-tuning.md`
- `model-cascade-cheap-first-routing.md`

## Sources

- Workers AI model catalog and context limits: https://developers.cloudflare.com/workers-ai/models/
- Cloudflare Workers bundle size limits: https://developers.cloudflare.com/workers/platform/limits/
- OpenAI Tiktoken tokenizer (reference): https://github.com/openai/tiktoken
