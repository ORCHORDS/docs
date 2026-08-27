# Tool Schema Design

Design agent tools with narrow, typed contracts.

## Checklist
- Use explicit required fields and constrained enums.
- Reject unknown or malformed inputs.
- Keep side-effecting tools separate from read-only tools.
- Return structured errors that agents can reason about safely.

## Primary sources
- OpenAI `openai/openai-agents-python` tool concepts.
- Cloudflare `cloudflare/agents` agent/tool patterns.
