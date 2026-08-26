# error-budget-slo

**Issue:** SLO + error budget — how to make reliability a decision
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your platform has 99.5% availability. You ship a feature that's
flaky. It causes a 1-hour outage. The team argues: "99.5% means
we can have 3.6 hours of downtime per month, we're fine." The
feature ships. The next outage happens. You never hit your SLO.

## Root cause
**SLOs and error budgets are about making tradeoffs explicit.**
Without a budget, every outage is a free option. With a budget,
the team knows "we've used 50% of our budget, let's stop
shipping risky features."

**Source:** Google SRE book — Service Level Objectives:
https://sre.google/sre-book/service-level-objectives/

> "An SLO is a target level of reliability for a service. ...
> The error budget is 1 - SLO."

## Define SLOs

For a consumer platform:
- **Availability SLO:** 99.9% of requests return 2xx (or 3xx for
  redirects) over 30 days
  - 99.9% = 43 minutes of downtime per month
  - 99.5% = 3.6 hours of downtime per month
- **Latency SLO:** p99 < 500ms for 95% of requests
- **Error budget:** 0.1% = 0.1% of requests can be slow or
  errored

## Track SLOs

```ts
// In your observability layer
async function recordSloMetric(
  endpoint: string,
  status: number,
  durationMs: number,
  env: Env
): Promise<void> {
  const isError = status >= 500;
  const isSlow = durationMs > 500;
  await env.ANALYTICS.writeDataPoint({
    blobs: [endpoint, isError ? 'error' : 'ok', isSlow ? 'slow' : 'fast'],
    doubles: [durationMs],
    indexes: [endpoint],
  });
}
```

In Grafana / Cloudflare Analytics:
- **Availability:** count of 2xx/3xx responses / total responses
- **Latency:** histogram p50, p95, p99
- **Error budget remaining:** `1 - (current_error_rate / 0.001)`

## Use the error budget for decisions

| Budget remaining | Action |
|---|---|
| > 75% | Ship freely (but not 100% freely) |
| 50-75% | Slow down on risky changes |
| 25-50% | Freeze non-critical deploys; investigate the cause |
| < 25% | Incident mode: stop the bleeding, then post-mortem |

The "stop the bleeding" trigger: don't ship anything that could
worsen the SLO. The "post-mortem" is a blameless review of what
went wrong.

## What SLOs are NOT

- **Marketing claims:** "99.999% uptime" is a claim; "99.9%
  monthly SLO" is a target. Different.
- **Per-request guarantees:** SLOs are aggregate. Individual
  requests can fail.
- **Free license to be unreliable:** if you consistently hit
  100% of your error budget, the SLO is too loose. Tighten it.

## Verification
- **Test:** Synthetic monitoring from multiple regions every
  1 minute (probe a known endpoint, record success/latency)
- **Live:** Real-user monitoring (RUM) via a JS snippet that
  records Core Web Vitals + custom timing
- **Audit:** Quarterly SLO review (is the SLO still right?)

## Gotchas
- **SLOs are for the system, not the team.** A team can hit its
  SLO while making users unhappy. Add user-satisfaction metrics
  (NPS, CSAT) for a fuller picture.
- **Multi-region complicates SLOs.** If 1 region is down for
  10 minutes, is that 10 minutes of downtime or 1/3 of 10
  minutes (weighted by traffic)? Pick a model and document it.
- **The error budget is reset on the 30-day rolling window.**
  Old outages age out. A 24-hour outage 2 months ago doesn't
  affect today's budget.
- **Some teams use "burn rate" alerting:** if the budget is
  being consumed at >2x the expected rate, alert. More useful
  than "we're at 50% of budget."
- **For CF Pages / Workers, the platform has its own SLO
  (100% per Cloudflare's commitment).** Your app's SLO is
  what you control, not the platform's.

## Related
- `retry-with-jitter.md`
- `circuit-breaker-pattern.md`
- Google SRE: https://sre.google/sre-book/service-level-objectives/
- CF Analytics: https://developers.cloudflare.com/analytics/
