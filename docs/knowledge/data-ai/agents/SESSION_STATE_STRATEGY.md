# Session State Strategy

Define how conversation and run state persists across agent executions.

## Checklist
- Separate transient run state from durable session state.
- Define retention and deletion rules.
- Avoid persisting secrets unless required.
- Test resume, reset, and concurrent-session behavior.

## Primary sources
- OpenAI `openai/openai-agents-python` sessions.
- Cloudflare `cloudflare/agents` stateful agents.
