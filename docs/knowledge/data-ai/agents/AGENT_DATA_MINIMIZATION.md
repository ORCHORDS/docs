# Agent Data Minimization

Give agents only the data required for the current task.

## Checklist
- Select fields instead of forwarding whole records.
- Expire temporary context when the task ends.
- Avoid logging unnecessary user content.
- Reassess data scope when tools or workflows expand.

## Primary sources
- OpenAI `openai/openai-agents-python` sessions/tracing patterns.
- Cloudflare `cloudflare/agents` stateful execution patterns.
