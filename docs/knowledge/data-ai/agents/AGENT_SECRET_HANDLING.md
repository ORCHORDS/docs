# Agent Secret Handling

Keep secrets out of agent-visible context unless the runtime strictly requires them.

## Checklist
- Prefer tool-side secret use over prompt injection.
- Do not persist secrets in session summaries or traces.
- Redact sensitive values from errors.
- Review new tools for accidental secret exposure.

## Primary sources
- OpenAI `openai/openai-agents-python` tool architecture.
- Cloudflare `cloudflare/agents` deployment/runtime patterns.
