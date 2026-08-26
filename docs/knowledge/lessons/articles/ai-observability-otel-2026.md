# ai-observability-otel-2026

**Issue:** A team deploys an LLM agent. A user reports "the agent is slow and the answers are bad." The team has no traces, no token counts, no prompt-version correlation. Debugging is guesswork.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

LLM applications need a different observability stack than traditional services. A stack trace doesn't tell the whole story — you need to trace across prompt construction, model inference, retrieval steps, tool calls, and evaluation scoring. Teams that adopt traditional APM find it misses the LLM-specific concerns.

## Root cause

OpenTelemetry's GenAI Semantic Conventions (stabilized late 2025, native in OTel 1.20) provide a vendor-neutral schema for AI workloads. The key attributes standardize across providers:

- `gen_ai.system` — provider (openai, anthropic, bedrock)
- `gen_ai.request.model` — model name
- `gen_ai.usage.input_tokens` / `output_tokens` — token counts
- `gen_ai.response.finish_reasons` — why the model stopped

A team that does not instrument with these attributes cannot attribute cost, latency, or quality issues to specific pipeline steps.

## The five instrumentation layers

For a production LLM system, instrument at five layers:

1. **LLM call spans** — wrap each model invocation in a span named with the `gen_ai.` prefix. Record model, tokens, latency.
2. **Retrieval spans** — for RAG, instrument embedding lookup, vector store query, and reranking as separate spans.
3. **Tool call spans** — nest under the reasoning span that triggered the tool. Record arguments, results, latency.
4. **Evaluation scores** — attach LLM-as-judge scores to the generation span so they correlate with the full trace context.
5. **Sanitization** — strip PII from prompts and completions in the instrumentation wrapper, not per-call.

## The minimum instrumentation

```python
from opentelemetry import trace
tracer = trace.get_tracer("my-llm-app")

with tracer.start_as_current_span("llm.chat") as span:
    span.set_attribute("gen_ai.system", "anthropic")
    span.set_attribute("gen_ai.request.model", "claude-sonnet-4")
    response = client.messages.create(...)
    span.set_attribute("gen_ai.usage.input_tokens", response.usage.input_tokens)
    span.set_attribute("gen_ai.usage.output_tokens", response.usage.output_tokens)
```

Tools like Langfuse, Arize Phoenix, and Weights & Biases Weave provide drop-in instrumentation for popular frameworks (LangChain, LlamaIndex, CrewAI) using these conventions.

## The five operational practices

- **Sample 10-30% in production.** 100% sampling in dev/staging; tail-based sampling on errors or high latency in prod.
- **Tag every call with feature, team, user tier.** Most providers support custom metadata; store in observability layer if not.
- **Pin prompt versions in a registry.** Langfuse, PromptLayer, or Git-tracked YAML. Tag every call with the prompt version.
- **Set budget alerts at the provider level.** Hard spending limits at the account level; soft alerts at the feature level.
- **Alert on per-intent anomalies.** A rolling average can mask a specific intent cluster degrading.

## The 80/20 starter stack

If starting from scratch:

1. Instrument with OpenTelemetry using the gen_ai semantic conventions
2. Ship to Langfuse (generous free tier) — immediate visibility
3. Add LLM-as-judge for top 3 critical user flows
4. Set budget alerts at the provider level
5. Tag everything with feature and team from day one

## Verification

The tell that observability is working:

- A user reports a bad response; the team pulls the trace and sees the exact prompt, model, tokens, and tool calls
- Cost dashboards show per-feature, per-team, per-model breakdown
- A model swap or prompt change shows up immediately in the metric stream
- A latency spike is attributable to retrieval, generation, or tool call by span

The tell it isn't:

- "The agent is slow" — no data on which span
- Token costs are aggregated, not per-request
- A model swap ships with no observed change in metrics
- Production debugging is log-grepping

## Gotchas

- **Never log raw completion as a span attribute in production.** Span attributes are indexed long-term. Use span events for large content.
- **Sanitize in the wrapper, not per-call.** A central scrubber ensures no call bypasses the redaction.
- **Sample intelligently.** 100% sampling in production is expensive; tail-based on errors captures what matters.
- **Tag from day one.** Retro-tagging after 6 months is impossible.
- **Pin semantic convention versions.** Treat as a versioned contract; update regularly.

## Related

- `lessons/ai-cost-finops-2026.md` — cost data feeds the metrics
- `lessons/ai-rollout-strategy-2026.md` — rollout metrics use these traces
- `lessons/agent-eval-2026.md` — eval scores live on the spans

## Source URLs (verified 2026-08-10)

- https://opentelemetry.io/blog/2026/genai-observability/
- https://devstarsj.github.io/ai/mlops/observability/2026/04/24/llm-observability-production-monitoring-guide-2026/
- https://mlflow.org/articles/setting-up-llm-observability-pipelines-in-2026/
- https://dev.to/johalputt/deep-dive-how-opentelemetry-120-and-langsmith-2026-power-ai-observability-for-llm-powered-apis-3cj2
- https://openobserve.ai/blog/opentelemetry-for-llms/
