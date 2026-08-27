# Agent Idempotency

Design repeated agent requests so duplicate delivery does not create duplicate work.

## Checklist
- Detect repeated requests where possible.
- Reuse prior confirmed results when safe.
- Separate replayable reasoning from one-time actions.
- Test duplicate and replay scenarios.

## Primary sources
- OpenAI `openai/openai-agents-python`.
- Cloudflare `cloudflare/agents`.
