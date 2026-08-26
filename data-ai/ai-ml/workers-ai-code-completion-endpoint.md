# Workers AI Code Completion Endpoint

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to add AI-powered code completion or generation to a developer tool, IDE extension, or internal platform without managing GPU infrastructure. Workers AI provides code-capable models at the edge, and you need a low-latency HTTP endpoint that accepts a code prefix (and optional suffix for fill-in-the-middle), streams the completion, and enforces language-specific constraints.

## Context

Workers AI hosts models such as `@cf/deepseek-ai/deepseek-coder-6.7b-base-awq` and `@cf/mistral/mistral-7b-instruct-v0.1` that handle code completion. For fill-in-the-middle (FIM) tasks, DeepSeek Coder supports the `<｜fim▁begin｜>`, `<｜fim▁hole｜>`, `<｜fim▁end｜>` special tokens. The endpoint streams tokens via Server-Sent Events so the IDE renders completions incrementally.

---

## Model Selection

```typescript
// models.ts
export const CODE_MODELS = {
  completion: "@cf/deepseek-ai/deepseek-coder-6.7b-base-awq",   // best for FIM / raw completion
  instruction: "@cf/mistral/mistral-7b-instruct-v0.1",           // better for "explain/refactor" tasks
  fast: "@cf/meta/llama-3.1-8b-instruct-fast"                    // lowest latency, decent code
} as const;

export type CodeModel = keyof typeof CODE_MODELS;
```

---

## Fill-in-the-Middle Prompt Construction

```typescript
// fim.ts
export function buildFIMPrompt(prefix: string, suffix: string): string {
  // DeepSeek Coder FIM format
  return `<｜fim▁begin｜>${prefix}<｜fim▁hole｜>${suffix}<｜fim▁end｜>`;
}

export function buildInstructionPrompt(
  language: string,
  context: string,
  instruction: string
): string {
  return `You are an expert ${language} programmer. Complete or refactor the following code as instructed.
Output ONLY the code, no markdown fences, no explanations.

### Code:
${context}

### Instruction:
${instruction}`;
}
```

---

## Streaming Completion Handler

```typescript
// completion.ts
import { CODE_MODELS } from "./models";
import { buildFIMPrompt, buildInstructionPrompt } from "./fim";

interface CompletionRequest {
  prefix: string;
  suffix?: string;
  language?: string;
  instruction?: string;
  maxTokens?: number;
  temperature?: number;
}

export async function handleCompletion(
  req: Request,
  ai: Ai,
  kv: KVNamespace
): Promise<Response> {
  const body = await req.json<CompletionRequest>();
  const {
    prefix,
    suffix = "",
    language = "typescript",
    instruction,
    maxTokens = 256,
    temperature = 0.1
  } = body;

  if (!prefix?.trim()) {
    return Response.json({ error: "prefix is required" }, { status: 400 });
  }

  // Rate-limit by IP using KV sliding window
  const ip = req.headers.get("CF-Connecting-IP") ?? "unknown";
  const allowed = await checkRateLimit(kv, `rl:code:${ip}`, 20, 60);
  if (!allowed) {
    return Response.json({ error: "Rate limit exceeded" }, { status: 429 });
  }

  const prompt = instruction
    ? buildInstructionPrompt(language, prefix, instruction)
    : buildFIMPrompt(prefix, suffix);

  const model = instruction ? CODE_MODELS.instruction : CODE_MODELS.completion;

  const aiStream = await ai.run(model, {
    prompt,
    max_tokens: Math.min(maxTokens, 512),
    temperature,
    stream: true
  }) as ReadableStream;

  return new Response(aiStream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "X-Model": model
    }
  });
}

async function checkRateLimit(
  kv: KVNamespace,
  key: string,
  limit: number,
  windowSec: number
): Promise<boolean> {
  const count = parseInt((await kv.get(key)) ?? "0", 10);
  if (count >= limit) return false;
  await kv.put(key, String(count + 1), { expirationTtl: windowSec });
  return true;
}
```

---

## Non-Streaming Completion with Stop Sequences

For simpler integrations that don't need SSE, return a single JSON object with stop sequences to prevent the model from continuing past a function boundary.

