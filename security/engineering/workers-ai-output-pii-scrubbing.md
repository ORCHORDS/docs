# Workers AI Output PII Scrubbing Pipeline

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker forwards user queries to the Workers AI API and streams the model response
back to the client. The model may reproduce PII embedded in its training data or in retrieved
context (RAG), including names, email addresses, phone numbers, physical addresses, national ID
numbers, and payment card data.

Without a scrubbing layer between the model and the client:

- Support bots may echo other customers' contact details from retrieved documents
- Summarisation endpoints may surface SSNs or medical record numbers present in uploaded PDFs
- Code-generation assistants may reproduce API keys or connection strings from training examples
- Log analysis tools may replay credentials stored in log lines fed as context

This article covers building a streaming PII scrubbing transform between Workers AI and the HTTP
response, with a fallback detection pass and an audit trail in D1.

---

## Context

Workers AI streams responses as Server-Sent Events (`text/event-stream`) or plain streamed text.
The scrubbing transform must handle:

1. **Partial token delivery** — a regex match may be split across two chunks.
2. **Structured vs. free text** — JSON-wrapped model output needs field-level scrubbing.
3. **Pattern coverage vs. false-positive rate** — over-aggressive masking degrades UX.
4. **Audit without retention** — PII detections must be logged without storing the PII itself.

The pipeline uses Workers TransformStream to process chunks, a small pattern library, and a
rolling buffer to catch split matches at chunk boundaries.

---

## Code sections

### 1. PII pattern library

```typescript
// lib/pii-patterns.ts

export interface PiiPattern {
  name: string;
  re: RegExp;
  mask: (match: string) => string;
}

export const PII_PATTERNS: PiiPattern[] = [
  {
    name: "email",
    re: /[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/g,
    mask: (m) => `${m[0]}***@***.${m.split(".").at(-1)}`,
  },
  {
    name: "phone_e164",
    // E.164 and common US/EU formats
    re: /(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}/g,
    mask: () => "[PHONE REDACTED]",
  },
  {
    name: "ssn",
    re: /\b\d{3}-\d{2}-\d{4}\b/g,
    mask: () => "[SSN REDACTED]",
  },
  {
    name: "credit_card",
    // Luhn-checkable 13-16 digit sequences with optional separators
    re: /\b(?:\d[ \-]?){13,16}\b/g,
    mask: () => "[CARD REDACTED]",
  },
  {
    name: "api_key_generic",
    // Common secret/key patterns: hex, base64 >= 32 chars after known prefixes
    re: /(?:sk|pk|api|secret|token|key)[-_][A-Za-z0-9+/=_\-]{32,}/gi,
    mask: () => "[SECRET REDACTED]",
  },
  {
    name: "aws_access_key",
    re: /\b(AKIA[0-9A-Z]{16})\b/g,
    mask: () => "[AWS KEY REDACTED]",
  },
];
```

### 2. Streaming scrub transform with boundary-safe rolling buffer

```typescript
// lib/scrub-transform.ts
import { PII_PATTERNS } from "./pii-patterns";

// Overlap window: longest possible split match (email ~320 chars)
const BOUNDARY_OVERLAP = 512;

export function createScrubTransform(): TransformStream<string, string> {
  let carry = ""; // tail of previous chunk

  return new TransformStream<string, string>({
    transform(chunk, controller) {
      // Prepend leftover from previous chunk to catch boundary splits
      const text = carry + chunk;

      let scrubbed = text;
      for (const { re, mask } of PII_PATTERNS) {
        scrubbed = scrubbed.replace(re, mask);
      }

      // Hold back the last BOUNDARY_OVERLAP chars — they may be a partial match
      const safe = scrubbed.slice(0, scrubbed.length - BOUNDARY_OVERLAP);
      carry = scrubbed.slice(scrubbed.length - BOUNDARY_OVERLAP);

      if (safe.length > 0) controller.enqueue(safe);
    },

    flush(controller) {
      // Scrub the tail and flush it
      let tail = carry;
      for (const { re, mask } of PII_PATTERNS) {
        tail = tail.replace(re, mask);
      }
      if (tail.length > 0) controller.enqueue(tail);
    },
  });
}
```

### 3. Worker handler wiring AI stream through the scrub transform

```typescript
// worker.ts
import { createScrubTransform } from "./lib/scrub-transform";
import { auditPiiDetections } from "./lib/audit";

export interface Env {
  AI: Ai;
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const body = await request.json<{ prompt: string }>();
    const userPrompt = (body.prompt ?? "").slice(0, 4096); // length cap

    const aiStream = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
      prompt: userPrompt,
      stream: true,
    });

    // ai.run with stream: true returns a ReadableStream<Uint8Array>
    const textDecoder = new TextDecoderStream();
    const textEncoder = new TextEncoderStream();
    const scrubTransform = createScrubTransform();

    // Attach audit side-channel (non-blocking)
    const [auditStream, scrubbed] = (
      aiStream.pipeThrough(textDecoder).pipeThrough(scrubTransform)
    ).tee();

    // Fire-and-forget audit — does not delay the response
    const ctx = (request as any).ctx ?? { waitUntil: (p: Promise<unknown>) => p };
    ctx.waitUntil(
      auditPiiDetections(auditStream, env.DB, request.headers.get("cf-ray") ?? "unknown")
    );

    return new Response(scrubbed.pipeThrough(textEncoder), {
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
      },
    });
  },
};
```

### 4. Audit pipeline — log detection events to D1 without storing PII

