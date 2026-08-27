# Agent Event Streams

Represent incremental agent progress with explicit event types.

## Checklist
- Define event names and ordering assumptions.
- Separate user-facing events from internal telemetry.
- Handle reconnects and duplicate delivery.
- Preserve terminal success, cancellation, and failure events.

## Primary sources
- OpenAI `openai/openai-agents-python`.
- Cloudflare `cloudflare/agents`.
