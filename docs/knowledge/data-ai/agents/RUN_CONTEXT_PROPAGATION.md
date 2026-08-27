# Run Context Propagation

Pass only the context required by nested agents and tools.

## Checklist
- Separate user-visible context from execution metadata.
- Keep correlation identifiers stable.
- Avoid copying stale mutable state between runs.
- Document which context is inherited and which is recomputed.

## Primary sources
- OpenAI `openai/openai-agents-python`.
- Cloudflare `cloudflare/agents`.
