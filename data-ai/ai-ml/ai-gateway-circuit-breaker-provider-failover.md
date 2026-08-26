# AI Gateway Circuit Breaker Provider Failover

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A provider (OpenAI, Anthropic, Google) goes into a partial outage where requests hang or return 5xx. Simple retry loops keep firing into the degraded endpoint, consuming budget and adding latency. You need a circuit breaker that opens automatically when failure rate crosses a threshold, routes to a healthy provider via AI Gateway, and re-probes after a cool-down period.

## Context

Cloudflare AI Gateway supports multiple provider endpoints under a single gateway URL. The circuit breaker state lives in Workers KV (fast reads, eventual consistency acceptable for this use case) and is updated by each Worker invocation. States: CLOSED (normal), OPEN (failing, skip provider), HALF-OPEN (probe with one request to test recovery).

---

## Circuit Breaker State in KV

```typescript
// circuit-breaker.ts
export type CBState = "CLOSED" | "OPEN" | "HALF_OPEN";

export interface CBRecord {
  state: CBState;
  failures: number;
  lastFailure: number;    // epoch ms
  successStreak: number;
}

const FAILURE_THRESHOLD = 5;
const OPEN_DURATION_MS = 60_000;   // 1 minute cool-down
const HALF_OPEN_SUCCESSES = 2;     // successes needed to close

export async function getState(kv: KVNamespace, provider: string): Promise<CBRecord> {
  const raw = await kv.get(`cb:${provider}`, "json") as CBRecord | null;
  if (!raw) return { state: "CLOSED", failures: 0, lastFailure: 0, successStreak: 0 };

  // Auto-transition OPEN → HALF_OPEN after cool-down
  if (raw.state === "OPEN" && Date.now() - raw.lastFailure > OPEN_DURATION_MS) {
    return { ...raw, state: "HALF_OPEN", successStreak: 0 };
  }
  return raw;
}

export async function recordSuccess(kv: KVNamespace, provider: string, cb: CBRecord): Promise<void> {
  const streak = cb.successStreak + 1;
  const newState: CBState =
    cb.state === "HALF_OPEN" && streak >= HALF_OPEN_SUCCESSES ? "CLOSED" : cb.state;

  await kv.put(`cb:${provider}`, JSON.stringify({
    state: newState,
    failures: newState === "CLOSED" ? 0 : cb.failures,
    lastFailure: cb.lastFailure,
    successStreak: streak
  }), { expirationTtl: 3600 });
}

export async function recordFailure(kv: KVNamespace, provider: string, cb: CBRecord): Promise<void> {
  const failures = cb.failures + 1;
  const newState: CBState = failures >= FAILURE_THRESHOLD ? "OPEN" : cb.state;

  await kv.put(`cb:${provider}`, JSON.stringify({
    state: newState,
    failures,
    lastFailure: Date.now(),
    successStreak: 0
  }), { expirationTtl: 3600 });
}
```

---

## Provider Priority List

Providers are tried in order; OPEN ones are skipped unless HALF_OPEN probe is due.

```typescript
// providers.ts
export interface Provider {
  id: string;
  gatewayUrl: string;  // AI Gateway endpoint for this provider
  model: string;
  apiKeyEnv: string;
}

export const PROVIDERS: Provider[] = [
  {
    id: "openai",
    gatewayUrl: "https://gateway.ai.cloudflare.com/v1/ACCOUNT/GW/openai",
    model: "gpt-4o-mini",
    apiKeyEnv: "OPENAI_API_KEY"
  },
  {
    id: "anthropic",
    gatewayUrl: "https://gateway.ai.cloudflare.com/v1/ACCOUNT/GW/anthropic",
    model: "claude-haiku-4-5",
    apiKeyEnv: "ANTHROPIC_API_KEY"
  },
  {
    id: "workers-ai",
    gatewayUrl: "https://gateway.ai.cloudflare.com/v1/ACCOUNT/GW/workers-ai",
    model: "@cf/mistral/mistral-7b-instruct-v0.1",
    apiKeyEnv: "CF_API_TOKEN"
  }
];
```

---

## Failover Router

