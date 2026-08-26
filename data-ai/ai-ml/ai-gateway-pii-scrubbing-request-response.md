# AI Gateway PII Scrubbing for Request and Response Pipelines

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
User prompts routed through AI Gateway can contain names, email addresses, phone numbers, SSNs, and other PII that must never reach a third-party LLM provider or be stored in AI Gateway logs. Responses from providers may also echo PII back in generated text that must be redacted before delivery to the client.

## Context
Cloudflare AI Gateway does not offer native PII redaction as of mid-2026. The recommended pattern is a Worker that sits in front of AI Gateway: it scrubs the outbound request body, forwards the sanitised prompt to AI Gateway, then scrubs the response before returning it to the caller. A KV store maps placeholder tokens (e.g. `[EMAIL_1]`) to original values so they can optionally be re-hydrated for internal audit trails stored in R2, never in logs.

## PII Detection Utilities

```typescript
// pii-patterns.ts
export interface PiiMatch {
  type: string;
  value: string;
  placeholder: string;
}

const PATTERNS: Array<{ type: string; re: RegExp }> = [
  { type: 'EMAIL',   re: /\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b/g },
  { type: 'PHONE',   re: /\b(\+?1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}\b/g },
  { type: 'SSN',     re: /\b(?!000|666|9\d{2})\d{3}[- ](?!00)\d{2}[- ](?!0000)\d{4}\b/g },
  { type: 'CARD',    re: /\b(?:4\d{12}(?:\d{3})?|5[1-5]\d{14}|3[47]\d{13}|6011\d{12})\b/g },
  { type: 'IP',      re: /\b(?:\d{1,3}\.){3}\d{1,3}\b/g },
  // Simple name pattern — augment with Workers AI NER for higher recall
  { type: 'NAME',    re: /\b([A-Z][a-z]+ [A-Z][a-z]+)\b/g },
];

export function scrub(text: string): { scrubbed: string; matches: PiiMatch[] } {
  const matches: PiiMatch[] = [];
  const counters: Record<string, number> = {};
  let scrubbed = text;

  for (const { type, re } of PATTERNS) {
    re.lastIndex = 0;
    scrubbed = scrubbed.replace(re, value => {
      counters[type] = (counters[type] ?? 0) + 1;
      const placeholder = `[${type}_${counters[type]}]`;
      matches.push({ type, value, placeholder });
      return placeholder;
    });
  }
  return { scrubbed, matches };
}

export function rehydrate(text: string, matches: PiiMatch[]): string {
  let result = text;
  for (const { placeholder, value } of matches) {
    result = result.replaceAll(placeholder, value);
  }
  return result;
}
```

## Worker: Scrub → Gateway → Scrub Pipeline

```typescript
// pii-gateway-worker.ts
import type { KVNamespace, R2Bucket } from '@cloudflare/workers-types';
import { scrub, rehydrate, type PiiMatch } from './pii-patterns';

interface Env {
  AI_GATEWAY_URL: string;   // e.g. https://gateway.ai.cloudflare.com/v1/<acct>/<gw>/openai
  AI_GATEWAY_TOKEN: string; // bearer token or CF AI Gateway API key
  PII_MAP: KVNamespace;     // stores requestId -> serialised PiiMatch[] (TTL 1h)
  AUDIT_BUCKET: R2Bucket;   // stores original + scrubbed pairs for compliance
}

interface ChatMessage {
  role: string;
  content: string;
}

interface ChatRequest {
  messages: ChatMessage[];
  model?: string;
  stream?: boolean;

}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const requestId = crypto.randomUUID();
    const body = (await req.json()) as ChatRequest;

    // --- 1. Scrub request messages ---
    const allMatches: PiiMatch[] = [];
    const scrubbedMessages = body.messages.map(msg => {
      if (typeof msg.content !== 'string') return msg;
      const { scrubbed, matches } = scrub(msg.content);
      allMatches.push(...matches);
      return { ...msg, content: scrubbed };
    });

    // Persist mapping for optional re-hydration (TTL 3600 s)
    if (allMatches.length > 0) {
      await env.PII_MAP.put(
        requestId,
        JSON.stringify(allMatches),
        { expirationTtl: 3600 },
      );
    }

    const sanitisedBody: ChatRequest = { ...body, messages: scrubbedMessages };

    // --- 2. Forward to AI Gateway ---
    const gwResp = await fetch(env.AI_GATEWAY_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${env.AI_GATEWAY_TOKEN}`,
        'cf-aig-request-id': requestId,
      },
      body: JSON.stringify(sanitisedBody),
    });

    if (!gwResp.ok) {
      return new Response(await gwResp.text(), { status: gwResp.status });
    }

    // --- 3. Scrub response (non-streaming path) ---
    const gwJson = await gwResp.json() as {
      choices?: Array<{ message?: { content?: string } }>;
    };

    const responseText =
      gwJson?.choices?.[0]?.message?.content ?? '';
    const { scrubbed: scrubbedResponse, matches: respMatches } = scrub(responseText);

    // Audit: write original + scrubbed to R2 (async, non-blocking)
    void writeAuditLog(env.AUDIT_BUCKET, requestId, {
      originalMessages: body.messages,
      scrubbedMessages,
      responseOriginal: responseText,
      responseScrubbedAdditional: respMatches,
    });

    // Return scrubbed response to caller
    const responseBody = {
      ...gwJson,
      choices: gwJson.choices?.map((c, i) =>
        i === 0
          ? { ...c, message: { ...c.message, content: scrubbedResponse } }
          : c,
      ),
      _pii: {
        requestId,
        requestRedactions: allMatches.length,
        responseRedactions: respMatches.length,
      },
    };

    return Response.json(responseBody);
  },
} satisfies ExportedHandler<Env>;

