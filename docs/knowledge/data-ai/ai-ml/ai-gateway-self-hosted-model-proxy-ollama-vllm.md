# AI Gateway Self-Hosted Model Proxy for Ollama and vLLM

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You run inference on private GPU hardware (Ollama, vLLM, LM Studio, or a bare OpenAI-compatible HTTP server) but want centralised logging, rate limiting, semantic caching, and cost attribution without rewriting every client. AI Gateway's "Universal Endpoint" accepts an arbitrary base URL, letting you proxy all traffic through the same observability layer you use for OpenAI and Anthropic.

## Context

AI Gateway supports a third-party / self-hosted provider target. You configure the gateway with your self-hosted server URL (must be publicly reachable or tunnelled via Cloudflare Tunnel). Every request hits `https://gateway.ai.cloudflare.com/v1/{account}/{gateway}/openai` and is forwarded to your backend with the original `Authorization` header stripped or rewritten. Responses are logged, cached per semantic similarity, and rate-limited at the gateway tier before they reach your client.

---

## 1. Expose Self-Hosted Inference via Cloudflare Tunnel

```bash
# Install cloudflared on the GPU host
curl -L https://pkg.cloudflare.com/cloudflare-main.gpg | sudo gpg --dearmor \
  -o /usr/share/keyrings/cloudflare-main.gpg
apt install cloudflared

# Create a named tunnel bound to your Ollama or vLLM port
cloudflared tunnel create my-gpu-server
cloudflared tunnel route dns my-gpu-server inference.example.com

# config.yaml — forward traffic to the local inference server
cat > ~/.cloudflared/config.yaml <<EOF
tunnel: <TUNNEL_ID>
credentials-file: /root/.cloudflared/<TUNNEL_ID>.json
ingress:
  - hostname: inference.example.com
    service: http://localhost:11434   # Ollama default port; use 8000 for vLLM
  - service: http_status:404
EOF

cloudflared tunnel run my-gpu-server
```

---

## 2. Configure AI Gateway with a Custom Provider Target

AI Gateway provider `openai` can be redirected to any OpenAI-compatible endpoint via the `cf-aig-base-url` header or via a gateway-level provider override in the dashboard.

```typescript
// src/inference/self-hosted.ts
export interface SelfHostedConfig {
  gatewayId: string;
  accountId: string;
  backendBaseUrl: string; // e.g. https://inference.example.com/v1
  apiKey: string;         // forwarded to backend; can be an empty string for Ollama
}

export function buildGatewayClient(cfg: SelfHostedConfig) {
  const gatewayBase = `https://gateway.ai.cloudflare.com/v1/${cfg.accountId}/${cfg.gatewayId}/openai`;

  return async function chatComplete(
    model: string,
    messages: { role: string; content: string }[],
    options: { stream?: boolean; temperature?: number } = {},
  ): Promise<Response> {
    return fetch(`${gatewayBase}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${cfg.apiKey}`,
        // Tell the gateway to route to the self-hosted backend
        'cf-aig-base-url': cfg.backendBaseUrl,
        // Optional: skip gateway cache for non-deterministic requests
        'cf-aig-cache-ttl': options.stream ? '0' : '300',
      },
      body: JSON.stringify({
        model,
        messages,
        stream: options.stream ?? false,
        temperature: options.temperature ?? 0.7,
      }),
    });
  };
}
```

---

## 3. Workers AI Fallback — Route to Cloud When GPU Is Down

```typescript
// src/inference/router.ts
import type { Env } from '../types';

export async function routeInference(
  env: Env,
  model: string,
  messages: { role: string; content: string }[],
): Promise<{ text: string; source: 'self-hosted' | 'workers-ai' }> {
  // Attempt self-hosted via AI Gateway proxy
  try {
    const client = buildGatewayClient({
      gatewayId: env.AI_GATEWAY_ID,
      accountId: env.CF_ACCOUNT_ID,
      backendBaseUrl: env.SELF_HOSTED_BASE_URL,
      apiKey: env.SELF_HOSTED_API_KEY,
    });

    const res = await client(model, messages);
    if (!res.ok) throw new Error(`Self-hosted returned ${res.status}`);

    const json = await res.json<{ choices: { message: { content: string } }[] }>();
    return { text: json.choices[0].message.content, source: 'self-hosted' };
  } catch (err) {
    console.warn('[router] self-hosted failed, falling back to Workers AI:', err);
  }

  // Fallback — Workers AI (Cloudflare-hosted)
  const result = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', { messages });
  return { text: result.response ?? '', source: 'workers-ai' };
}
```

---

## 4. Semantic Cache Bypass for Streaming Requests

AI Gateway caches non-streaming completions; streaming responses are never cached. To avoid cache misses masking latency improvements on self-hosted hardware, use cache headers explicitly:

```typescript
// Cache control per request type
const headers: Record<string, string> = {
  'Content-Type': 'application/json',
  Authorization: `Bearer ${apiKey}`,
  'cf-aig-base-url': backendBaseUrl,
};

