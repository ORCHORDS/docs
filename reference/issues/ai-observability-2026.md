# ai-observability-2026

**Issue:** A team runs LLM inference in production. The team needs to debug why a particular user got a particular output, why latency spiked, why the model started hallucinating. The team debates Langfuse, Helicone, Phoenix, Datadog LLM Observability. The team needs the 2026 reference for LLM observability.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 observability signals

1. **Traces.** Request, response, latency, token usage, model version.
2. **Logs.** Full prompt/response (with PII redaction), tool calls, errors.
3. **Metrics.** Latency p50/p95/p99, tokens/sec, error rate, cost per request.
4. **Evaluations.** Online evals (LLM-as-judge, heuristic) on production traffic.
5. **User feedback.** Thumbs up/down, regeneration rate, escalation.

## The 5 OpenTelemetry GenAI semantic conventions

1. `gen_ai.system` (e.g., openai, anthropic).
2. `gen_ai.request.model`.
3. `gen_ai.usage.input_tokens` / `output_tokens`.
4. `gen_ai.response.finish_reasons`.
5. `gen_ai.agent.name` (for agentic systems).

## The 5 platforms

1. **Langfuse.** OSS, self-hostable, OpenTelemetry-native.
2. **Helicone.** LLM proxy with observability, caching, evals.
3. **Arize Phoenix.** OSS tracing + evals.
4. **Datadog LLM Observability.** Commercial, integrated with Datadog APM.
5. **OpenLLMetry.** OSS instrumentation, vendor-neutral.

## The 5 best practices

1. **OpenTelemetry-native** for portability across vendors.
2. **PII redaction** in traces and logs (production may contain sensitive data).
3. **Sample rate** based on traffic (10-100% for traces, 100% for errors).
4. **Online evals** for known failure modes (hallucination, toxicity, bias).
5. **User feedback loop** in UI (thumbs up/down, regenerations).

## The 5 anti-patterns

1. **Logging full prompts in production** without redaction. PII leaks.
2. **No token tracking** - cost surprises.
3. **No latency tracking** - SLA breaches invisible.
4. **Eval as one-time check** - production drift undetected.
5. **Vendor lock-in** without OpenTelemetry. Migration cost.

## Gotchas

- PII redaction is hard; consider not logging inputs at all for sensitive domains.
- Some observability platforms double-proxy, adding latency.
- Eval LLM-as-judge is itself an LLM call, can fail or hallucinate.
- Trace sampling must keep all error traces, not sample them out.
- Online eval can be expensive; sample 1-10% of traffic.

## Source URLs (verified 2026-08-10)

- https://opentelemetry.io/docs/specs/semconv/gen-ai/
- https://langfuse.com/
- https://docs.helicone.ai/
- https://docs.arize.com/phoenix
- https://github.com/traceloop/openllmetry
- https://www.datadoghq.com/product/llm-observability/
