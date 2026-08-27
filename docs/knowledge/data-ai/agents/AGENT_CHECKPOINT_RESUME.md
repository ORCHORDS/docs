# Agent Checkpoint Resume

Checkpoint long-running work so interrupted runs can resume from known state.

## Checklist
- Record completed steps and pending dependencies.
- Make checkpoints idempotent.
- Validate external state before resuming.
- Prevent replay of already completed side effects.

## Primary sources
- OpenAI `openai/openai-agents-python` sandbox/long-running concepts.
- Cloudflare `cloudflare/agents` workflow patterns.
