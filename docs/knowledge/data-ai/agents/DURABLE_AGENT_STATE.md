# Durable Agent State

Store only the agent state that must survive process or request boundaries.

## Checklist
- Separate durable facts from temporary execution data.
- Version the state schema.
- Define retention and reset behavior.
- Test concurrent updates and restart recovery.

## Primary source
- Cloudflare `cloudflare/agents` durable/stateful agent design.
