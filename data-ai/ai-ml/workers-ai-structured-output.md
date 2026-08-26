# Workers AI — Structured JSON Output from LLMs

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need an LLM to return machine-readable JSON instead of free-form prose — extracting entities from a support ticket, returning a typed decision object, or filling a form schema from unstructured text. Parsing free-form LLM output with regex is fragile; schema-guided generation with validation and retry gives you reliable structured data.

---

## Context

Cloudflare Workers AI exposes a `response_format` parameter (JSON mode) on compatible models such as `@cf/meta/llama-3.1-8b-instruct` and `@cf/mistral/mistral-7b-instruct-v0.1`. Combined with a Zod schema on the Worker side, you can enforce structure, validate the response, and automatically retry on parse failure — all inside a single Worker request with no external services.

Supported models for `response_format: { type: 'json_object' }` as of mid-2026:
- `@cf/meta/llama-3.1-8b-instruct`
- `@cf/meta/llama-3.3-70b-instruct-fp8-fast`
- `@cf/mistral/mistral-7b-instruct-v0.2`

---

## Solution

```typescript
import { z } from 'zod';

export interface Env {
  AI: Ai;
}

// ── 1. Define your target schema with Zod ────────────────────────────────────

const SupportTicketSchema = z.object({
  category: z.enum(['billing', 'technical', 'account', 'general']),
  priority: z.enum(['low', 'medium', 'high', 'critical']),
  summary: z.string().min(1).max(200),
  sentiment: z.enum(['positive', 'neutral', 'negative']),
  entities: z.object({
    product: z.string().nullable(),
    orderId: z.string().nullable(),
    errorCode: z.string().nullable(),
  }),
  suggestedAction: z.string(),
});

type SupportTicket = z.infer<typeof SupportTicketSchema>;

// ── 2. Build the system prompt with JSON schema instructions ─────────────────

function buildSystemPrompt(): string {
  return `You are a support ticket classifier. Analyze the user message and return ONLY valid JSON.

The JSON object MUST match this exact schema:
{
  "category": "billing" | "technical" | "account" | "general",
  "priority": "low" | "medium" | "high" | "critical",
  "summary": "string (max 200 chars)",
  "sentiment": "positive" | "neutral" | "negative",
  "entities": {
    "product": "string or null",
    "orderId": "string or null",
    "errorCode": "string or null"
  },
  "suggestedAction": "string"
}

