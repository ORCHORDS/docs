# Durable Agent WebSockets

Define how persistent connections interact with durable agent state.

## Checklist
- Track connection lifecycle separately from agent lifecycle.
- Reconcile reconnecting clients with current state.
- Handle duplicate or late messages.
- Preserve explicit terminal states.

## Primary source
- Cloudflare `cloudflare/agents` realtime/stateful patterns.
