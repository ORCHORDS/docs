# Workers AI Inference Parameter Tuning

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Workers AI text-generation responses feel too random (hallucinating facts), too repetitive (loops on
the same phrase), or too conservative (short, hedge-heavy outputs). You need to tune decoding
parameters — temperature, top_p, top_k, repetition_penalty, frequency_penalty, seed — to hit the
right quality/diversity trade-off for each workload without switching models.

## Context

Cloudflare Workers AI exposes a subset of the standard text-generation decoding parameters for
models like `@cf/meta/llama-3.1-8b-instruct`, `@cf/mistral/mistral-7b-instruct-v0.2`, and the
larger `@cf/meta/llama-3.3-70b-instruct-fp8-fast`. Not every model honours every parameter — the
binding silently drops unsupported keys. Parameters are passed in the `AiTextGenerationInput` object
alongside `messages` or `prompt`. They are evaluated at inference time on Cloudflare's GPU fleet,
so there is no cold-start penalty for changing values between requests.

Understanding the interaction between parameters prevents contradictory settings that degrade quality
(e.g. low temperature + high top_p makes top_p irrelevant).

## Core Parameters

| Parameter | Type | Default | Effect |
|---|---|---|---|
| `temperature` | float [0, 5] | `1.0` | Scales logit distribution before sampling. 0 = greedy. |
| `top_p` | float (0, 1] | `1.0` | Nucleus sampling; keeps tokens whose cumulative prob ≥ top_p. |
| `top_k` | int ≥ 1 | disabled | Keeps top-k highest-probability tokens before sampling. |
| `repetition_penalty` | float ≥ 1 | `1.0` | Penalises tokens already in the output. |
| `frequency_penalty` | float [-2, 2] | `0.0` | Linearly penalises tokens by frequency in output so far. |
| `seed` | int | random | Fixes the PRNG for reproducible outputs. |
| `max_tokens` | int | model max | Hard cap on output length. |

## Temperature

Temperature < 1 sharpens the distribution (more deterministic, higher-confidence tokens win).
Temperature > 1 flattens it (more randomness, long-tail tokens surface). Use 0 for deterministic
code generation or classification; 0.7–0.9 for creative writing; leave at 1.0 for chat.

```typescript
// src/inference.ts
import type { AiTextGenerationInput } from "@cloudflare/workers-types";

interface TextGenOptions {
  temperature?: number;
  topP?: number;
  topK?: number;
  repetitionPenalty?: number;
  frequencyPenalty?: number;
  seed?: number;
  maxTokens?: number;
}

export async function generate(
  ai: Ai,
  model: BaseAiTextGenerationModels,
  systemPrompt: string,
  userMessage: string,
  opts: TextGenOptions = {}
): Promise<string> {
  const input: AiTextGenerationInput = {
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: userMessage },
    ],
    temperature: opts.temperature ?? 1.0,
    top_p: opts.topP ?? 1.0,
    ...(opts.topK !== undefined && { top_k: opts.topK }),
    repetition_penalty: opts.repetitionPenalty ?? 1.0,
    frequency_penalty: opts.frequencyPenalty ?? 0.0,
    ...(opts.seed !== undefined && { seed: opts.seed }),
    max_tokens: opts.maxTokens ?? 512,
  };

  const result = await ai.run(model, input);
  if (result instanceof ReadableStream) {
    throw new Error("Did not expect streaming response");
  }
  return (result as { response?: string }).response ?? "";
}
```

## Preset Profiles for Common Workloads

Define named presets rather than scattering magic numbers across handler code.

```typescript
// src/presets.ts
export const INFERENCE_PRESETS = {
  /** Structured extraction, JSON, classification */
  deterministic: {
    temperature: 0.1,
    topP: 0.9,
    repetitionPenalty: 1.0,
    maxTokens: 256,
  },
  /** Balanced chat responses */
  chat: {
    temperature: 0.7,
    topP: 0.9,
    topK: 40,
    repetitionPenalty: 1.1,
    maxTokens: 1024,
  },
  /** Creative writing, brainstorming */
  creative: {
    temperature: 1.2,
    topP: 0.95,
    frequencyPenalty: 0.4,
    repetitionPenalty: 1.15,
    maxTokens: 2048,
  },
  /** Code generation */
  code: {
    temperature: 0.2,
    topP: 0.95,
    repetitionPenalty: 1.0,
    maxTokens: 1500,
  },
} satisfies Record<string, TextGenOptions>;
```

## Reproducible Outputs with `seed`

Setting `seed` to a fixed integer makes inference deterministic given identical inputs and parameters.
Useful for regression tests, content snapshots, and A/B experiments where you need the same baseline.

