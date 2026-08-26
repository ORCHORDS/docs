# AI Gateway Request Deduplication and Idempotency

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Downstream clients retry LLM requests on timeout or transient failure, causing duplicate charges and inconsistent
responses when the same prompt is processed twice. You need the AI Gateway layer to collapse identical in-flight
requests and return a stable response for a given idempotency key without re-running inference.

## Context

Cloudflare AI Gateway sits between your Worker and upstream model providers. It already offers semantic caching, but
semantic caching is similarity-based and non-deterministic in key collisions. For billing-critical or side-effect-rich
workflows (e.g., a generation that writes to D1 after completion) you need hard idempotency: the same logical request
must produce the same response and trigger downstream effects exactly once. The pattern uses a KV store to record
in-progress and completed request state, keyed by a client-supplied or deterministically derived idempotency key.

## Idempotency Key Derivation

Generate the key from request content so retries without an explicit header still deduplicate.

```typescript
import { Ai } from "@cloudflare/ai";

interface Env {
  AI: Ai;
  IDEMPOTENCY_KV: KVNamespace;
}

interface LLMRequest {
  model: string;
  messages: { role: string; content: string }[];
  idempotencyKey?: string;
}

async function deriveIdempotencyKey(req: LLMRequest): Promise<string> {
  const payload = JSON.stringify({
    model: req.model,
    messages: req.messages,
  });
  const hashBuffer = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(payload)
  );
  const hashHex = Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  return req.idempotencyKey ?? `idem:${hashHex}`;
}
```

## In-Flight Deduplication with KV Locks

Use a two-phase KV entry: `pending` while inference runs, `done` once complete. Concurrent retries poll until done.

```typescript
type IdempotencyState =
  | { status: "pending"; startedAt: number }
  | { status: "done"; response: unknown; completedAt: number };

const LOCK_TTL_SECONDS = 30;
const POLL_INTERVAL_MS = 500;
const MAX_POLLS = 60;

async function runWithIdempotency(
  env: Env,
  key: string,
  run: () => Promise<unknown>
): Promise<unknown> {
  // Check if already completed
  const existing = await env.IDEMPOTENCY_KV.get<IdempotencyState>(key, "json");
  if (existing?.status === "done") {
    return existing.response;
  }

  // Try to acquire lock
  if (existing?.status === "pending") {
    // Another request is in-flight — poll for completion
    for (let i = 0; i < MAX_POLLS; i++) {
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
      const polled = await env.IDEMPOTENCY_KV.get<IdempotencyState>(key, "json");
      if (polled?.status === "done") return polled.response;
      if (!polled) break; // lock expired, fall through to re-run
    }
  }

  // Claim the lock
  const pendingState: IdempotencyState = {
    status: "pending",
    startedAt: Date.now(),
  };
  await env.IDEMPOTENCY_KV.put(key, JSON.stringify(pendingState), {
    expirationTtl: LOCK_TTL_SECONDS,
  });

  try {
    const response = await run();
    const doneState: IdempotencyState = {
      status: "done",
      response,
      completedAt: Date.now(),
    };
    // Store completed response for 24 h
    await env.IDEMPOTENCY_KV.put(key, JSON.stringify(doneState), {
      expirationTtl: 86400,
    });
    return response;
  } catch (err) {
    // Release lock on failure so callers can retry
    await env.IDEMPOTENCY_KV.delete(key);
    throw err;
  }
}
```

## Worker Handler with AI Gateway

Wire the deduplication logic into an AI Gateway-routed fetch, forwarding the resolved response to the client.

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const body = (await request.json()) as LLMRequest;
    const idempotencyKey = await deriveIdempotencyKey(body);

    const result = await runWithIdempotency(env, idempotencyKey, async () => {
      // AI Gateway endpoint — configured in Cloudflare dashboard
      const gatewayUrl =
        "https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/workers-ai/v1/chat/completions";

      const upstream = await fetch(gatewayUrl, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${(env as any).CF_API_TOKEN}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model: body.model,
          messages: body.messages,
        }),
      });

      if (!upstream.ok) {
        throw new Error(`Upstream error: ${upstream.status}`);
      }
      return upstream.json();
    });

    return Response.json({
      idempotencyKey,
      data: result,
    });
  },
} satisfies ExportedHandler<Env>;
```

## Anti-patterns

- Using only semantic cache TTL as a deduplication mechanism — it is probabilistic and will miss exact retries with
  slightly different whitespace or punctuation.
- Storing the lock in memory (e.g., a `Map`) — Worker instances are ephemeral and do not share memory across requests.
- Setting the done-state TTL too short — clients that retry after 5 minutes will bypass deduplication and incur a
  second inference charge.

## Gotchas

- KV write propagation is eventually consistent (~60 ms typical). Under extremely tight retry bursts two Workers may
  both see no lock entry and both start inference. Accept this rare race or use a Durable Object for strict
  serialisation when absolute once-only semantics are required.
- The `LOCK_TTL_SECONDS` must exceed the 99th-percentile inference latency for your model. Set it too low and an
  in-progress request has its lock evicted, causing a duplicate run.

## Verification

```bash
# Send initial request and capture idempotency key
KEY=$(curl -s -X POST https://your-worker.workers.dev/ \
  -H "Content-Type: application/json" \
  -d '{"model":"@cf/meta/llama-3.1-8b-instruct","messages":[{"role":"user","content":"Hello"}]}' \
  | jq -r '.idempotencyKey')

echo "Key: $KEY"

# Send identical request — should return cached done-state, not re-run inference
curl -s -X POST https://your-worker.workers.dev/ \
  -H "Content-Type: application/json" \
  -d '{"model":"@cf/meta/llama-3.1-8b-instruct","messages":[{"role":"user","content":"Hello"}]}' \
  | jq '.idempotencyKey'

# Keys must match; response times should differ (second << first)
```

## Related

- `ai-ml/ai-gateway-caching.md`
- `ai-ml/ai-agent-tool-call-retry-idempotency-durable-objects.md`
- `ai-ml/ai-gateway-logging.md`

## Sources

- https://developers.cloudflare.com/ai-gateway/
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/
- https://developers.cloudflare.com/ai-gateway/configuration/caching/
