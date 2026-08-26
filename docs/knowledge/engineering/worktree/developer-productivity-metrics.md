# developer-productivity-metrics

**Issue:** Engineering productivity is measured by output (lines of code, story points) rather than outcomes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Management asks "how productive is the team?" Engineers point to story point velocity. But velocity is gameable, doesn't correlate with business outcomes, and ignores quality and sustainability.

## Pattern / Solution
Use a layered metrics approach combining delivery metrics, quality signals, and developer experience data.

**Delivery metrics (what ships):**
| Metric | Description | Target |
|--------|-------------|--------|
| Deployment frequency | How often code ships to prod | Daily |
| Lead time for change | Commit to prod time | < 1 day |
| Change failure rate | % deploys causing incidents | < 5% |
| MTTR | Time to restore after failure | < 1 hour |

**Quality metrics:**
| Metric | Description |
|--------|-------------|
| Test coverage trend | Is it going up or down? |
| Tech debt ratio | % of sprint spent on debt |
| Bug escape rate | Bugs found in prod vs. caught in dev |
| P1 incident frequency | Trending up or down? |

**Developer experience metrics (how it feels):**
- PR cycle time (open → merged): target < 24h
- Build time: target < 10 min
- On-call page volume per engineer per week
- Quarterly developer experience survey (eNPS-style)

**Anti-patterns to avoid:**
- Individual story point velocity (creates gaming and comparison anxiety)
- Lines of code (no correlation with value)
- PRs merged per engineer (biases against reviewers and architects)
- Test coverage as a target (creates useless tests)

## Gotchas
- DORA metrics are team-level, never individual-level
- Measuring everything creates survey fatigue — pick 5–7 metrics max and stick with them
- Metrics are signals for conversation, not performance management inputs

## Related
- `dora-metrics-implementation.md`
- `space-framework-developer-experience.md`
- `engineering-kpis-dashboard.md`
