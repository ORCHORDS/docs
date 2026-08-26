# sre-error-budget-policy

**Issue:** Defining and enforcing an error budget policy to govern feature velocity vs reliability
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Reliability and product teams in constant tension. Features ship too fast causing reliability regressions. No shared language for "we are moving too fast" or "we have reliability headroom".

## Pattern / Solution
Error budget policy document template:
```markdown
# Error Budget Policy — [Service Name]

## SLO
Availability: 99.9% measured over rolling 30 days
Error budget: 43.8 minutes/month of allowed downtime

## Budget Consumption Thresholds

### Budget > 50% remaining (green)
- Normal feature development velocity
- Deploy anytime during business hours
- Automated releases proceed without human approval

### Budget 25–50% remaining (yellow)
- Slow release cadence — maximum 1 deploy per day
- All deploys require IC on standby
- New features require SRE review before ship

### Budget < 25% remaining (red)
- Feature freeze — only reliability and bug fixes ship
- All deploys require SRE approval
- Weekly review with VP Engineering and CTO

### Budget exhausted (incident mode)
- All non-emergency deploys halted
- SRE team prioritizes reliability project for next sprint
- Joint postmortem required before returning to green

## Budget Reset
Error budget resets at the start of each calendar month.
```

Budget tracking in Grafana:
```promql
# Remaining error budget as % of monthly budget
(
  sum_over_time(
    (rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]))[30d:]
  ) * 5 / 60 / 24 / 30
) / 0.001   # 0.001 = 1 - 0.999 SLO
```

## Gotchas
- Error budget policy is only effective if product leadership co-owns and enforces it
- Budget consumption from infrastructure failures (cloud outages) should not block feature deploys — differentiate cause
- Retroactive budget adjustments (excusing incidents) undermine the policy — resist pressure to exclude incidents post-hoc
- Review SLO targets annually — an SLO that's never breached may be too lenient

## Related
- `monitoring-sla-slo-sli.md`
- `toil-reduction-sre.md`
- `chaos-engineering-gameday.md`
