# Engineering Productivity Measurement: SPACE

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Leadership asks for a productivity metric. An engineer
exports lines of code per developer per sprint. The
number goes up after a refactor that removes duplicate
logic; leadership concludes productivity has fallen.
Meanwhile the team that actually shipped the hardest
feature of the quarter scores worst because they spent
three weeks in architecture reviews and wrote fewer
lines than everyone else.

## Context

The SPACE framework (Satisfaction, Performance,
Activity, Communication/Collaboration, Efficiency) was
developed by researchers at GitHub, Microsoft Research,
and the University of Victoria as a response to the
failure of single-dimensional productivity metrics.
No single number captures engineering productivity.
SPACE gives teams a vocabulary for measuring across
dimensions without reducing everything to output.
DORA metrics are a subset of the Performance dimension.

## 1. The Five SPACE Dimensions

```
+-------------------+------------------------------------------+
| Dimension         | What it measures                         |
+-------------------+------------------------------------------+
| Satisfaction      | Developer wellbeing, engagement, and     |
|                   | sense of meaningful work.                |
+-------------------+------------------------------------------+
| Performance       | Outcome quality and speed: DORA metrics, |
|                   | defect escape rate, SLO attainment.      |
+-------------------+------------------------------------------+
| Activity          | Artifacts produced: PRs merged, deploys, |
|                   | code review turnaround.                  |
+-------------------+------------------------------------------+
| Communication /   | Onboarding speed, knowledge sharing,     |
| Collaboration     | documentation coverage.                  |
+-------------------+------------------------------------------+
| Efficiency        | Flow time, interruption rate, work       |
|                   | item age, meeting load.                  |
+-------------------+------------------------------------------+
```

Measure at least one metric per dimension. Never report
a single dimension as "productivity."

## 2. DORA as a Sub-component of Performance

DORA (DevOps Research and Assessment) defines four key
metrics. They belong in the Performance dimension of
SPACE and should be read alongside the others.

```
+-------------------------------+-------------------+----------+
| DORA Metric                   | Elite             | Low      |
+-------------------------------+-------------------+----------+
| Deployment Frequency          | On demand / daily | Monthly+ |
| Lead Time for Changes         | < 1 hour          | > 6 mo   |
| Change Failure Rate           | < 5 %             | > 15 %   |
| Time to Restore Service       | < 1 hour          | > 1 week |
+-------------------------------+-------------------+----------+
```

Collect DORA metrics from CI/CD pipeline events, not
from developer self-report. Automation removes bias
from the data.

```yaml
# Example: emit deploy event to DORA data store
# in your GitHub Actions deploy workflow
- name: Record deployment event
  run: |
    curl -X POST "$DORA_INGEST_URL/deployments" \
      -H "Authorization: Bearer $DORA_TOKEN" \
      -d '{
        "service":     "${{ github.repository }}",
        "sha":         "${{ github.sha }}",
        "deployed_at": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
      }'
```

## 3. Metric Collection Tooling per Dimension

```
+-------------------+----------------------------------------+
| Dimension         | Tooling                                |
+-------------------+----------------------------------------+
| Satisfaction      | Quarterly pulse survey (5-question     |
|                   | eNPS-style). Tools: Culture Amp,       |
|                   | Lattice, or a Google Form.             |
+-------------------+----------------------------------------+
| Performance       | DORA dashboard from CI/CD events.      |
|                   | Tools: LinearB, Sleuth, Faros, or      |
|                   | custom Grafana with pipeline webhooks. |
+-------------------+----------------------------------------+
| Activity          | PR cycle time, review turnaround.      |
|                   | Tools: GitHub Insights, LinearB,       |
|                   | Swarmia, or Jellyfish.                 |
+-------------------+----------------------------------------+
| Communication     | Onboarding checklist completion rate.  |
|                   | Docs coverage ratio (pages per         |
|                   | service). Manual audit quarterly.      |
+-------------------+----------------------------------------+
| Efficiency        | Flow time per work item (Jira/Linear   |
|                   | cycle time). Calendar meeting load     |
|                   | (Clockwise or manual audit).           |
+-------------------+----------------------------------------+
```

