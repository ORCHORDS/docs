# AI Gateway Conditional Model Routing: Content-Based and Tier-Based Dispatch

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your AI application serves multiple user segments — free-tier users, paid subscribers, and internal tooling — and different request types: short classification tasks, long-form document summarisation, code generation, and multi-turn chat. Routing every request to the same model is wasteful: cheap, fast models handle 80% of traffic, while expensive frontier models handle only the requests that genuinely require them.

AI Gateway's built-in fallback chain handles provider unavailability but not content-based or user-tier-based routing. This article implements a routing layer in Workers that sits in front of AI Gateway, inspecting each request at the edge and dispatching to the appropriate AI Gateway endpoint and model based on declared rules.

## Context

Cloudflare AI Gateway provides a universal endpoint (`https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/`) that normalises requests to OpenAI-compatible, Anthropic, and Workers AI providers. Each request to AI Gateway goes to a single configured provider/model pair per call. Conditional routing — choosing which model to call — must happen before the AI Gateway request, in Worker code.

The routing Worker acts as a middleware: it reads routing signals from the request (user tier from a JWT, estimated token count, task type from a request header or classifier), applies a declarative rule set fetched from KV, then forwards to the appropriate AI Gateway URL. This keeps routing configuration hot-swappable without redeployment.

## Routing Signal Sources

```typescript
// signals.ts — extract routing signals from an incoming request
export interface RoutingSignals {
  userTier: "free" | "pro" | "enterprise" | "internal";
  estimatedInputTokens: number;
  taskType: "classification" | "summarisation" | "code" | "chat" | "embedding" | "unknown";
  requestedModel?: string; // explicit override from request body
  contentLanguage: string;
}

export async function extractSignals(request: Request): Promise<RoutingSignals> {
  const body = await request.clone().json<{
    model?: string;
    messages?: Array<{ role: string; content: string }>;
    prompt?: string;
    task_type?: string;
  }>();

  const userTier = extractTierFromJWT(request.headers.get("Authorization") ?? "");
  const inputText = extractInputText(body);
  const estimatedTokens = Math.ceil(inputText.length / 4); // rough estimate: ~4 chars/token

  return {
    userTier,
    estimatedInputTokens: estimatedTokens,
    taskType: (body.task_type as RoutingSignals["taskType"]) ?? inferTaskType(body),
    requestedModel: body.model,
    contentLanguage: request.headers.get("Content-Language") ?? "en",
  };
}

function extractTierFromJWT(authHeader: string): RoutingSignals["userTier"] {
  try {
    const token = authHeader.replace("Bearer ", "");
    const payload = JSON.parse(atob(token.split(".")[1]));
    return payload.tier ?? "free";
  } catch {
    return "free";
  }
}

function extractInputText(body: { messages?: Array<{ role: string; content: string }>; prompt?: string }): string {
  if (body.messages) {
    return body.messages.map((m) => m.content).join(" ");
  }
  return body.prompt ?? "";
}

function inferTaskType(body: { messages?: Array<{ role: string; content: string }>; prompt?: string }): RoutingSignals["taskType"] {
  const text = extractInputText(body).toLowerCase();
  if (text.includes("summarize") || text.includes("summarise") || text.includes("tldr")) return "summarisation";
  if (text.includes("classify") || text.includes("category") || text.includes("label")) return "classification";
  if (text.includes("code") || text.includes("function") || text.includes("implement")) return "code";
  return "chat";
}
```

## Routing Rule Configuration (KV-Backed)

Store routing rules in Workers KV as JSON. This allows hot-swapping rules without redeployment:

