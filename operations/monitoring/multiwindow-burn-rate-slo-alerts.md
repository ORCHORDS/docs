# Multiwindow burn-rate alerts for SLOs

**Category:** Monitoring
**Author:** ORCHORDS
**Primary source:** [Google SRE: Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)

## Problem

Alerting whenever an instantaneous error rate exceeds an SLO creates noisy pages; alerting only over a long window clears too slowly. SLO alerts should reflect significant error-budget consumption and whether the incident is still active.

## Practice

- Define a user-visible SLI, SLO period, error budget, and minimum traffic condition before choosing alert thresholds.
- Alert on budget burn rate rather than the raw SLO target alone.
- Pair each long burn window with a short confirmation window. A practical starting ratio is a short window one-twelfth of the long window.
- Use distinct urgency levels: fast, high burn can page; slower sustained burn can create a ticket.
- Suppress lower-priority alerts when a higher-severity burn alert already represents the same incident.
- Tune all starting values against real traffic volume, incident response expectations, and the cost of false pages.

## Verification

1. Replay a short total outage, a sustained partial outage, and a transient spike against the rules.
2. Confirm severe active burn pages promptly and clears promptly after recovery.
3. Confirm slower budget depletion creates the intended non-page work item.
4. Test low-traffic periods so a few requests cannot produce a misleading page.

## Failure modes

- A single long window stays firing long after recovery.
- A duration clause misses intermittent but damaging bursts.
- Multiple alert rules page for the same event.
- An SLO alert is built from infrastructure signals that do not represent user experience.

## Related

- [Google SRE: Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