Do not buy a tool before you know which metrics you
need. Start with data you already have in GitHub and
your CI system.

## 4. Leading vs Lagging Indicator Table

```
+--------------------------------+----------+---------------+
| Metric                         | Type     | Dimension     |
+--------------------------------+----------+---------------+
| PR cycle time                  | leading  | Efficiency    |
| Deployment frequency           | leading  | Performance   |
| Meeting hours / engineer / wk  | leading  | Efficiency    |
| Developer satisfaction score   | leading  | Satisfaction  |
| Onboarding time to first PR    | leading  | Communication |
+--------------------------------+----------+---------------+
| Change failure rate            | lagging  | Performance   |
| Defect escape rate to prod     | lagging  | Performance   |
| Customer-reported incidents    | lagging  | Performance   |
| Engineer attrition rate        | lagging  | Satisfaction  |
| P1 incident count / quarter    | lagging  | Performance   |
+--------------------------------+----------+---------------+
```

Leading indicators let you intervene early. Lagging
indicators confirm whether interventions worked.
Report both; act primarily on leading indicators.

## 5. Quarterly Review Cycle

Run a SPACE review at the end of each quarter. Keep
the format consistent so trends are visible.

```
Q3 2026 SPACE Review — [Team Name]

Satisfaction
  Pulse score:          7.4 / 10  (up from 6.9 in Q2)
  Theme from comments:  "Too many interruptions"

Performance
  Deploy frequency:     4.2 / day
  Lead time:            22 hours
  CFR:                  3.1 %
  MTTR:                 47 minutes

Activity
  Avg PR cycle time:    18 hours
  PRs merged / eng / wk: 3.2

Communication
  New-hire time to
  first PR:             6 days
  Docs coverage:        71 %

Efficiency
  Avg meeting load:     9.4 h / eng / week
  Flow efficiency:      41 %

Top actions for Q4:
  1. Reduce meeting load; block 2-hour focus blocks.
  2. Improve docs coverage to 80 %.
  3. Investigate interrupt sources from Slack audit.
```

Share the review with leadership as a dashboard link,
not a raw spreadsheet. Hide individual-level data.

## Anti-patterns

- Tracking lines of code as a proxy for productivity;
  this rewards verbose code and punishes refactors.
- Measuring heroism: celebrating engineers who resolve
  incidents fastest incentivises not fixing root causes.
- Comparing SPACE scores between teams with different
  domains; a platform team and a product team will
  always have different profiles.
- Sharing individual-level Activity metrics with
  managers for performance review purposes; this
  creates gaming and fear.
- Running the measurement programme without a feedback
  loop; if metrics do not change decisions, stop
  collecting them.

## Gotchas

- PR cycle time includes review wait time, which is
  partly a function of team size, not individual speed.
  Normalise for team size before comparing.
- Satisfaction surveys must be anonymous or responses
  will be inflated. Guarantee anonymity in writing.
- DORA metrics from self-hosted runners may miss
  deployments that bypass CI; audit pipeline coverage
  before trusting the numbers.
- Flow efficiency (value-add time / elapsed time)
  typically runs 15–40 % in healthy teams; do not
  target 80 %+ without removing necessary activities.

## Verification

1. Confirm the quarterly pulse survey has been sent
   and has at least 70 % response rate before
   reporting results.
2. Validate DORA deployment frequency by spot-checking
   three recent deploys against the ingest log.
3. Review the metrics dashboard with one engineer who
   was not involved in building it; confirm they can
   interpret every number without explanation.
4. Verify that no individual-level metric appears in
   the leadership report.

## Related

- `documentation/docs/policies/lessons/dora-metrics-engineering-measurement.md`
- `documentation/docs/policies/lessons/focus-time-over-velocity.md`
- `documentation/docs/policies/lessons/tech-debt-management-2026.md`
- `documentation/docs/policies/lessons/blameless-culture-produces-better-postmortems.md`

## Source URLs (verified 2026-08-17)

- https://queue.acm.org/detail.cfm?id=3454124
- https://dora.dev/research/
- https://linearb.io/blog/space-framework
- https://www.microsoft.com/en-us/research/publication/the-space-of-developer-productivity/
