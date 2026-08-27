# Agent Ephemeral State

Keep short-lived run state separate from durable memory.

## Checklist
- Identify values that only matter during one run.
- Expire temporary state at terminal completion.
- Avoid promoting transient errors into long-term memory.
- Make restart behavior explicit.

## Primary sources
- OpenAI `openai/openai-agents-python` run/session concepts.
- Cloudflare `cloudflare/agents` stateful execution.