```typescript
// src/reproducible.ts
export async function reproducibleGenerate(
  ai: Ai,
  prompt: string,
  seed: number = 42
): Promise<string> {
  const result = await ai.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [{ role: "user", content: prompt }],
    temperature: 0.7,
    seed,
    max_tokens: 512,
  });

  return (result as { response?: string }).response ?? "";
}

// In tests:
// const a = await reproducibleGenerate(ai, "Tell me a joke", 42);
// const b = await reproducibleGenerate(ai, "Tell me a joke", 42);
// assert(a === b);  // true
```

## Repetition vs Frequency Penalty Trade-off

`repetition_penalty` (≥ 1.0) multiplies the logit of any already-seen token by 1/penalty, making
it less likely to recur. Good for preventing identical phrase loops.

`frequency_penalty` subtracts `penalty * count` from the logit proportionally to how many times
the token has already appeared. Good for ensuring diverse vocabulary throughout longer outputs.

Combine them carefully — stacking both at high values distorts the distribution aggressively.

```typescript
// For a summariser that tends to repeat topic phrases:
const summaryResult = await ai.run("@cf/meta/llama-3.1-8b-instruct", {
  messages: [
    { role: "system", content: "Summarise the following text in 3 sentences." },
    { role: "user", content: longDocument },
  ],
  temperature: 0.5,
  repetition_penalty: 1.2,  // moderate loop prevention
  frequency_penalty: 0.3,   // mild vocabulary diversity
  max_tokens: 300,
});
```

## Dynamic Parameter Selection at Runtime

Route to parameter presets based on request metadata rather than hard-coding per endpoint.

```typescript
// src/router.ts
import { INFERENCE_PRESETS } from "./presets";
import { generate } from "./inference";

type PresetKey = keyof typeof INFERENCE_PRESETS;

export async function routedGenerate(
  ai: Ai,
  request: Request
): Promise<Response> {
  const { message, preset = "chat" } = await request.json<{
    message: string;
    preset?: PresetKey;
  }>();

  const opts = INFERENCE_PRESETS[preset] ?? INFERENCE_PRESETS.chat;

  const text = await generate(
    ai,
    "@cf/meta/llama-3.1-8b-instruct",
    "You are a helpful assistant.",
    message,
    opts
  );

  return Response.json({ text, preset });
}
```

## Anti-patterns

- **Setting `temperature: 0` and `top_p: 0.9` together** — once temperature collapses the
  distribution to the greedy peak, top_p is moot. Use one nucleus strategy at a time.
- **`repetition_penalty > 1.5`** — aggressively penalises grammatically necessary repeated words
  ("the", "is") and produces garbled output.
- **`top_k: 1`** — equivalent to greedy decoding; ignores temperature entirely.
- **Assuming `seed` means bit-for-bit reproducibility across model upgrades** — when Cloudflare
  updates a model checkpoint the same seed will produce different output.
- **Using creative presets for JSON extraction** — high temperature causes malformed JSON. Always
  use deterministic presets with JSON-mode tasks.

## Gotchas

- Workers AI ignores unknown parameters silently. If you misspell `repetition_penalty` as
  `rep_penalty` the request succeeds but with the default value.
- `max_tokens` counts *output* tokens only. Input tokens still count against the model context
  window independently.
- Not all models support `frequency_penalty`; it is more widely implemented in OpenAI-compatible
  endpoints than in native Workers AI bindings.
- `seed` combined with `stream: true` may not guarantee identical token timing, only identical
  token sequence when the model processes the same request.

## Verification

```bash
# Call the binding with explicit seed twice and compare responses:
wrangler dev --local
curl -s -X POST http://localhost:8787/generate \
  -H "Content-Type: application/json" \
  -d '{"message":"Explain gravity in one sentence","preset":"deterministic"}' \
  | jq '.text'

# Repeat — output should be identical with deterministic preset + same seed.
```

## Related

- `workers-ai-json-schema-constrained-generation.md` — constraining output format beyond sampling
- `workers-ai-structured-output-parallel-tool-calls.md` — parallel tool calls with structured output
- `llm-temperature-sampling-decoding.md` — theory behind decoding strategies
- `workers-ai-pipeline-chaining-multi-model.md` — chaining models with different parameter profiles

## Sources

- Cloudflare Workers AI text generation input schema: https://developers.cloudflare.com/workers-ai/models/llama-3.1-8b-instruct/
- Workers AI model list and capabilities: https://developers.cloudflare.com/workers-ai/models/
- Hugging Face transformers generation config reference: https://huggingface.co/docs/transformers/main_classes/text_generation
