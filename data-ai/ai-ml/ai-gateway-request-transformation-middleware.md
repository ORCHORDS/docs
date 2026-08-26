# AI Gateway Request Transformation Middleware

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
You need to enforce system prompts, sanitize user inputs, strip PII from responses, and add per-request cost metadata before and after every LLM call — without duplicating this logic across every calling service.

## Context
Cloudflare AI Gateway sits between your Workers and upstream LLM providers. Workers can call the gateway endpoint directly using a `gateway` binding (available in 2025+) or by constructing the gateway URL manually. By placing a thin Worker in front of the gateway, you can intercept, transform, and enrich every request and response in a single place without touching application code. This middleware pattern also centralises audit logging, prompt versioning, and PII redaction.

## Injecting Mandatory System Prompts

Downstream callers often omit or override the system prompt. The middleware layer intercepts the request body and prepends or replaces the system message before forwarding to AI Gateway.

```typescript
// src/middleware/system-prompt-injector.ts
interface Env {
  AI_GATEWAY_ENDPOINT: string; // https://gateway.ai.cloudflare.com/v1/{account}/{gateway}/openai
  GATEWAY_TOKEN: string;
  SYSTEM_PROMPTS: KVNamespace; // keyed by customer_id or "default"
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const customerId = request.headers.get('X-Customer-Id') ?? 'default';
    const body = await request.json<{ messages: { role: string; content: string }[]; model: string; [k: string]: unknown }>();

    // Fetch tenant-specific system prompt from KV, fallback to default
    const systemPrompt =
      (await env.SYSTEM_PROMPTS.get(`system:${customerId}`)) ??
      (await env.SYSTEM_PROMPTS.get('system:default')) ??
      'You are a helpful assistant.';

    // Replace any existing system message with the enforced one
    const messages = [
      { role: 'system', content: systemPrompt },
      ...body.messages.filter((m) => m.role !== 'system'),
    ];

    const upstream = await fetch(`${env.AI_GATEWAY_ENDPOINT}/chat/completions`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.GATEWAY_TOKEN}`,
        'Content-Type': 'application/json',
        'cf-aig-customer-id': customerId,
      },
      body: JSON.stringify({ ...body, messages }),
    });

    return upstream;
  },
};
```

## Sanitizing Inputs Before Forwarding

Strip personally identifiable information from user messages before they reach the LLM provider's servers, using regex or a dedicated PII classifier running on Workers AI.

```typescript
// src/middleware/pii-sanitizer.ts
const PII_PATTERNS: [RegExp, string][] = [
  [/\b\d{3}-\d{2}-\d{4}\b/g, '[SSN]'],
  [/\b[A-Z]{1,2}\d{6,9}\b/g, '[PASSPORT]'],
  [/\b\d{13,19}\b/g, '[CARD]'],
  [/\b[\w.+-]+@[\w-]+\.[a-z]{2,}\b/gi, '[EMAIL]'],
  [/\b\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b/g, '[PHONE]'],
];

export function sanitizeMessage(text: string): { sanitized: string; redactions: number } {
  let sanitized = text;
  let redactions = 0;
  for (const [pattern, replacement] of PII_PATTERNS) {
    const before = sanitized;
    sanitized = sanitized.replace(pattern, replacement);
    if (sanitized !== before) redactions++;
  }
  return { sanitized, redactions };
}

export function sanitizeMessages(
  messages: { role: string; content: string }[]
): { messages: { role: string; content: string }[]; totalRedactions: number } {
  let totalRedactions = 0;
  const sanitized = messages.map((m) => {
    if (m.role !== 'user') return m;
    const { sanitized: content, redactions } = sanitizeMessage(m.content);
    totalRedactions += redactions;
    return { ...m, content };
  });
  return { messages: sanitized, totalRedactions };
}
```

## Attaching Cost and Routing Metadata

AI Gateway accepts custom metadata headers (`cf-aig-*`) that appear in Gateway logs. Use these to attribute costs to teams, features, and experiments.

```typescript
// src/middleware/metadata-enricher.ts
interface RequestMetadata {
  customerId: string;
  featureId: string;
  sessionId: string;
  modelTier: 'fast' | 'quality';
}

