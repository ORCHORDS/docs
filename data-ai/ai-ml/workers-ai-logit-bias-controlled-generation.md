# Workers AI Logit Bias for Controlled Token Generation

date: 2026-08-24 / author: example.com / status: production

---

## Symptom / Use-case

A Workers AI text-generation model occasionally outputs tokens you must never emit — competitor
brand names in customer-facing copy, profanity in a moderated forum, or specific JSON field names
that would break a downstream parser. You want to steer the sampling distribution away from
forbidden tokens (or toward preferred tokens) without adding a post-processing filter that discards
and retries entire responses.

## Context

Most Workers AI text-generation models that support the `logit_bias` parameter accept a mapping of
token IDs to bias scalars. A negative bias (e.g. `-100`) effectively bans a token; a positive bias
(e.g. `+5`) makes it significantly more likely. The bias is added to the raw logit before the
softmax so it operates in log-space: a bias of +10 makes a token roughly 22 000× more likely; -100
makes it negligible.

Token IDs are model-specific and tied to the tokenizer. For Llama-based models the tokenizer
vocabulary is public; you look up the token ID for a string using the model's tokenizer, then pass
the `{tokenId: bias}` map in the API call. Not all Workers AI models expose `logit_bias`; the
pattern applies to models that accept it (currently the Llama 3.x family and compatible models).

---

## Tokenizer lookup utility

```typescript
// src/tokenizer.ts
// Workers AI does not expose a tokenizer endpoint; look up token IDs
// from the published Llama 3 tokenizer vocabulary or use a lightweight
// JS port of tiktoken / @huggingface/transformers in a build step.

/**
 * A pre-built lookup for common banned tokens in the Llama 3 tokenizer.
 * Build this map offline using the tokenizer vocab and check it into source.
 *
 * Token IDs shown here are illustrative — replace with real IDs from the
 * model's tokenizer.json vocabulary file.
 */
export const BANNED_TOKEN_IDS: Record<string, number> = {
  "CompetitorA":  12483,
  "CompetitorB":  29900,
  "CompetitorC":  15290,
  "damn":          2952,
  "hell":          7096,
};

export const STRONG_SUPPRESS = -100;  // effectively bans the token
export const MILD_SUPPRESS   = -10;   // makes the token ~22 000× less likely
export const ENCOURAGE        = 5;    // makes the token ~150× more likely

/**
 * Build a logit_bias map from a list of human-readable token strings.
 * Unknown tokens are silently skipped.
 */
export function buildLogitBias(
  tokens: string[],
  bias: number,
): Record<number, number> {
  const result: Record<number, number> = {};
  for (const token of tokens) {
    const id = BANNED_TOKEN_IDS[token];
    if (id !== undefined) {
      result[id] = bias;
    }
  }
  return result;
}
```

---

## Inference call with logit_bias

```typescript
// src/inference.ts
import { buildLogitBias, STRONG_SUPPRESS } from "./tokenizer";

export interface Env {
  AI: Ai;
}

export interface GenerationOptions {
  /** Token strings to suppress entirely. */
  bannedTokens?: string[];
  /** Token strings to gently discourage. */
  discouragedTokens?: string[];
  /** Token strings to encourage. */
  preferredTokens?: string[];
  maxTokens?: number;
  temperature?: number;
}

export interface GenerationResult {
  text: string;
  logitBiasApplied: Record<number, number>;
}

export async function generateWithBias(
  env: Env,
  systemPrompt: string,
  userMessage: string,
  options: GenerationOptions = {},
): Promise<GenerationResult> {
  const {
    bannedTokens = [],
    discouragedTokens = [],
    preferredTokens = [],
    maxTokens = 512,
    temperature = 0.7,
  } = options;

  // Merge bias maps — banned tokens take priority over discouraged
  const logitBias: Record<number, number> = {
    ...buildLogitBias(discouragedTokens, -10),
    ...buildLogitBias(bannedTokens, STRONG_SUPPRESS),
    ...buildLogitBias(preferredTokens, 5),
  };

  const result = await env.AI.run("@cf/meta/llama-3.1-8b-instruct" as any, {
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user",   content: userMessage },
    ],
    max_tokens: maxTokens,
    temperature,
    logit_bias: Object.keys(logitBias).length > 0 ? logitBias : undefined,
  });

  const text =
    typeof result === "object" && result !== null && "response" in result
      ? String((result as any).response)
      : String(result);

  return { text, logitBiasApplied: logitBias };
}
```

---

## Worker entry point with preset ban lists

```typescript
// src/index.ts
import { generateWithBias, type Env } from "./inference";

export { Env };

// Domain-specific ban list — store in KV for runtime updates
const COMPETITOR_TOKENS = ["CompetitorA", "CompetitorB", "CompetitorC"];
const PROFANITY_TOKENS  = ["damn", "hell"];

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const body = await request.json() as {
      prompt: string;
      mode?: "marketing" | "support" | "general";
    };

    if (!body.prompt) {
      return new Response(JSON.stringify({ error: "prompt required" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    const mode = body.mode ?? "general";
    const bannedTokens =
      mode === "marketing"
        ? [...COMPETITOR_TOKENS, ...PROFANITY_TOKENS]
        : PROFANITY_TOKENS;

    const { text, logitBiasApplied } = await generateWithBias(
      env,
      "You are a helpful assistant. Be concise and professional.",
      body.prompt,
      { bannedTokens, temperature: 0.7, maxTokens: 256 },
    );

    return new Response(
      JSON.stringify({
        response: text,
        biasedTokenCount: Object.keys(logitBiasApplied).length,
      }),
      { headers: { "Content-Type": "application/json" } },
    );
  },
};
```

