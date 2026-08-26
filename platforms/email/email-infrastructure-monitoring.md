# email-infrastructure-monitoring

**Issue:** Monitoring email infrastructure health across sending IPs, queues, and delivery rates
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Email infrastructure failures (queue buildup, IP blacklisting, ESP outages) need immediate detection to minimize impact.

## Pattern / Solution
Key metrics to monitor:
| Metric | Alert threshold |
|---|---|
| Queue depth | > 1000 messages for > 5 minutes |
| Send error rate | > 1% in 5-minute window |
| Delivery rate | < 95% in 1-hour window |
| Bounce rate | > 5% spike in 1-hour window |
| IP blacklist | Any new listing |
| ESP API latency | > 2s p99 |

Monitoring stack:
- CloudWatch / Datadog for queue and API metrics.
- MXToolbox Blacklist Monitor for IP reputation.
- PagerDuty / OpsGenie for on-call alerting.
- Google Postmaster Tools weekly review.

Runbook trigger: any alert on send error rate or bounce rate spike requires immediate investigation.

## Gotchas
- Queue depth alone isn't alarming; pair with age of oldest message (messages > 1 hour old is critical).
- Different ESPs have different API behaviors; test your monitoring against staging ESP endpoint.
- IP blacklisting affects only some receiving servers; delivery rate drop may not catch all blacklists.
- Monitor each sending IP separately; one bad IP in a pool can cause intermittent issues hard to detect in aggregate.

## Related
- email-deliverability-audit, postmaster-tools-setup, email-queue-architecture, ip-warming-strategy
