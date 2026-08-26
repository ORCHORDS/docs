# Workers AI Structured Output Regex Constraint

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Workers AI LLM call must return a value in an exact surface form — an ISO 8601 date,
a currency code, a UUID, a fixed enum member — but free-text generation occasionally
returns near-miss values that break downstream parsers (`"2024/01/15"` instead of
`"2024-01-15"`, `"usd"` instead of `"USD"`). JSON Schema mode constrains shape but not
string format. You need output that is provably conformant to a regular expression before
it ever leaves the Worker.

---

## Context

Two layers of enforcement exist in a Workers AI text pipeline:

1. **Model-side constrained decoding** — the model's token sampler is guided by an allowed
   token set derived from a grammar or regex. Workers AI exposes this through the
   `response_format` field on supported models (grammar-based JSON schema). For tighter
   regex constraints beyond JSON Schema, you pass a CFG (context-free grammar) string in
   GBNF notation to models that accept `grammar`.

2. **Post-generation validation and retry** — parse the model's output against a regex;
   on failure, retry with a clarifying prompt up to a configured limit. This works with
   any model regardless of grammar support.

This article covers both approaches and how to combine them.

---

## Approach A: GBNF Grammar Constraint (Model-Side)

Some Workers AI models (llama-family via llama.cpp backend) accept a `grammar` parameter
in GBNF notation. A grammar that only allows a date string:

```
root   ::= date
date   ::= [0-9] [0-9] [0-9] [0-9] "-" month "-" day
month  ::= ("0" [1-9]) | ("1" [0-2])
day    ::= ("0" [1-9]) | ([1-2] [0-9]) | ("3" [0-1])
```

```typescript
// grammar-date.ts
const DATE_GRAMMAR = `
root   ::= date
date   ::= [0-9] [0-9] [0-9] [0-9] "-" month "-" day
month  ::= ("0" [1-9]) | ("1" [0-2])
day    ::= ("0" [1-9]) | ([1-2] [0-9]) | ("3" [0-1])
`.trim();

export async function extractDate(ai: Ai, text: string): Promise<string> {
  const result = await (ai as any).run('@cf/meta/llama-3.1-8b-instruct', {
    messages: [
      {
        role: 'user',
        content: `Extract the date mentioned in the text below as YYYY-MM-DD.
Return the date only, nothing else.

Text: ${text}`,
      },
    ],
    grammar: DATE_GRAMMAR,
    max_tokens: 12,
  });

  return result.response?.trim() ?? '';
}
```

**Caveat**: grammar support availability varies by model version. Always check
`response?.trim()` against the regex client-side even when grammar is applied — a malformed
grammar silently disables constraint on some backends.

---

## Approach B: Post-Generation Validation with Retry

When grammar parameters are unavailable or insufficient, validate output client-side and
retry with a repair prompt.

```typescript
// regex-validate.ts
export interface RegexConstraint {
  pattern: RegExp;
  description: string;  // human-readable, used in repair prompt
  maxRetries?: number;
}

export async function runWithRegexConstraint(
  ai: Ai,
  messages: Array<{ role: string; content: string }>,
  constraint: RegexConstraint
): Promise<{ value: string; attempts: number }> {
  const maxRetries = constraint.maxRetries ?? 3;
  let attempt = 0;
  let conversationMessages = [...messages];

  while (attempt < maxRetries) {
    attempt++;

    const result = await ai.run('@cf/meta/llama-3.1-8b-instruct', {
      messages: conversationMessages as any,
      max_tokens: 128,
      temperature: attempt > 1 ? 0.0 : 0.2,  // go greedy on retries
    });

    const raw = (result as any).response?.trim() ?? '';

    // Extract only the part that matches the regex (first match)
    const match = raw.match(constraint.pattern);
    if (match) {
      return { value: match[0], attempts: attempt };
    }

    // Repair prompt: append assistant output and correction request
    conversationMessages = [
      ...conversationMessages,
      { role: 'assistant', content: raw },
      {
        role: 'user',
        content:
          `That response does not match the required format: ${constraint.description}. ` +
          `Please respond with ONLY the value in the correct format, nothing else.`,
      },
    ];
  }

  throw new Error(
    `Output did not match ${constraint.pattern} after ${maxRetries} attempts`
  );
}
```

---

## Predefined Constraint Library

