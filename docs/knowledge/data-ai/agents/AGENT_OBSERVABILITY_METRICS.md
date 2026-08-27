# Agent Observability Metrics

Measure agent behavior using operational metrics, not only final-answer quality.

## Checklist
- Track latency, tool calls, retries, handoffs, and terminal outcomes.
- Segment metrics by workflow and model/runtime version.
- Link metrics to traces where available.
- Avoid collecting unnecessary user content.

## Primary sources
- OpenAI `openai/openai-agents-python` tracing.
- Cloudflare `cloudflare/agents` runtime patterns.