if (stream) {
  headers['cf-aig-skip-cache'] = 'true';
} else {
  // Cache deterministic completions for 10 minutes
  headers['cf-aig-cache-ttl'] = '600';
}
```

---

## 5. Rate Limiting and Per-Model Budget in AI Gateway

AI Gateway rate limits apply before the backend sees the request. Configure per-model limits in the dashboard or via the API to prevent a single heavy model from starving lighter ones:

```bash
# Set a rate limit of 60 requests/minute on a specific provider config
curl -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT/ai-gateway/gateways/$GATEWAY_ID/providers/openai/rate-limits" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"requests_per_minute": 60, "model": "llama3:70b"}'
```

For cost attribution, pass a `cf-aig-metadata` header; the gateway logs it alongside the request:

```typescript
headers['cf-aig-metadata'] = JSON.stringify({
  tenant: userId,
  model: 'llama3:70b',
  feature: 'chat',
});
```

---

## 6. Validating Connectivity Before Serving Traffic

```typescript
// src/lib/health.ts
export async function checkSelfHostedHealth(baseUrl: string): Promise<boolean> {
  try {
    const res = await fetch(`${baseUrl}/models`, {
      signal: AbortSignal.timeout(3000),
    });
    return res.ok;
  } catch {
    return false;
  }
}
```

Call this from a Workers startup check or a scheduled health-ping cron.

---

## Anti-patterns

- Pointing `cf-aig-base-url` at a local LAN IP — the gateway cannot reach RFC-1918 addresses; use Cloudflare Tunnel.
- Forwarding raw `Authorization` headers from clients to the backend — rotate to a server-side secret; never expose backend credentials to the client.
- Enabling gateway caching for embedding endpoints — embedding responses are cheap to recompute and caching them by exact text match rarely helps; enable caching only for chat completions.
- Running both OpenAI and self-hosted providers under the same gateway ID without metadata tagging — log analysis becomes impossible without per-source labels.

## Gotchas

- Ollama's default `/v1/chat/completions` endpoint is OpenAI-compatible only for models loaded with `ollama pull`; models pulled from GGUF files may not enumerate correctly via `/v1/models`.
- vLLM's `--served-model-name` flag must match the `model` field in the request body; a mismatch returns a 404 even when the model is loaded.
- `cf-aig-base-url` overrides the gateway's configured backend for that request only; it does not persist across requests.
- AI Gateway semantic cache computes embeddings on the gateway side; very long prompts (>8 k tokens) may fail cache lookup silently and always hit the backend.

## Verification

```bash
# Smoke test through AI Gateway to self-hosted backend
curl -X POST \
  "https://gateway.ai.cloudflare.com/v1/$CF_ACCOUNT/$GATEWAY_ID/openai/chat/completions" \
  -H "Authorization: Bearer $SELF_HOSTED_KEY" \
  -H "cf-aig-base-url: https://inference.example.com/v1" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3:8b","messages":[{"role":"user","content":"ping"}]}'

# Confirm log appears in AI Gateway dashboard with source header
# Check cf-aig-metadata in the gateway logs UI
```

## Related

- `ai-gateway-fallback-model-chain.md`
- `ai-gateway-model-routing-latency-cost-workers.md`
- `ai-gateway-logging.md`
- `llm-inference-serving-vllm.md`
- `always-on-local-llm-deployment.md`

## Sources

- Cloudflare AI Gateway — Universal Endpoint documentation
- Cloudflare Tunnel quickstart
- Ollama OpenAI compatibility guide
- vLLM OpenAI-compatible server documentation
