# on-call-handoff-checklist

**Issue:** Ensuring complete knowledge transfer between outgoing and incoming on-call engineers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Incoming on-call engineers start their rotation without context on active incidents, recent changes, or known fragile areas. When something breaks they spend time reconstructing context rather than resolving.

## Pattern / Solution
Conduct a 15-minute handoff meeting at every rotation change covering five areas: (1) Active incidents and their current status, workarounds, and next steps. (2) Recent deployments in the last 48 hours and any observed side effects. (3) Known fragile systems or elevated risk areas to watch closely. (4) Scheduled maintenance windows or planned changes during the upcoming rotation. (5) Any alerts that fired but were judged as noise — so the incoming engineer knows context if they fire again. Document the handoff in a shared log (Confluence page, Slack thread, or Notion) with timestamp and names. Outgoing engineer remains available by message for the first 2 hours of the new rotation.

## Gotchas
Do not skip handoffs for short rotations or during low-incident periods — the next incident will be worse without context. Handoff notes should be written down, not just verbally communicated — verbal handoffs degrade with each rotation. If the outgoing engineer is unavailable (sick, emergency) designate a backup who has read the on-call log. Make handoff notes findable — link from the on-call rotation schedule.

## Related
on-call-rotation-setup, escalation-policy-design, alerting-runbook-linking, deployment-event-tracking
