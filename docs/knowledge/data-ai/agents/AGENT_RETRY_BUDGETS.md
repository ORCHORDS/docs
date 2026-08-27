# Agent Retry Budgets

Bound retries so repeated failures do not expand latency or cost without limit.

## Checklist
- Set retry counts per failure class.
- Use delay between transient retries.
- Stop when the retry budget is exhausted.
- Record the final outcome for diagnosis.

## Primary sources
- OpenAI `openai/openai-agents-python`.
- Cloudflare `cloudflare/agents`.
