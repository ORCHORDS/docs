# agent-observability-2026

- **Issue**: "Why did the agent do that?" is the one question that matters when production breaks. Without standardized spans, every framework invents its own telemetry, and you can't switch backends without re-instrumenting. OpenTelemetry GenAI semantic conventions (in **Development** status as of v1.42, June 2026) are the converging answer.
- **Date**: 2026-08-09
- **Repo**: example-org/example-repo
- **Author**: kb-batch-2
- **Status**: Active; complements `documentation/categories/patterns/distributed-tracing-otel.md` and `documentation/categories/patterns/agent-eval-2026.md`.

## Symptom

- A production agent does the wrong thing. You have no trace, or you have a trace but the attribute names are framework-specific, so you can't search across the org's other agents.
- Switching observability backends means re-instrumenting every agent.
- Your token-usage dashboard disagrees with your cost dashboard. One of them is wrong; you don't know which.
- A tool call's output is invisible in the trace. You know the agent made a tool call; you don't know what came back.

## Root cause

Before 2024, every framework (LangChain, LlamaIndex, CrewAI, OpenAI Agents SDK) invented its own telemetry. OpenTelemetry started a GenAI working group in April 2024 to fix the fragmentation. By mid-2026, the conventions are shipping in real instrumentation across providers and frameworks — but they are still **pre-stable / Development** status, with no 1.0 release.

## The five load-bearing span types

| Span name pattern | What it represents | Key attributes |
|---|---|---|
| `chat {gen_ai.request.model}` (e.g., `chat gpt-5.1`) | Single model invocation | `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.response.finish_reasons` |
| `embeddings {gen_ai.request.model}` | Vector generation | Same model + token attributes |
| `execute_tool {gen_ai.tool.name}` | Agent-initiated tool call | `gen_ai.tool.name`, `gen_ai.tool.call.id` |
| `invoke_agent {gen_ai.agent.name}` | One reasoning cycle in a multi-step agent | `gen_ai.agent.name` (parents the `chat` and `execute_tool` subtree) |
| `create_agent {gen_ai.agent.name}` | Agent construction | (rare in traces) |

The agent and framework spans capture the causal chain that matters: which LLM call produced which tool call, which tool call's output fed which retry, which retry finally settled on a result. Each tool call, LLM invocation, and retrieval step is a child span of the parent agent step.

## The minimum attribute set (split into four orthogonal buckets)

- **Provider identification**: `gen_ai.provider.name` (canonical: `openai`, `anthropic`, `aws.bedrock`, `azure.ai.openai`, `google.genai`) and `gen_ai.system` (human, e.g. `Anthropic`).
  - In 2026, **emit both**. Older collectors still read `gen_ai.system`.
- **Operation**: `gen_ai.operation.name` ∈ {`chat`, `text_completion`, `embeddings`, `execute_tool`, `invoke_agent`, `create_agent`}.
- **Request**: `gen_ai.request.model`, optionally `gen_ai.request.max_tokens`, `temperature`, `top_p`, `stop_sequences`.
- **Response**: `gen_ai.response.model` (may differ if the provider routes to a variant), `gen_ai.response.id`, `gen_ai.response.finish_reasons`.
- **Usage**: `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens`.

## The two mandatory metrics

- `gen_ai.client.operation.duration` (histogram, seconds) — latency of a GenAI client operation.
- `gen_ai.client.token.usage` (histogram, broken down by input and output) — consumption.

These two are the floor. Export them or you cannot reason about cost or speed.

## MCP tracing (OTel v1.39, late 2025)

OpenTelemetry added a dedicated sub-spec for MCP servers. MCP spans **enrich** existing `execute_tool` spans rather than duplicating them.

- **Required**: `mcp.method.name` (values: `tools/call`, `tools/list`, `initialize`, …)
- **Recommended**: `mcp.protocol.version` (e.g., `2025-06-18`), `mcp.session.id`, `mcp.resource.uri`

## Provider-specific conventions

- Anthropic, OpenAI, Azure AI Inference, AWS Bedrock each have their own attribute vocabulary on top of the core spec.
- Anthropic tool-call IDs are prefixed `toolu_`; OpenAI are prefixed `call_`. Both fit in `gen_ai.tool.call.id`.
- For streaming responses, `gen_ai.usage.*_tokens` may be empty if the call never completed. Track separately if cost-sensitive.

## The two-hour setup checklist

1. Install the OpenTelemetry SDK, an OTLP exporter, and your framework's GenAI instrumentation.
2. Point the exporter at an **OpenTelemetry Collector**, not directly at the backend. Redaction and sampling have a home there.
3. Run one agent request and confirm `gen_ai.provider.name`, `gen_ai.request.model`, and both `gen_ai.usage.*_tokens` actually land.
4. Add the attributes the spec omits: `agent.loop.iteration`, `app.tenant.id`, a derived tool-success flag.
5. Verify **context propagation**: tool and retrieval spans are children of the parent model span, not siblings.
6. Add a Collector **redaction processor** so prompt and completion text is stripped before anything leaves your boundary.
7. Configure **tail-based sampling**: keep 100% of error traces, sample clean ones.
8. Wire one alert on **token budget**: sum `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens` per window against a threshold.

