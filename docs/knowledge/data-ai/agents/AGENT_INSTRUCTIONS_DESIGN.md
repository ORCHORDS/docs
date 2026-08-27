# Agent Instructions Design

Use this pattern to make agent instructions explicit and testable.

## Checklist
- Define scope, trigger, allowed actions, output contract, and failure boundary.
- Separate durable policy from task-specific instructions.
- Keep tool permissions minimal and state assumptions explicit.
- Test ambiguous requests, conflicting instructions, and recovery paths.

## Primary sources
- OpenAI `openai/openai-agents-python`.
- Cloudflare `cloudflare/agents`.