```typescript
// rules.ts
export interface ModelTarget {
  provider: "workers-ai" | "openai" | "anthropic";
  model: string;
  gatewayPath: string; // path appended to AI Gateway universal endpoint
  maxInputTokens: number;
  costTierIndex: number; // 0 = cheapest, higher = more expensive
}

export interface RoutingRule {
  id: string;
  priority: number; // lower = evaluated first
  conditions: {
    userTiers?: Array<"free" | "pro" | "enterprise" | "internal">;
    taskTypes?: Array<"classification" | "summarisation" | "code" | "chat" | "embedding">;
    minInputTokens?: number;
    maxInputTokens?: number;
  };
  target: ModelTarget;
}

// Default rules — stored in KV under key "routing_rules_v1"
export const DEFAULT_RULES: RoutingRule[] = [
  {
    id: "internal-frontier",
    priority: 0,
    conditions: { userTiers: ["internal"] },
    target: {
      provider: "anthropic",
      model: "claude-opus-4-5",
      gatewayPath: "anthropic/v1/messages",
      maxInputTokens: 200_000,
      costTierIndex: 3,
    },
  },
  {
    id: "enterprise-code",
    priority: 10,
    conditions: { userTiers: ["enterprise"], taskTypes: ["code"] },
    target: {
      provider: "anthropic",
      model: "claude-sonnet-4-5",
      gatewayPath: "anthropic/v1/messages",
      maxInputTokens: 100_000,
      costTierIndex: 2,
    },
  },
  {
    id: "long-document-summarisation",
    priority: 20,
    conditions: { taskTypes: ["summarisation"], minInputTokens: 4000 },
    target: {
      provider: "workers-ai",
      model: "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
      gatewayPath: "workers-ai/@cf/meta/llama-3.3-70b-instruct-fp8-fast",
      maxInputTokens: 32_000,
      costTierIndex: 1,
    },
  },
  {
    id: "free-tier-default",
    priority: 100,
    conditions: { userTiers: ["free"] },
    target: {
      provider: "workers-ai",
      model: "@cf/meta/llama-3.1-8b-instruct",
      gatewayPath: "workers-ai/@cf/meta/llama-3.1-8b-instruct",
      maxInputTokens: 8_000,
      costTierIndex: 0,
    },
  },
  {
    id: "catch-all",
    priority: 999,
    conditions: {},
    target: {
      provider: "workers-ai",
      model: "@cf/meta/llama-3.1-8b-instruct",
      gatewayPath: "workers-ai/@cf/meta/llama-3.1-8b-instruct",
      maxInputTokens: 8_000,
      costTierIndex: 0,
    },
  },
];
```

## Rule Evaluation Engine

```typescript
// router.ts
import { RoutingSignals, RoutingRule, ModelTarget } from "./rules";

export function selectTarget(
  signals: RoutingSignals,
  rules: RoutingRule[]
): ModelTarget {
  // Respect explicit model override for internal/enterprise tiers only
  if (
    signals.requestedModel &&
    (signals.userTier === "enterprise" || signals.userTier === "internal")
  ) {
    // Pass-through to a generic target that uses the requested model directly
    return {
      provider: "workers-ai",
      model: signals.requestedModel,
      gatewayPath: `workers-ai/${signals.requestedModel}`,
      maxInputTokens: 200_000,
      costTierIndex: 2,
    };
  }

  // Sort by priority (ascending), evaluate conditions
  const sorted = [...rules].sort((a, b) => a.priority - b.priority);

  for (const rule of sorted) {
    if (matchesRule(signals, rule)) {
      return rule.target;
    }
  }

  // Should never reach here if catch-all rule is present
  throw new Error("No routing rule matched and no catch-all defined");
}

function matchesRule(signals: RoutingSignals, rule: RoutingRule): boolean {
  const c = rule.conditions;

  if (c.userTiers && !c.userTiers.includes(signals.userTier)) return false;
  if (c.taskTypes && !c.taskTypes.includes(signals.taskType)) return false;
  if (c.minInputTokens !== undefined && signals.estimatedInputTokens < c.minInputTokens) return false;
  if (c.maxInputTokens !== undefined && signals.estimatedInputTokens > c.maxInputTokens) return false;

  return true;
}
```

## Request Forwarding Through AI Gateway

```typescript
// forwarder.ts
import { ModelTarget } from "./rules";

const GATEWAY_BASE = `https://gateway.ai.cloudflare.com/v1`;

