# Durable Object Agent Concurrency

Use a clear concurrency model when agent state is coordinated through Durable Objects.

## Checklist
- Define which updates must serialize.
- Avoid hidden cross-instance shared state.
- Make conflict behavior explicit.
- Test concurrent events and reconnects.

## Primary source
- Cloudflare `cloudflare/agents` Durable Objects patterns.