async function writeAuditLog(bucket: R2Bucket, id: string, data: unknown) {
  try {
    await bucket.put(
      `pii-audit/${new Date().toISOString().slice(0, 10)}/${id}.json`,
      JSON.stringify(data),
      { httpMetadata: { contentType: 'application/json' } },
    );
  } catch {
    // Audit failure must not affect the user response
  }
}
```

## Streaming Response Scrubbing

For streaming completions (`stream: true`), scrub each delta chunk on the fly:

```typescript
// streaming-scrub.ts
import { scrub } from './pii-patterns';

export function createScrubbingStream(
  upstream: ReadableStream<Uint8Array>,
): ReadableStream<Uint8Array> {
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();

  return new ReadableStream({
    async start(controller) {
      const reader = upstream.getReader();
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) { controller.close(); break; }

          const chunk = decoder.decode(value, { stream: true });
          // SSE format: "data: {...}\n\n"
          const cleaned = chunk.replace(/"content":"([^"]*)"/g, (_, content) => {
            const { scrubbed } = scrub(content);
            return `"content":"${scrubbed}"`;
          });
          controller.enqueue(encoder.encode(cleaned));
        }
      } catch (e) {
        controller.error(e);
      }
    },
  });
}
```

## NER-Augmented Name Detection with Workers AI

Regex-based name detection has high false-positive rates. Use Workers AI text classification to validate candidates:

```typescript
// ner-pii.ts
import type { Ai } from '@cloudflare/workers-types';

export async function validateNameCandidates(
  ai: Ai,
  candidates: string[],
): Promise<Set<string>> {
  if (candidates.length === 0) return new Set();

  // Use zero-shot classification to confirm each candidate is a person name
  const confirmed = new Set<string>();
  for (const name of candidates) {
    const result = await ai.run('@cf/facebook/bart-large-mnli', {
      text: `"${name}" is a person's full name`,
      candidate_labels: ['person name', 'organisation', 'place', 'other'],
    });
    // @ts-expect-error — runtime shape
    if (result.labels?.[0] === 'person name' && result.scores?.[0] > 0.75) {
      confirmed.add(name);
    }
  }
  return confirmed;
}
```

## Anti-patterns

- **Logging the original prompt anywhere after scrubbing** — if the original prompt is written to Workers logs or AI Gateway logs before scrubbing, PII is already exposed; scrub first, then forward.
- **Using PII placeholders that appear in real text** — tokens like `[NAME]` can clash with markdown formatting; use UUID-suffixed tokens or format `[NAME_abc123]`.
- **Re-hydrating PII into the final user response** — re-hydration is only for internal audit trails; callers should receive the scrubbed response.
- **Skipping stream scrubbing** — SSE deltas are raw strings and must be scrubbed per chunk; not scrubbing streaming responses is a common leak vector.
- **Relying solely on regex** — regex misses context-dependent PII (initials, codenames); combine with a Workers AI NER pass for higher recall.

## Gotchas

- AI Gateway logs (`cf-aig-request-id` tagged) store the request body AI Gateway sees — ensure you forward the *scrubbed* body, not the original.
- KV write latency (10–50 ms) is in the hot path; only write the mapping when `allMatches.length > 0`.
- The `R2Bucket.put` for audit must be fire-and-forget (`void`) — awaiting it adds 50–200 ms to every response.
- Chunked SSE scrubbing can break multi-byte characters at chunk boundaries; use `TextDecoder` with `{ stream: true }` to handle correctly.
- GDPR/CCPA require audit logs themselves to be encrypted at rest; use R2 bucket-level SSE (enabled by default) and restrict access via R2 bucket policies.

## Verification

```bash
# Send a prompt with PII
curl -X POST https://<worker>/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role":"user","content":"My name is John Smith and email is john@example.com"}]
  }'

# Expect response _pii.requestRedactions >= 2
# Check AI Gateway log — prompt should show [NAME_1] [EMAIL_1]
# Check R2 bucket pii-audit/<date>/<requestId>.json for full audit trail
```

## Related

- `pii-detection-redaction.md`
- `ai-gateway-request-transformation-middleware.md`
- `ai-gateway-logging.md`
- `ai-gateway-request-deduplication-idempotency.md`
- `llm-context-poisoning-detection-workers.md`

## Sources

- https://developers.cloudflare.com/ai-gateway/
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/r2/