function buildGatewayHeaders(meta: RequestMetadata, incomingHeaders: Headers): Headers {
  const out = new Headers(incomingHeaders);
  out.set('cf-aig-customer-id', meta.customerId);
  out.set('cf-aig-metadata', JSON.stringify({
    featureId: meta.featureId,
    sessionId: meta.sessionId,
    modelTier: meta.modelTier,
    ts: Date.now(),
  }));
  // Route to cost-optimised model for 'fast' tier
  if (meta.modelTier === 'fast') {
    out.set('cf-aig-prefer-model', 'gpt-4o-mini');
  }
  return out;
}
```

## Streaming Response Pass-Through with Inspection

When upstream returns `text/event-stream`, the middleware must pass through the SSE stream while still inspecting the final delta for output filtering.

```typescript
// src/middleware/streaming-passthrough.ts
export async function passthroughStream(
  upstream: Response,
  filterFn: (chunk: string) => string
): Promise<Response> {
  if (!upstream.body) return upstream;

  const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>();
  const writer = writable.getWriter();
  const encoder = new TextEncoder();
  const decoder = new TextDecoder();

  (async () => {
    const reader = upstream.body!.getReader();
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const text = decoder.decode(value, { stream: true });
        const filtered = filterFn(text);
        await writer.write(encoder.encode(filtered));
      }
    } finally {
      await writer.close();
    }
  })();

  return new Response(readable, {
    status: upstream.status,
    headers: upstream.headers,
  });
}
```

## Response Output Filtering

Scan the final assistant message for policy violations (competitor names, prohibited content) and replace offending segments before returning to the caller.

```typescript
// src/middleware/output-filter.ts
const BLOCKED_TERMS: string[] = ['CompetitorX', 'CompetitorY'];

export function filterOutput(text: string): string {
  let filtered = text;
  for (const term of BLOCKED_TERMS) {
    filtered = filtered.replaceAll(term, '[redacted]');
  }
  return filtered;
}

export function isNonStreamingResponse(response: Response): boolean {
  const ct = response.headers.get('content-type') ?? '';
  return ct.includes('application/json') && !ct.includes('text/event-stream');
}

export async function filterNonStreamingResponse(response: Response): Promise<Response> {
  if (!isNonStreamingResponse(response)) return response;
  const body = await response.json<{
    choices: { message: { content: string } }[];

  }>();
  if (body.choices?.[0]?.message?.content) {
    body.choices[0].message.content = filterOutput(body.choices[0].message.content);
  }
  return Response.json(body, { status: response.status, headers: response.headers });
}
```

## Anti-patterns
- Buffering the entire streaming response body to apply filters — kills time-to-first-token
- Storing the `GATEWAY_TOKEN` in Worker source code instead of a secret binding
- Applying PII sanitization only to the final message and not the full conversation history
- Forwarding all incoming request headers verbatim to the upstream — leaks internal headers
- Using a synchronous regex pass over every SSE chunk — causes CPU spikes on large completions

## Gotchas
- AI Gateway's `cf-aig-metadata` header is capped at 1,024 bytes of JSON; keep metadata lean
- Injecting a system prompt changes token counts — update any upstream token-budget logic accordingly
- Workers have a 128 MB memory limit; avoid accumulating stream chunks in memory for large responses
- `TransformStream` piping is non-blocking but the Writer must be explicitly closed or the response hangs
- Gateway logs show the transformed request, not the original — document redaction behaviour for compliance audits

## Verification
1. POST a message containing a fake SSN (`123-45-6789`) and confirm the upstream log shows `[SSN]`.
2. Check AI Gateway dashboard logs for `cf-aig-customer-id` presence on every request.
3. Confirm a response containing a blocked term returns `[redacted]` for both streaming and non-streaming paths.
4. Assert that system messages from callers are dropped and only the KV-backed prompt appears.

## Related
- [AI Gateway Logging](ai-gateway-logging.md)
- [AI Gateway Rate Limiting](ai-gateway-rate-limiting.md)
- [LLM Prompt Injection Defense Workers](llm-prompt-injection-defense-workers.md)
- [PII Detection Redaction](pii-detection-redaction.md)

## Sources
- https://developers.cloudflare.com/ai-gateway/configuration/custom-metadata/
- https://developers.cloudflare.com/ai-gateway/providers/openai/
- https://developers.cloudflare.com/workers/runtime-apis/streams/transformstream/
