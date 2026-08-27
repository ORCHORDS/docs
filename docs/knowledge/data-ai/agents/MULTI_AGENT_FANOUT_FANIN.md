# Multi-Agent Fan-Out and Fan-In

Use parallel specialist work only when outputs can be reconciled deterministically.

## Checklist
- Define independent subproblems.
- Bound fan-out width.
- Normalize outputs before aggregation.
- Handle partial failures without hiding them.

## Primary sources
- OpenAI `openai/openai-agents-python` multi-agent patterns.
- Cloudflare `cloudflare/agents` workflow orchestration.
