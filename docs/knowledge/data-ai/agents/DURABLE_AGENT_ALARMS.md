# Durable Agent Alarms

Use scheduled wake-ups for deferred agent work that must survive request boundaries.

## Checklist
- Record why the wake-up is scheduled.
- Re-check current state when the alarm fires.
- Make repeated alarms safe.
- Define cancellation and terminal completion behavior.

## Primary source
- Cloudflare `cloudflare/agents` durable scheduling patterns.