```typescript
// batch-completion.ts
export async function handleBatchCompletion(
  req: Request,
  ai: Ai
): Promise<Response> {
  const { prefix, language = "typescript", maxTokens = 200 } = await req.json<{
    prefix: string;
    language?: string;
    maxTokens?: number;
  }>();

  const STOP_SEQUENCES: Record<string, string[]> = {
    typescript: ["\nfunction ", "\nclass ", "\nexport ", "\n// ---"],
    python: ["\ndef ", "\nclass ", "\n# ---"],
    go: ["\nfunc ", "\ntype ", "\n// ---"]
  };

  const stops = STOP_SEQUENCES[language] ?? ["\n\n"];

  const result = await ai.run(CODE_MODELS.completion, {
    prompt: buildFIMPrompt(prefix, ""),
    max_tokens: maxTokens,
    temperature: 0.05,
    // stop: stops  // pass if model supports stop sequences
  }) as { response: string };

  // Client-side stop trimming as fallback
  let completion = result.response;
  for (const stop of stops) {
    const idx = completion.indexOf(stop);
    if (idx !== -1) completion = completion.slice(0, idx);
  }

  return Response.json({ completion, language, model: CODE_MODELS.completion });
}
```

---

## Worker Router

```typescript
// worker.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    if (req.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    switch (url.pathname) {
      case "/v1/completions/stream":
        return handleCompletion(req, env.AI, env.KV);

      case "/v1/completions":
        return handleBatchCompletion(req, env.AI);

      default:
        return new Response("Not Found", { status: 404 });
    }
  }
};
```

---

## IDE Extension Integration (VS Code)

```typescript
// vscode-extension snippet
const response = await fetch("https://your-worker.workers.dev/v1/completions/stream", {
  method: "POST",
  headers: { "Content-Type": "application/json", "Authorization": `Bearer ${apiKey}` },
  body: JSON.stringify({
    prefix: document.getText(new vscode.Range(new vscode.Position(0, 0), position)),
    suffix: document.getText(new vscode.Range(position, document.positionAt(document.getText().length))),
    language: document.languageId,
    maxTokens: 128
  })
});

const reader = response.body!.getReader();
// Decode SSE stream and insert tokens at cursor position
```

---

## Anti-patterns

- **No stop sequences** — code models will generate entire files; always trim at natural boundaries.
- **Returning raw FIM tokens to the client** — strip `<｜fim▁begin｜>` and similar tokens before sending the response.
- **Temperature > 0.3 for autocomplete** — higher temperatures introduce syntax errors; keep it low for completion, higher only for creative tasks.
- **Ignoring model context limits** — DeepSeek Coder 6.7B has a 4096-token context; truncate the prefix if needed.
- **No rate limiting** — code models are expensive per token; always gate per-user or per-IP.

## Gotchas

- Workers AI streaming uses a custom SSE format where each `data:` line is a JSON object `{ response: "token" }`, not raw text — parse accordingly.
- The `@cf/deepseek-ai/deepseek-coder-6.7b-base-awq` model is a base (not instruction-tuned) model; it does not follow chat-style prompts.
- FIM tokens must be exact Unicode characters — copy them from the DeepSeek Coder documentation rather than typing lookalikes.
- Workers AI does not currently support `n > 1` (multiple completions); implement sampling in your client if needed.
- Model availability varies by Cloudflare region; set `CF-Worker-AI-Model-Region: WNAM` in bindings for consistent routing if latency is critical.

## Verification

```bash
# Stream completion
curl -X POST https://your-worker.workers.dev/v1/completions/stream \
  -H "Content-Type: application/json" \
  -d '{"prefix":"function add(a: number, b: number): ","language":"typescript"}' \
  --no-buffer

# Batch completion
curl -X POST https://your-worker.workers.dev/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"prefix":"def fibonacci(n):\n    ","language":"python","maxTokens":100}'
```

## Related

- `cloudflare-workers-ai-streaming-inference.md`
- `workers-ai-structured-output-parallel-tool-calls.md`
- `workers-ai-inference-parameter-tuning.md`
- `workers-ai-streaming-server-sent-events.md`
- `llm-for-code-generation.md`

## Sources

- Workers AI text generation: https://developers.cloudflare.com/workers-ai/models/text-generation/
- DeepSeek Coder model: https://huggingface.co/deepseek-ai/deepseek-coder-6.7b-base
- Workers AI streaming: https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/