---

## KV-based dynamic ban list for runtime updates

```typescript
// src/ban-list-kv.ts

export interface Env {
  BAN_LIST_KV: KVNamespace;
}

export interface BanList {
  strongSuppress: string[];  // -100 bias
  mildSuppress:   string[];  // -10  bias
  encourage:      string[];  // +5   bias
  updatedAt:      number;
}

const BAN_LIST_KEY = "ban-list:v1";
const DEFAULT_BAN_LIST: BanList = {
  strongSuppress: [],
  mildSuppress:   [],
  encourage:      [],
  updatedAt:      0,
};

export async function loadBanList(kv: KVNamespace): Promise<BanList> {
  const raw = await kv.get(BAN_LIST_KEY, { type: "json" });
  return (raw as BanList | null) ?? DEFAULT_BAN_LIST;
}

export async function updateBanList(kv: KVNamespace, list: BanList): Promise<void> {
  list.updatedAt = Date.now();
  await kv.put(BAN_LIST_KEY, JSON.stringify(list));
}

// Cache the ban list in-memory per isolate (refreshed every 60 s)
let cachedList: BanList = DEFAULT_BAN_LIST;
let cacheExpiry = 0;

export async function getCachedBanList(kv: KVNamespace): Promise<BanList> {
  if (Date.now() > cacheExpiry) {
    cachedList = await loadBanList(kv);
    cacheExpiry = Date.now() + 60_000;
  }
  return cachedList;
}
```

---

## Validation: confirm bias is working

```typescript
// src/bias-validator.ts
// Use this in integration tests to confirm banned tokens never appear.

export async function validateNoBannedOutput(
  response: string,
  bannedWords: string[],
): Promise<{ passed: boolean; violations: string[] }> {
  const lower = response.toLowerCase();
  const violations = bannedWords.filter((w) => lower.includes(w.toLowerCase()));
  return { passed: violations.length === 0, violations };
}

// Note: logit_bias suppresses at the token level, not the word level.
// A strongly biased (-100) token will not appear in output in practice,
// but multi-token words can still appear if only *some* of their tokens are banned.
// Always validate output post-generation for multi-token banned phrases.
```

## Anti-patterns

- **Banning words by string match instead of token IDs** — `logit_bias` operates on token IDs; a
  word like "CompetitorA" may split across 2-3 tokens in the tokenizer. You must suppress all
  token ID variants that produce the banned word.
- **Applying large positive biases to preferred tokens** — biases above +10 distort the sampling
  distribution enough to degrade output quality and coherence; prefer +2 to +5 for gentle guidance.
- **Assuming token IDs are stable across model versions** — tokenizer vocabularies can change with
  model updates; rebuild and validate the token ID map after every model upgrade.
- **Using logit_bias as a content moderation substitute** — it reduces but does not eliminate
  undesired outputs (multi-token paths can bypass single-token suppression); always layer a
  post-generation content filter.
- **Not checking if the model supports logit_bias** — passing an unsupported parameter to a model
  that ignores it silently produces unbounded output; verify support in the model's capability spec.

## Gotchas

- A bias of -100 does not set the probability to zero — floating-point softmax keeps a tiny
  residual probability; in practice this is negligible for single tokens but compound multi-token
  words require all constituent token IDs to be suppressed.
- Workers AI may not forward unknown parameters to all models; if `logit_bias` is silently ignored
  the call succeeds with no error — validate by checking output for banned tokens in CI.
- The Llama 3 tokenizer uses byte-pair encoding; a surface word maps to different token IDs
  depending on whether it appears at the start of a sentence, mid-sentence, or with leading
  whitespace (e.g. `" France"` ≠ `"France"` — they are different tokens).
- Very long ban lists (> 500 entries) may exceed API payload limits; batch into multiple focused
  lists and select the appropriate one per use-case.

## Verification

```bash
# Call with a competitor ban list and check the response never contains the banned word
curl -sX POST https://your-worker.workers.dev \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Compare us to CompetitorA","mode":"marketing"}' \
  | jq -r .response | grep -ic "competitora"
# Expected: 0

# Check biasedTokenCount to confirm logit_bias was applied
curl -sX POST https://your-worker.workers.dev \
  -H "Content-Type: application/json" \
  -d '{"prompt":"hello","mode":"marketing"}' \
  | jq .biasedTokenCount
# Expected: > 0
```

## Related

- `workers-ai-structured-output-regex-constraint.md` — regex grammar constraints for structured output
- `workers-ai-json-schema-constrained-generation.md` — JSON schema constrained generation
- `llm-output-filtering.md` — post-generation output filtering
- `prompt-injection-defense-strategies.md` — defence against prompt injection attacks
- `workers-ai-inference-parameter-tuning.md` — temperature, top-p, and other sampling parameters

## Sources

- Llama 3 tokenizer vocabulary: https://huggingface.co/meta-llama/Meta-Llama-3.1-8B
- Workers AI run API: https://developers.cloudflare.com/workers-ai/
- OpenAI logit_bias reference (compatible interface): https://platform.openai.com/docs/api-reference/chat/create#logit_bias
