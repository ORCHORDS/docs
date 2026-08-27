# Agent Session Migration

Move agent session state between runtime versions without losing required context.

## Checklist
- Version durable session formats.
- Define forward and rollback compatibility.
- Validate migrated state before reuse.
- Preserve a migration audit trail.

## Primary sources
- OpenAI `openai/openai-agents-python` sessions.
- Cloudflare `cloudflare/agents` durable state patterns.
