# Agent Queue Backpressure

Prevent queued agent work from growing faster than the runtime can process safely.

## Checklist
- Define queue depth and age thresholds.
- Shed or defer non-critical work predictably.
- Preserve ordering only where the workflow requires it.
- Monitor retry storms and repeated scheduling.

## Primary source
- Cloudflare `cloudflare/agents` durable/workflow execution patterns.
