# Agent Cancellation Propagation

Propagate cancellation through nested agent work.

## Checklist
- Make cancellation observable to child tasks.
- Stop creating new work after cancellation.
- Define cleanup behavior.
- Record the final cancellation reason.

## Primary sources
- OpenAI `openai/openai-agents-python`.
- Cloudflare `cloudflare/agents`.
