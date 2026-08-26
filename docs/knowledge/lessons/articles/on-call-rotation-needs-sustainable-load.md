# on-call-rotation-needs-sustainable-load

**Issue:** Unsustainable on-call load causes engineer burnout, attrition, and degraded incident response quality
**Date:** 2026-08-11
**Status:** documented

## What happened
A three-person engineering team maintained a 24/7 on-call rotation. Over six months, each engineer was paged an average of 14 times per week, including nights and weekends. Two engineers resigned citing on-call exhaustion within the same quarter. The remaining team was further overloaded, accelerating the spiral. A fourth engineer could not be hired fast enough. Service quality declined as fatigued engineers made errors during incidents.

## The lesson
On-call is sustainable only when the alert volume is low enough that on-call weeks are not dreaded, and the rotation is large enough that engineers recover before their next shift. Target: fewer than 5 actionable alerts per on-call week, and a rotation large enough that no engineer is on-call more than once every 4-5 weeks.

## Why it matters
Burned-out engineers leave. Replacing an experienced engineer costs 6-12 months of productivity. Fatigued engineers in incidents make mistakes. Alert fatigue leads to real alerts being ignored. The on-call experience is a recruiting signal — bad on-call conditions are shared widely.

## How to apply
- [ ] Measure alert volume per on-call week. If it exceeds 5 actionable alerts, treat it as a P1 reliability issue.
- [ ] Categorize every alert: actionable (requires human response), noisy (fires but resolves itself), duplicate. Delete noisy and duplicate alerts.
- [ ] Ensure the rotation has enough engineers (6+ ideal, 4+ minimum) that nobody is on-call more than once per month.
- [ ] Pay on-call compensation and offer time off after particularly heavy weeks.
- [ ] Run regular alert reviews: every alert that fired in the last month must justify its existence.

## Related
- `write-the-runbook-before-the-incident.md`
- `blameless-culture-produces-better-postmortems.md`
