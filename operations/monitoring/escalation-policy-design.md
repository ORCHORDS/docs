# escalation-policy-design

**Issue:** Defining escalation paths so unacknowledged alerts reach someone who can act
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
On-call engineer misses a page; no one else is notified; outage extends. Need automatic escalation.

## Pattern / Solution
Define escalation tiers per service: T1 primary on-call (immediate), T2 secondary on-call (after 5min), T3 team lead (after 15min), T4 VP Engineering (after 30min, P1 only). Configure in alerting platform with explicit timeouts. Separate escalation policies per team. For P2/P3, escalate to team channel before individual pages.

## Gotchas
Test escalation paths quarterly with drills. Escalation to managers should be automatic for P1 with no acknowledgement after 30min. Adjust timeouts based on your actual response SLA. Document who is in each tier so substitutions during vacations are clear.

## Related
on-call-rotation-setup, pagerduty-integration, alert-severity-levels