export async function forwardToGateway(
  originalRequest: Request,
  target: ModelTarget,
  accountId: string,
  gatewayId: string,
  cfToken: string
): Promise<Response> {
  const gatewayUrl = `${GATEWAY_BASE}/${accountId}/${gatewayId}/${target.gatewayPath}`;

  const body = await originalRequest.json();

  // Normalise to provider format
  const normalised = normaliseRequestBody(body, target);

  const gatewayResponse = await fetch(gatewayUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${cfToken}`,
      // AI Gateway custom metadata for logging / cost attribution
      "cf-aig-metadata": JSON.stringify({
        userTier: (originalRequest as any)._routingTier,
        model: target.model,
        provider: target.provider,
      }),
    },
    body: JSON.stringify(normalised),
  });

  return gatewayResponse;
}

function normaliseRequestBody(
  body: Record<string, unknown>,
  target: ModelTarget
): Record<string, unknown> {
  // Anthropic format differs from OpenAI — inject model field for Workers AI / OpenAI
  if (target.provider === "anthropic") {
    const { model: _model, ...rest } = body;
    return { ...rest, model: target.model };
  }
  // Workers AI and OpenAI-compatible providers accept model in the body
  return { ...body, model: target.model };
}
```

## Full Worker Entry Point

```typescript
// worker.ts
import { Env } from "./types";
import { extractSignals } from "./signals";
import { DEFAULT_RULES, RoutingRule } from "./rules";
import { selectTarget } from "./router";
import { forwardToGateway } from "./forwarder";

const RULES_KV_KEY = "routing_rules_v1";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    // 1. Load routing rules from KV (hot-reloadable)
    let rules: RoutingRule[] = DEFAULT_RULES;
    try {
      const kvRules = await env.CONFIG_KV.get(RULES_KV_KEY, "json");
      if (kvRules) rules = kvRules as RoutingRule[];
    } catch {
      // Fall back to compiled defaults
    }

    // 2. Extract routing signals from the request
    const signals = await extractSignals(request.clone());

    // 3. Select target model
    const target = selectTarget(signals, rules);

    // 4. Log routing decision to Analytics Engine
    env.ANALYTICS.writeDataPoint({
      blobs: [signals.userTier, signals.taskType, target.model, target.provider],
      doubles: [signals.estimatedInputTokens, target.costTierIndex],
      indexes: [signals.userTier],
    });

    // 5. Forward to AI Gateway
    const response = await forwardToGateway(
      request,
      target,
      env.CLOUDFLARE_ACCOUNT_ID,
      env.AI_GATEWAY_ID,
      env.AI_GATEWAY_TOKEN
    );

    // 6. Annotate response with routing metadata
    const responseWithHeaders = new Response(response.body, response);
    responseWithHeaders.headers.set("X-Routed-Model", target.model);
    responseWithHeaders.headers.set("X-Routed-Provider", target.provider);

    return responseWithHeaders;
  },
};
```

## Anti-patterns

- Hard-coding routing rules in Worker source code — rules must change without redeployment; store them in KV
- Using input token estimates as the sole routing signal — a 100-token request might be complex reasoning requiring a frontier model; combine token count with task type
- Letting free-tier users override the model via the `model` request field — gate explicit overrides to enterprise/internal tiers only
- Not logging routing decisions — without telemetry you cannot measure model cost savings or detect routing anomalies
- Setting no catch-all rule — if all conditions fail, the router should have a safe default rather than throwing an unhandled error
- Routing to a model that cannot handle the estimated token count — validate against `target.maxInputTokens` before forwarding and return a 413 with a clear error

## Gotchas

- AI Gateway URL paths differ by provider: `anthropic/v1/messages`, `openai/chat/completions`, `workers-ai/@cf/model/name`. The `gatewayPath` field in each rule must match exactly.
- Normalising request bodies across providers is non-trivial. Anthropic's `messages` format and Workers AI's format both use `messages`, but max_tokens key names differ (`max_tokens` vs `max_tokens` in newer models). Test each provider path with a real request before going to production.
- Workers KV has eventual consistency. A routing rule update may take up to 60 seconds to propagate globally. Design rule changes to be safe during the propagation window (e.g., adding new rules rather than modifying existing ones).
- The `cf-aig-metadata` header has a size limit; keep the JSON payload under 1 KB.
- Token estimation with `chars / 4` is a rough heuristic. Code and non-English text tokenise very differently. Over-estimate by 20% for safety margins when checking against `maxInputTokens`.

## Verification

```bash
# Route free-tier chat request → 8B model
curl -X POST https://your-worker.workers.dev/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <free-tier-jwt>" \
  -d '{"messages":[{"role":"user","content":"Hello"}]}' \
  -i | grep X-Routed-Model
# Expected: X-Routed-Model: @cf/meta/llama-3.1-8b-instruct

# Route enterprise code request → Sonnet
curl -X POST https://your-worker.workers.dev/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <enterprise-jwt>" \
  -H "X-Task-Type: code" \
  -d '{"messages":[{"role":"user","content":"Write a Rust parser"}],"task_type":"code"}' \
  -i | grep X-Routed-Model
# Expected: X-Routed-Model: claude-sonnet-4-5
```

## Related

- `ai-gateway-fallback-model-chain.md` — provider-level fallback for unavailability (complements routing)
- `ai-gateway-cost-attribution-per-tenant-d1.md` — attributing costs by user tier after routing
- `ai-gateway-multi-provider-ab-testing.md` — splitting traffic for model quality experiments
- `model-cascade-cheap-first-routing.md` — cascade pattern: try cheap model, escalate on low confidence

## Sources

- Cloudflare AI Gateway documentation: https://developers.cloudflare.com/ai-gateway/
- Cloudflare AI Gateway universal endpoint: https://developers.cloudflare.com/ai-gateway/providers/
- Workers KV documentation: https://developers.cloudflare.com/kv/
