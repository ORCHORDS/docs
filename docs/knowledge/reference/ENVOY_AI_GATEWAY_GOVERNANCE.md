---
title: Envoy AI Gateway LLM Proxy Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-07
review-cycle: 180 days
next-review: 2027-03-06
source: https://gateway.envoyproxy.io/ ; https://github.com/envoyproxy/ai-gateway ; https://docs.envoyproxy.io
---

# Envoy AI Gateway LLM Proxy Version Governance

## 1. Purpose

This reference card governs the lifecycle of the Envoy AI Gateway — an OSS LLM-aware proxy built on Envoy Gateway — when used to route, observe, rate-limit, and secure traffic to upstream LLM providers (OpenAI, Anthropic, Bedrock, Vertex AI, self-hosted vLLM/TGI). It applies to platform teams that expose multiple LLM backends behind a unified, OpenAI-compatible API.

## 2. Scope

In scope:

- Envoy AI Gateway ≥ 0.3.x with the `llm` filter extension.
- Upstream providers: OpenAI, Anthropic, AWS Bedrock, GCP Vertex AI, Azure OpenAI, self-hosted vLLM, self-hosted TGI.
- Routing via **AIGatewayRoute** (apiVersion `aigateway.envoyproxy.io/v1alpha1`) and inference-pool selection via `InferencePool`.
- Token-budget policy via the `tokenUsage` filter and `tokenRateLimitPolicy` extension.

Out of scope:

- Custom LLM-aware proxies built on Envoy directly (without the AI Gateway CRDs).
- LLM evaluation or fine-tuning infrastructure.

## 3. Versioning policy

- Pin the Envoy AI Gateway image to a specific patch release (e.g. `envoyproxy/ai-gateway:v0.3.4`) and SHA-256 digest.
- Pin the underlying Envoy version that the gateway ships with; do not mix custom Envoy patches with the gateway binary.
- Maintain a single inference-pool mapping per model family (`gpt-4o`, `claude-3-7-sonnet`, `llama-3-3-70b-instruct`); do not alias provider-specific IDs at the route layer.

## 4. Compatibility matrix

| AI Gateway | Envoy | Kubernetes | Notes |
| --- | --- | --- | --- |
| 0.2.x | 1.31 | 1.27+ | Initial AIGatewayRoute CRD |
| 0.3.x | 1.32 | 1.29+ | InferencePool GA, token-budget policies |
| 0.4.x (preview) | 1.33 | 1.30+ | Streaming response replay |

## 5. Routing and policy

- AIGatewayRoute groups multiple `InferencePool` references and selects between them with weighted priorities.
- Apply `tokenRateLimitPolicy` per principal (API key, JWT sub, SPIFFE ID) with daily, hourly, and per-minute quotas.
- Reject prompts that exceed the model's context window upstream-side rather than letting the upstream provider truncate.

## 6. Provider credentials

- Use workload identity (SPIFFE/SPIRE, GCP Workload Identity Federation, AWS IRSA) to obtain provider credentials; never use static long-lived API keys.
- Rotate any unavoidable static keys via Vault short-lived dynamic secrets with TTL ≤ 24 hours.

## 7. Observability

- Required metrics: `ai_gateway_requests_total{provider,model,status}`, `ai_gateway_tokens_total{provider,model,direction}`, `ai_gateway_request_duration_seconds_bucket{provider,model,le}`, `ai_gateway_token_rate_limit_remaining{principal,model}`.
- Required logs: full request/response audit with PII redaction at the gateway before forwarding to log store.
- Alert on `rate(ai_gateway_requests_total{status="5xx"}[5m]) > 0.01` and on `ai_gateway_token_rate_limit_remaining < 0.1 * quota`.

## 8. Upgrade procedure

1. Roll the gateway image in a canary GatewayClass; route 1 % of traffic to the new instance.
2. Compare token-bucket consumption and error rates between canary and baseline.
3. Promote to 100 % after 24 h of parity and zero SSE/streaming regressions.

## 9. Rollback procedure

- `kubectl rollout undo deployment/envoy-ai-gateway` reverts the canary; no downstream impact because the upstream providers retain conversation state.
- Disable a route with `enabled: false` if a provider is rate-limited at the org level.

## 10. References

- Envoy AI Gateway docs — https://gateway.envoyproxy.io/ai-gateway/
- Envoy Gateway documentation — https://gateway.envoyproxy.io/
- InferencePool KEP — https://gateway-api.sigs.k8s.io/geps/gep-1611/
