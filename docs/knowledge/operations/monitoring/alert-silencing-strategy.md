# alert-silencing-strategy

**Issue:** Temporarily suppressing alerts during maintenance, deployments, or known incidents
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Planned maintenance triggers cascade of alerts. Engineers acknowledge and clear manually. Need systematic silencing.

## Pattern / Solution
Use Alertmanager silences for planned maintenance: amtool silence add with matchers, duration, and comment. Integrate silence creation into deployment pipeline — silence service alerts during rollout, auto-expire after deployment. For recurring maintenance use alert routing with time-based matchers. Track all silences with author, reason, and expiry.

## Gotchas
Silences expire automatically — always set duration. Never create open-ended silences; they accumulate and hide real problems. amtool silence list to audit active silences. Remove or expire silences immediately after maintenance completes.

## Related
alert-inhibition-rules, alert-noise-reduction, alert-grouping-patterns