```typescript
// router.ts
export async function callWithCircuitBreaker(
  kv: KVNamespace,
  env: Env,
  messages: { role: string; content: string }[]
): Promise<string> {
  for (const provider of PROVIDERS) {
    const cb = await getState(kv, provider.id);

    if (cb.state === "OPEN") {
      console.log(`[CB] ${provider.id} is OPEN — skipping`);
      continue;
    }

    try {
      const answer = await callProvider(provider, env, messages);
      await recordSuccess(kv, provider.id, cb);
      return answer;
    } catch (err) {
      console.error(`[CB] ${provider.id} failed:`, err);
      await recordFailure(kv, provider.id, cb);
      // Continue to next provider
    }
  }

  throw new Error("All providers are unavailable.");
}

async function callProvider(
  provider: Provider,
  env: Env,
  messages: { role: string; content: string }[]
): Promise<string> {
  const apiKey = (env as Record<string, string>)[provider.apiKeyEnv];
  const res = await fetch(`${provider.gatewayUrl}/chat/completions`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${apiKey}`,
      "Content-Type": "application/json",
      "cf-aig-metadata": JSON.stringify({ provider: provider.id })
    },
    body: JSON.stringify({ model: provider.model, messages, max_tokens: 512 }),
    signal: AbortSignal.timeout(15_000)
  });

  if (!res.ok) throw new Error(`HTTP ${res.status} from ${provider.id}`);
  const json = await res.json<{ choices: { message: { content: string } }[] }>();
  return json.choices[0].message.content;
}
```

---

## Worker Entry Point with Observability

```typescript
// worker.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { messages } = await req.json<{ messages: { role: string; content: string }[] }>();

    const start = Date.now();
    try {
      const answer = await callWithCircuitBreaker(env.KV, env, messages);
      return Response.json({ answer, latencyMs: Date.now() - start });
    } catch (err) {
      return Response.json(
        { error: "All LLM providers unavailable. Please retry later." },
        { status: 503 }
      );
    }
  }
};
```

---

## Dashboard: Circuit Breaker Status Endpoint

```typescript
// status.ts
export async function handleStatus(kv: KVNamespace): Promise<Response> {
  const states = await Promise.all(
    PROVIDERS.map(async p => ({ provider: p.id, ...(await getState(kv, p.id)) }))
  );
  return Response.json({ circuitBreakers: states, timestamp: new Date().toISOString() });
}
```

---

## Anti-patterns

- **Sharing circuit breaker state only in memory** — Workers are stateless; KV is the only way to share failure counts across instances.
- **Using the same threshold for all providers** — a bursty Workers AI quota error differs from a real OpenAI outage; tune per provider if needed.
- **Not logging which provider served the request** — use `cf-aig-metadata` so AI Gateway logs carry the provider label.
- **Infinite HALF_OPEN probes** — if the probe itself throws, re-open the circuit; don't let it loop in HALF_OPEN indefinitely.
- **Opening the circuit on client errors (4xx)** — only count 5xx and timeouts; 4xx usually indicates a bad request, not a provider failure.

## Gotchas

- KV writes are eventually consistent; two Worker instances may both attempt a HALF_OPEN probe simultaneously. This is acceptable — the extra probe is cheap and recovers the circuit faster.
- `AbortSignal.timeout()` is supported in Workers runtime ≥ 2024-08-01; ensure `compatibility_date` is set accordingly.
- AI Gateway does not itself implement circuit breaking; it routes to a single provider per request. The circuit breaker logic must live in your Worker.
- Cloudflare AI Gateway's provider-level retry setting applies within a single request; it does not open/close circuits across requests.
- When all three providers are OPEN, return HTTP 503 with `Retry-After: 60` so clients back off.

## Verification

```bash
# Check circuit states
curl https://your-worker.workers.dev/status

# Simulate provider failure by calling a bad endpoint, then check state transitions:
# After FAILURE_THRESHOLD failures, provider moves to OPEN.
# After OPEN_DURATION_MS, moves to HALF_OPEN.
# After HALF_OPEN_SUCCESSES successes, moves back to CLOSED.

# Integration test
curl -X POST https://your-worker.workers.dev/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"ping"}]}'
```

## Related

- `ai-gateway-fallback-model-chain.md`
- `ai-gateway-model-routing-latency-cost-workers.md`
- `llm-retry-patterns.md`
- `llm-fallback-provider-rotation.md`
- `ai-gateway-rate-limiting.md`

## Sources

- Cloudflare AI Gateway: https://developers.cloudflare.com/ai-gateway/
- Circuit breaker pattern: https://martinfowler.com/bliki/CircuitBreaker.html
- Workers KV: https://developers.cloudflare.com/kv/
