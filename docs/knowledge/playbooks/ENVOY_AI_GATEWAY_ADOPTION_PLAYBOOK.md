# Envoy AI Gateway LLM Proxy Adoption Playbook

## Purpose

Replace direct provider integrations with the Envoy AI Gateway so that all LLM traffic flows through a single, observable, rate-limited, OpenAI-compatible proxy with workload-identity-based credential management.

## Audience

Platform engineers, AI platform owners, application teams migrating from per-service provider SDKs.

## Pre-conditions

- Envoy AI Gateway ≥ 0.3 deployed with an `InferencePool` per LLM family.
- Workload identity (SPIFFE/SPIRE, AWS IRSA, GCP WIF) configured for each upstream provider.
- Service mesh (Istio or Linkerd) installed if the gateway is east-west inside the cluster.
- A baseline of representative traffic to evaluate parity (latency, token consumption, cost).

## Procedure

1. **Discovery**: inventory every direct call to OpenAI / Anthropic / Bedrock / Vertex / vLLM in the codebase. Use `grep` for SDK-specific endpoints and a CNM-like contract test harness.
2. **Model family mapping**: for each upstream, map the application-facing model name (e.g. `gpt-4o`) to an `InferencePool` alias in the gateway.
3. **Credential handoff**: replace static API keys with workload-identity federation per upstream; document in `policies/ai-gateway/credentials.md`.
4. **SDK swap**: change each application to call the gateway endpoint (`https://ai-gateway.<cluster>/v1`) instead of the provider URL. Keep the OpenAI-compatible request/response shape so existing SDK code works unchanged.
5. **Quota rollout**: start with generous `tokenRateLimitPolicy` and tighten per principal based on observed usage; do not enforce hard quotas in the first 7 days.
6. **Observability**: validate that the gateway exposes `ai_gateway_requests_total`, `ai_gateway_tokens_total`, and `ai_gateway_request_duration_seconds` to your dashboards.
7. **Cost guardrails**: enable cost attribution labels (`team`, `product_area`) on the gateway filter so that chargeback reports can be generated monthly.
8. **Cutover**: shift traffic in waves (10 %, 50 %, 100 %) with at least 24 h of parity metrics between each step.

## Rollback

- Revert the application endpoint to the upstream provider URL; the gateway's `AIGatewayRoute` resource can remain in place.
- If a model alias becomes unavailable, disable the corresponding `InferencePool` with `enabled: false`; clients fail-fast with a 503 carrying the standard OpenAI error envelope.

## References

- Envoy AI Gateway documentation — https://gateway.envoyproxy.io/ai-gateway/
- Internal: Batch 100 reference card `ENVOY_AI_GATEWAY_GOVERNANCE.md`.