```typescript
// constraints.ts
export const Constraints = {
  isoDate: {
    pattern: /\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])/,
    description: 'ISO 8601 date: YYYY-MM-DD',
    maxRetries: 3,
  },

  currencyCode: {
    pattern: /\b[A-Z]{3}\b/,
    description: 'ISO 4217 currency code: three uppercase letters (e.g. USD, EUR, GBP)',
    maxRetries: 2,
  },

  uuid: {
    pattern: /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i,
    description: 'UUID v4 format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx',
    maxRetries: 2,
  },

  semver: {
    pattern: /\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?/,
    description: 'Semantic version: MAJOR.MINOR.PATCH',
    maxRetries: 3,
  },

  yesNo: {
    pattern: /\b(yes|no)\b/i,
    description: 'Single word: yes or no',
    maxRetries: 2,
  },
} as const;
```

---

## Combined Approach: Schema + Regex Co-validation

Use JSON Schema mode to get structured output, then regex-validate individual string
fields within it.

```typescript
// structured-extract.ts
import { runWithRegexConstraint, Constraints } from './constraints';

export interface InvoiceFields {
  date: string;
  currency: string;
  total: string;
}

export async function extractInvoiceFields(
  ai: Ai,
  invoiceText: string
): Promise<InvoiceFields> {
  const { value: date } = await runWithRegexConstraint(
    ai,
    [
      { role: 'system', content: 'You extract structured data from invoices.' },
      {
        role: 'user',
        content: `Extract the invoice date as YYYY-MM-DD.\n\nInvoice:\n${invoiceText}`,
      },
    ],
    Constraints.isoDate
  );

  const { value: currency } = await runWithRegexConstraint(
    ai,
    [
      { role: 'system', content: 'You extract structured data from invoices.' },
      {
        role: 'user',
        content: `Extract the currency code (e.g. USD, EUR).\n\nInvoice:\n${invoiceText}`,
      },
    ],
    Constraints.currencyCode
  );

  // total is a number field — use JSON schema mode
  const totalResult = await ai.run('@cf/meta/llama-3.1-8b-instruct', {
    messages: [
      { role: 'system', content: 'You extract structured data. Respond with JSON only.' },
      { role: 'user', content: `Extract the total amount as a number.\n\nInvoice:\n${invoiceText}` },
    ],
    response_format: {
      type: 'json_schema',
      json_schema: {
        name: 'total',
        schema: { type: 'object', properties: { total: { type: 'number' } }, required: ['total'] },
      },
    },
  } as any);

  const { total } = JSON.parse((totalResult as any).response ?? '{}');

  return { date, currency, total: String(total) };
}
```

---

## Anti-patterns

- **Trusting the model's output directly on first attempt** — even with grammar constraints,
  always validate in application code; treat the constraint as a probabilistic guide, not
  a hard guarantee.
- **Retrying with identical messages** — the model will likely reproduce the same error.
  Change temperature to 0 and append a repair prompt that names the failure.
- **Using overly broad patterns to reduce retries** — a pattern of `/.+/` always matches;
  the constraint must match only valid values.
- **Running sequential field extractions** — when extracting multiple constrained fields from
  the same document, use `Promise.all` across independent constraints to avoid serial
  latency stacking.

---

## Gotchas

- GBNF grammar support is model-backend-dependent. At the time of writing, it is available
  on llama.cpp-backed models; confirm support via the Workers AI model catalogue before
  relying on it in production.
- Regex `match()` returns the first match in the string, not the whole string. Wrap with
  `^...$` anchors if you need a whole-string match, or use `match()?.[0] === raw` to
  confirm no surrounding text was generated.
- Retries consume additional AI Gateway tokens and incur extra cost; set `maxRetries` ≤ 3
  and alert if the retry rate exceeds ~5% of requests in production.
- `temperature: 0` is not available on all Workers AI models; some clamp to a minimum of
  `0.01`. Check model docs before assuming deterministic output on retry.

---

## Verification

1. Send a prompt known to produce a non-conformant date string with `runWithRegexConstraint`
   using `Constraints.isoDate`; confirm the retry loop fires and the returned value matches
   the pattern.
2. Force `maxRetries: 1` and confirm the function throws rather than returning a bad value.
3. Pass a valid ISO date as the model output on the first attempt; confirm `attempts === 1`
   in the return value.
4. Benchmark: measure p99 latency for the retry path vs. the single-attempt path; confirm
   retries fall within acceptable SLA headroom.

---

## Related

- `workers-ai-json-schema-constrained-generation.md`
- `llm-structured-extraction-zod-workers.md`
- `llm-structured-output-json-mode.md`
- `llm-output-parsing.md`
- `workers-ai-entity-extraction-structured-output-d1.md`

---

## Sources

- Cloudflare Workers AI structured outputs: https://developers.cloudflare.com/workers-ai/features/structured-outputs/
- GBNF grammar notation (llama.cpp): https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md
- Cloudflare Workers AI models: https://developers.cloudflare.com/workers-ai/models/