## The 2026 observability platform landscape (grouped by deployment)

| Deployment | Platforms |
|---|---|
| **Self-hosted / OSS** | Arize Phoenix (Apache 2.0, OTel-native), Langfuse (MIT), Comet Opik (Apache 2.0), Inspect AI (MIT) |
| **Managed SDK** | LangSmith (LangChain-native), Braintrust, Maxim AI, Galileo |
| **Proxy / gateway** | Cloudflare AI Gateway, Portkey, Helicone (mostly cost/rate telemetry; not full tracing) |
| **BYO OTel Collector → backend** | OpenTelemetry Collector → Tempo / Jaeger / Honeycomb / Datadog / New Relic |

The 2026 production pattern: emit OTel GenAI semconv once at the agent boundary, then route via Collector to whichever backend you run. Switching backends (Tempo → Honeycomb, Phoenix → Langfuse) is a config change, not a code change.

## Verification

- **Span coverage**: 100% of `chat` calls have a `gen_ai.usage.*_tokens` attribute. Anything missing is a hidden cost.
- **Parent-child integrity**: every `execute_tool` span has a `chat` parent; every `chat` has an `invoke_agent` ancestor.
- **Context propagation**: a request that fans out to a sub-agent carries the same trace context.
- **Collector redaction**: prompt text in spans is `[REDACTED]` before the Collector exporter. Verify by inspecting the exporter output, not the agent.
- **Sample rate on errors**: 100% of failed runs are kept; clean runs are sampled at 1–5%.
- **Cost reconciliation**: `gen_ai.usage.input_tokens × rate` from traces matches the provider bill within 5%.

## Gotchas

- **`gen_ai.*` attributes are still in Development status.** Names can change without a major version bump. Pin the spec version; subscribe to the changelog.
- **Dual-emit is the safety net.** Set `OTEL_SEMCONV_STABILITY_OPT_IN` so instrumentation emits both legacy and latest-experimental schemas simultaneously. Let backends migrate on their own clocks.
- **Streaming calls lose the token count if they never complete.** A 30-minute stream that times out is invisible to `gen_ai.usage.*_tokens`. Track start/end separately.
- **Structured content (prompts, tool arguments) is intentionally not in span attributes.** It moves to log-correlated events to avoid bloat. Don't put PII in span attributes; that path is unredacted by default.
- **`gen_ai.system` is the legacy attribute; `gen_ai.provider.name` is the modern one.** Emit both until your collectors all upgrade.
- **MCP tracing depends on the MCP server emitting OTel.** If your MCP server doesn't, the `execute_tool` span is the only signal you have. Pick MCP servers that emit OTel.
- **Tail-based sampling is essential at scale.** Head-based sampling drops the error traces you actually need.
- **Don't tail-sample on `gen_ai.response.finish_reasons`** — it might be missing in the early life of a stream. Sample on error type or HTTP status instead.
- **The OTel Collector is the policy boundary.** Redaction, sampling, and routing happen there, not in your agent. If you push those into the agent, you have an unredacted path somewhere.

## Related

- `documentation/categories/patterns/distributed-tracing-otel.md` — the OTel substrate
- `documentation/categories/patterns/agent-eval-2026.md` — observability feeds the evaluator
- `documentation/categories/patterns/structured-logging.md` — log shape for events
- `documentation/categories/patterns/mcp-server-patterns.md` — MCP servers that emit OTel
- `documentation/categories/cloudflare/ai-gateway-best-practices.md` — the proxy/gateway layer

## Source URLs (verified 2026-08-09)

- OpenTelemetry GenAI semantic conventions (Development status, v1.42) — https://opentelemetry.io/docs/specs/semconv/gen-ai/
- "OpenTelemetry GenAI Conventions: The 2026 Default Schema for Agent Observability" (agentmarketcap) — https://agentmarketcap.ai/blog/2026/07/13/opentelemetry-genai-semantic-conventions-agent-observability-standard
- "Observability for Agents: OpenTelemetry GenAI Conventions" (pondero) — https://pondero.ai/enterprise/guides/observability-agents-opentelemetry-genai/
- "OpenTelemetry GenAI Semantic Conventions: Tracing AI Agents" (veraexmachina) — https://veraexmachina.com/tech/opentelemetry-genai-agent-observability-production/
- "Agent observability with OpenTelemetry GenAI semconv in 2026" (jacar) — https://jacar.es/en/agent-observability-with-opentelemetry-genai-semconv-in-2026/
- "AI Agent Observability: Tracing & Monitoring in 2026" (digitalapplied) — https://www.digitalapplied.com/blog/ai-agent-observability-2026-tracing-monitoring-stack-guide
- semantic-conventions-genai repo — https://github.com/open-telemetry/semantic-conventions-genai
