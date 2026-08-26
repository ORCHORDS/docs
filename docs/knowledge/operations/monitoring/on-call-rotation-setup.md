# on-call-rotation-setup

**Issue:** Designing sustainable on-call rotations that avoid burnout while maintaining coverage
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Single engineer on-call for weeks leads to burnout. Need fair, documented rotation with coverage for weekends and holidays.

## Pattern / Solution
Use weekly rotations at minimum. Define primary and secondary on-call. Handoff meeting (15min) between outgoing and incoming: review open incidents, pending changes, known fragile areas. Compensate on-call with time-off or pay. Track pages per shift — target fewer than 2 actionable pages per night. Shadow rotation for new engineers before primary duty. Document on-call calendar 3 months ahead.

## Gotchas
Never put someone on-call for a system they have not been trained on. Holiday coverage needs explicit planning. Engineers on leave should be automatically removed from rotation. Measure on-call burden as a team health metric.

## Related
escalation-policy-design, pagerduty-integration, alert-severity-levels, alerting-runbook-linking