Return ONLY the JSON object. No markdown, no explanation, no code fences.`;
}

// ── 3. Few-shot examples for consistent structure ────────────────────────────

const FEW_SHOT_EXAMPLES = [
  {
    role: 'user' as const,
    content: 'I was charged twice for order #ORD-9921 last Tuesday.',
  },
  {
    role: 'assistant' as const,
    content: JSON.stringify({
      category: 'billing',
      priority: 'high',
      summary: 'Customer reports duplicate charge for order #ORD-9921.',
      sentiment: 'negative',
      entities: { product: null, orderId: 'ORD-9921', errorCode: null },
      suggestedAction: 'Investigate payment processor logs and initiate refund if confirmed.',
    }),
  },
];

// ── 4. LLM call with JSON mode ───────────────────────────────────────────────

async function extractStructuredData(
  ai: Ai,
  rawText: string,
  attempt: number = 1,
): Promise<SupportTicket> {
  const MAX_ATTEMPTS = 3;

  const messages: RoleScopedChatInput[] = [
    { role: 'system', content: buildSystemPrompt() },
    ...FEW_SHOT_EXAMPLES,
    { role: 'user', content: rawText },
  ];

  // On retry, add a corrective turn
  if (attempt > 1) {
    messages.push({
      role: 'user',
      content:
        'Your previous response was not valid JSON. Return ONLY a raw JSON object, nothing else.',
    });
  }

  const response = await ai.run('@cf/meta/llama-3.1-8b-instruct', {
    messages,
    response_format: { type: 'json_object' },
    max_tokens: 512,
    temperature: 0.1, // low temperature for deterministic structure
  });

  const rawJson = (response as { response: string }).response.trim();

  // Strip accidental markdown fences if model ignores instructions
  const cleaned = rawJson.replace(/^```(?:json)?\n?/, '').replace(/\n?```$/, '');

  let parsed: unknown;
  try {
    parsed = JSON.parse(cleaned);
  } catch (err) {
    if (attempt >= MAX_ATTEMPTS) {
      throw new Error(`JSON parse failed after ${MAX_ATTEMPTS} attempts: ${String(err)}`);
    }
    console.warn(`Attempt ${attempt}: invalid JSON, retrying.`, cleaned.slice(0, 200));
    return extractStructuredData(ai, rawText, attempt + 1);
  }

  // ── 5. Validate against Zod schema ──────────────────────────────────────
  const result = SupportTicketSchema.safeParse(parsed);
  if (!result.success) {
    if (attempt >= MAX_ATTEMPTS) {
      throw new Error(
        `Schema validation failed after ${MAX_ATTEMPTS} attempts: ${
          result.error.message
        }`,
      );
    }
    console.warn(
      `Attempt ${attempt}: schema mismatch, retrying.`,
      result.error.flatten(),
    );
    return extractStructuredData(ai, rawText, attempt + 1);
  }

  return result.data;
}

// ── 6. Worker entry point ────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405 });
    }

    let body: { text?: string };
    try {
      body = await request.json();
    } catch {
      return new Response('Invalid JSON body', { status: 400 });
    }

    if (!body.text || typeof body.text !== 'string') {
      return new Response('Missing field: text', { status: 400 });
    }

    if (body.text.length > 4000) {
      return new Response('text exceeds 4000 characters', { status: 413 });
    }

    try {
      const structured = await extractStructuredData(env.AI, body.text);
      return Response.json({ ok: true, data: structured });
    } catch (err) {
      console.error('Structured extraction error:', err);
      return Response.json(
        { ok: false, error: String(err) },
        { status: 500 },
      );
    }
  },
} satisfies ExportedHandler<Env>;
```

---

## Implementation Details

**JSON mode activation** — Pass `response_format: { type: 'json_object' }` in the `ai.run` call. The model is constrained at the token-sampling level to produce valid JSON; it cannot emit tokens outside the JSON grammar. This does not guarantee the object matches your application schema, only that it is parseable JSON.

**System prompt schema description** — Include a human-readable description of expected fields directly in the system prompt. Models follow inline schema descriptions more reliably than abstract schema language. Repeat enum values verbatim; do not use shorthand like `"low/medium/high"`.

**Few-shot examples** — Two well-formed examples (one per common category) dramatically improve consistency. Keep them in the `messages` array as `user`/`assistant` pairs before the real user message.

**Temperature** — Use `temperature: 0.1` or lower for structured extraction. High temperature increases creative but schema-breaking variation.

**Retry loop** — Parse failures and Zod validation failures both trigger a retry with an additional corrective instruction turn. Three attempts covers the vast majority of transient failures.

**Zod over manual checks** — `safeParse` returns a discriminated union; use `result.success` to branch. The `.flatten()` method on `result.error` gives field-level error messages suitable for logging.

---

## Anti-patterns

- **Returning raw LLM text to the client** — Always validate through Zod before returning. An un-validated response can contain extra narrative text around the JSON.
- **Using high `max_tokens`** — Cap at 512–1024 for extraction tasks. Uncapped tokens allow the model to add explanatory prose after the closing brace.
- **Parsing with `eval()`** — Never. Use `JSON.parse()` inside try/catch.
- **Asking for JSON in the user message only** — The system prompt is the authoritative instruction layer; move schema descriptions there.
- **Omitting nullable fields from the schema description** — If the prompt says nothing about optional fields, the model may omit them entirely, causing validation failures.

---

## Gotchas

- `response_format` is silently ignored by models that do not support it; always test against the target model.
- Very long input text can crowd out the JSON schema instructions in the context window. Chunk long documents and extract per-chunk, then merge.
- `@cf/meta/llama-3.1-8b-instruct` occasionally wraps the JSON in a markdown fence despite explicit instructions; the `cleaned` strip step in the solution handles this.
- Zod `.enum()` is case-sensitive. Normalize model output with `.toLowerCase()` before parsing if the model sometimes returns `"Billing"` instead of `"billing"`.
- Workers AI billing counts input + output tokens; few-shot examples add to input token cost on every call.

---

## Verification

```bash
# 1. Deploy
npx wrangler deploy

# 2. Test happy path
curl -X POST https://your-worker.workers.dev \
  -H 'Content-Type: application/json' \
  -d '{"text": "My Pro plan renewal failed with error E4023 and I cannot access my dashboard."}'
# Expected: { ok: true, data: { category: "technical", priority: "high", ... } }

# 3. Confirm schema enforcement
curl -X POST https://your-worker.workers.dev \
  -H 'Content-Type: application/json' \
  -d '{"text": "hello"}'
# Expect valid JSON response with all required Zod fields present

# 4. Local unit test
npx vitest run --reporter verbose
```

```typescript
// src/__tests__/structured.test.ts
import { describe, it, expect, vi } from 'vitest';
import { unstable_dev } from 'wrangler';

describe('structured output', () => {
  it('returns valid schema for a billing complaint', async () => {
    const worker = await unstable_dev('src/index.ts', { experimental: { disableExperimentalWarning: true } });
    const res = await worker.fetch('/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: 'You charged me twice for order ORD-001.' }),
    });
    const json = await res.json() as { ok: boolean; data: { category: string } };
    expect(json.ok).toBe(true);
    expect(json.data.category).toBe('billing');
    await worker.stop();
  });
});
```

---

## Related

- `documentation/categories/ai-ml/workers-ai-function-calling-tool-use.md` — tool-use as an alternative structured-output pattern
- `documentation/categories/ai-ml/workers-ai-rag-pipeline.md` — structured output used to format retrieved context
- `documentation/categories/ai-ml/workers-ai-content-moderation.md` — classification output validated with same Zod pattern
- [Cloudflare Workers AI — Text Generation](https://developers.cloudflare.com/workers-ai/models/text-generation/)
- [Zod documentation](https://zod.dev/)

---

## Sources

- Cloudflare Workers AI model catalog, August 2026
- Cloudflare Workers AI `response_format` parameter documentation
- Zod v3 API reference
- Internal example.com extraction service, production since 2025-Q3
