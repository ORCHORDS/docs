# alert-severity-levels

**Issue:** Defining consistent alert severity tiers so on-call knows urgency without reading the full alert
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
All alerts page the same person at the same urgency. Engineers get fatigued and ignore real critical issues.

## Pattern / Solution
Define four levels: P1/Critical — immediate page, revenue impact or full outage, response SLA 5min. P2/High — page with delay, degraded functionality, response SLA 30min. P3/Medium — ticket in queue, non-user-facing, response SLA next business day. P4/Low — informational, batch review weekly. Map levels to routing: P1 calls phone, P2 pages app, P3 creates ticket, P4 goes to dashboard only.

## Gotchas
Start conservative — it is easier to downgrade alerts than convince engineers that pages are real. Review severity assignments quarterly. P1 should be rare (fewer than 2 per week per service). Include severity label in every alert rule.

## Related
alerting-runbook-linking, alert-noise-reduction, pagerduty-integration, on-call-rotation-setup