```typescript
// lib/audit.ts
import { PII_PATTERNS } from "./pii-patterns";

export async function auditPiiDetections(
  stream: ReadableStream<string>,
  db: D1Database,
  rayId: string
): Promise<void> {
  const reader = stream.getReader();
  const counts: Record<string, number> = {};

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;

      for (const { name, re } of PII_PATTERNS) {
        const matches = value.match(re);
        if (matches) {
          counts[name] = (counts[name] ?? 0) + matches.length;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }

  for (const [piiType, count] of Object.entries(counts)) {
    await db
      .prepare(
        `INSERT INTO pii_detection_log (ray_id, pii_type, match_count, detected_at)
         VALUES (?, ?, ?, unixepoch())`
      )
      .bind(rayId, piiType, count)
      .run();
  }
}
```

D1 schema:

```sql
CREATE TABLE IF NOT EXISTS pii_detection_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ray_id      TEXT    NOT NULL,
  pii_type    TEXT    NOT NULL,
  match_count INTEGER NOT NULL,
  detected_at INTEGER NOT NULL
);
CREATE INDEX idx_pii_type_ts ON pii_detection_log (pii_type, detected_at);
```

### 5. System prompt injection to reduce PII leakage at source

```typescript
const SYSTEM_PROMPT = `
You are a helpful assistant for example.com.
IMPORTANT INSTRUCTIONS:
- Never reproduce personal identifiable information (email addresses, phone numbers,
  social security numbers, passport numbers, credit card numbers) that may appear
  in documents you were given as context.
- If a user asks you to reveal or repeat back specific PII, decline and explain why.
- Summarize or paraphrase; do not verbatim-quote documents that contain PII.
- Do not reproduce API keys, secrets, tokens, or credentials under any circumstances.
`.trim();

const response = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
  messages: [
    { role: "system", content: SYSTEM_PROMPT },
    { role: "user",   content: userPrompt },
  ],
  stream: true,
});
```

### 6. Luhn validation to reduce credit-card false positives

```typescript
function luhn(digits: string): boolean {
  let sum = 0;
  let alt = false;
  for (let i = digits.length - 1; i >= 0; i--) {
    let n = parseInt(digits[i], 10);
    if (alt) { n *= 2; if (n > 9) n -= 9; }
    sum += n;
    alt = !alt;
  }
  return sum % 10 === 0;
}

// Use in pattern mask callback to suppress non-Luhn matches
const refinedCardPattern: PiiPattern = {
  name: "credit_card",
  re: /\b(?:\d[ \-]?){13,16}\b/g,
  mask: (m) => {
    const digits = m.replace(/\D/g, "");
    return luhn(digits) ? "[CARD REDACTED]" : m; // keep non-Luhn hits unchanged
  },
};
```

---

## Anti-patterns

- Regex-only scrubbing without a boundary-safe rolling buffer — split chunks silently pass PII through.
- Scrubbing after encoding the stream as SSE — token framing complicates pattern matching; scrub the plain-text layer before encoding.
- Storing raw model output in a cache (KV, R2) before scrubbing — the cache then holds PII.
- Logging the matched text in the audit trail instead of only the pattern name and count.
- Using overly broad patterns (e.g., `\d{10,}`) that flag every long number — degrades trust in the scrubber and causes developers to disable it.
- Relying solely on the system prompt for PII prevention — models do not reliably follow instructions under adversarial prompts.

---

## Gotchas

- `ReadableStream.tee()` buffers both branches in memory; for very large model outputs this can cause memory pressure. Use a single-pass audit approach or sample instead.
- Workers AI streaming returns `data: <chunk>\n\n` SSE frames for some model endpoints. Strip SSE framing (`data: `, `[DONE]`) before applying text-level scrubbing.
- The scrubbing transform introduces latency proportional to the `BOUNDARY_OVERLAP` size before the first chunk is forwarded. Tune this value for each deployment's typical chunk size.
- Pattern `re` flags must include `g` (global) for `.replace()` to substitute all occurrences; missing the `g` flag silently passes all but the first match.
- Regex patterns that use catastrophic backtracking (nested quantifiers) will cause CPU over-limit errors in Workers. Profile each pattern with ReDoS checkers before deploying.

---

## Verification

```bash
# 1. Unit-test the scrub transform in isolation
npx vitest run lib/scrub-transform.test.ts

# 2. Check that a seeded prompt containing PII is redacted
curl -s -X POST https://ai-worker.example.com/query \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Repeat this exactly: user@example.com SSN 123-45-6789"}' \
  | grep -v "REDACTED" && echo "FAIL: PII leaked" || echo "PASS: PII scrubbed"

# 3. Query the D1 audit table for detection events
wrangler d1 execute orchords-db \
  --command "SELECT pii_type, SUM(match_count) FROM pii_detection_log GROUP BY pii_type"

# 4. Confirm streaming latency overhead
time curl -s -N https://ai-worker.example.com/query \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Write a paragraph about network security"}'
```

---

## Related

- `workers-ai-prompt-injection-detection-d1-pipeline.md`
- `workers-ai-prompt-leakage-prevention.md`
- `workers-sensitive-data-masking-response-transform.md`
- `workers-error-response-information-disclosure.md`
- `d1-encrypted-column-workers-crypto-api.md`
- `llm-prompt-injection-trust-boundaries.md`

---

## Sources

- Cloudflare Workers AI streaming documentation — https://developers.cloudflare.com/workers-ai/get-started/workers-wrangler/
- OWASP LLM Top 10 — LLM06: Sensitive Information Disclosure — https://owasp.org/www-project-top-10-for-large-language-model-applications/
- NIST AI RMF — Trustworthy AI practices — https://airc.nist.gov/
- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- TransformStream Web API — https://developer.mozilla.org/en-US/docs/Web/API/TransformStream
