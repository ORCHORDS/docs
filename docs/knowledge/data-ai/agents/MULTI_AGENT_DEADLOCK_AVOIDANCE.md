# Multi-Agent Deadlock Avoidance

Prevent agents from waiting on each other indefinitely.

## Checklist
- Define ownership of each pending dependency.
- Bound wait time and delegation depth.
- Detect circular dependency chains.
- Provide an explicit terminal escalation path.

## Primary sources
- OpenAI `openai/openai-agents-python` multi-agent workflows.
- Cloudflare `cloudflare/agents` orchestration patterns.
