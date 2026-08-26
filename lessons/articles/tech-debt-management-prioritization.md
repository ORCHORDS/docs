# Tech Debt Management and Prioritization

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Feature delivery is slowing down, but the backlog keeps growing. Engineers
complain about "legacy code" but cannot articulate which parts hurt the
most. Tech debt remediation is either ignored entirely or attempted as a
"big rewrite" that stalls product delivery. Leadership sees debt work as
a cost center with no measurable return.

## Context

Technical debt is the gap between the current state of the codebase and
the state it needs to be in to deliver features safely and efficiently.
In 2026, technical debt costs US companies over $2.4 trillion annually.
High-debt organizations spend 40% more on maintenance and deliver features
25-50% slower than peers. Effective management requires measurement,
prioritization by business impact, and continuous allocation — not one-time
cleanup sprints.

## Measurement

### Quantitative signals

| Metric | What it measures | Source |
|---|---|---|
| **Change failure rate** | % of deployments causing incidents | DORA metrics |
| **Lead time for changes** | Time from commit to production | DORA metrics |
| **Hotspot analysis** | Files with high churn + high complexity | CodeScene, CodeClimate |
| **Dependency age** | Outdated dependencies with known vulnerabilities | Dependabot, Renovate |
| **Test coverage gaps** | Critical paths with zero test coverage | Coverage reports |
| **Build time** | CI pipeline duration trend | CI metrics |

### Qualitative signals

- Developer surveys: "How confident are you deploying on Friday?"
- Onboarding time: how long until a new engineer can ship independently.
- Incident post-mortems: how often does debt appear as a contributing
  factor.

## Prioritization framework

### 1. Impact-effort matrix

Categorize debt items by **business impact** (how much it affects
revenue, reliability, security, or developer velocity) and **effort**
(how long remediation takes):

| | Low effort | High effort |
|---|---|---|
| **High impact** | Do first (quick wins) | Plan and schedule |
| **Low impact** | Do opportunistically | Deprioritize or accept |

### 2. Hotspot-driven prioritization

Use tools like CodeScene to identify files with the highest combination of:

- **Change frequency** (churn) — files changed most often.
- **Complexity** — cyclomatic complexity, nesting depth.
- **Developer count** — files touched by many developers (coordination
  cost).

High-churn, high-complexity files are where debt remediation has the
highest ROI — these are the files engineers modify most and where bugs
are most likely to occur.

### 3. Risk-based prioritization

Prioritize debt that creates security, reliability, or compliance risk:

- Outdated dependencies with known CVEs (CRITICAL/HIGH).
- Authentication/authorization code with no tests.
- Infrastructure components past end-of-life.

## Allocation strategies

### Continuous allocation (recommended)

Reserve **10-30% of sprint capacity** for tech debt reduction. This
prevents accumulation without stalling product delivery.

```
Sprint capacity: 100 story points
Feature work: 70-80 points
Tech debt: 10-20 points
Bugs: 5-10 points
```

### Tech debt sprints (quarterly)

Dedicate one sprint per quarter entirely to debt reduction. Works for
larger refactoring that cannot be broken into small increments.

### Boy Scout Rule

"Leave the code better than you found it." Every PR that touches a file
may include small improvements: rename a confusing variable, extract a
function, add a missing test. No separate ticket needed.

### Debt budget

Set a maximum acceptable debt level (e.g., "no dependencies more than 2
major versions behind," "no files with cyclomatic complexity > 30"). When
the budget is exceeded, debt work takes priority over features.

## Making debt visible to leadership

- **Dashboard** — track DORA metrics, dependency health, and hotspot
  trends on a visible dashboard. Show the trend, not just the snapshot.
- **Business impact framing** — "this refactoring will reduce deployment
  failures by 30%" is more compelling than "we need to clean up the
  legacy code."
- **Quarterly review** — include tech debt status in quarterly planning.
  Show remediation completed, debt introduced, and net position.
- **Incident attribution** — tag post-mortem action items as "debt-
  related" when applicable. This creates a direct line from debt to
  incidents to business impact.

## Anti-patterns

- **Big rewrite** — rewriting a system from scratch while maintaining the
  old one doubles the maintenance burden and usually fails. Prefer
  incremental strangler fig migration.
- **Zero allocation** — never scheduling debt work guarantees
  accumulation. The codebase degrades until feature delivery becomes
  impossible.
- **Debt-only sprints without measurement** — "we spent a sprint on tech
  debt" without measuring before/after impact is unaccountable. Define
  success metrics before starting.
- **Treating all debt equally** — a confusing variable name and a
  security-critical dependency vulnerability are not the same priority.
  Prioritize by business impact.
- **Gold plating as debt reduction** — rewriting working code to use a
  newer pattern without measurable benefit is not debt reduction. Debt
  work must address a real problem.

## Gotchas

- **Debt is not always bad** — intentional, documented debt (shipping a
  simpler solution now with a plan to iterate) is a valid business
  decision. The problem is unintentional, invisible debt.
- **Metrics can be gamed** — coverage percentage, complexity scores, and
  dependency counts can all be gamed. Use metrics as signals, not targets.
- **Organizational resistance** — teams may resist debt allocation if
  leadership rewards only feature delivery. Recognize debt remediation as
  a first-class contribution.
- **Debt creates more debt** — working around existing debt creates
  additional workarounds. The cost of debt is not linear — it compounds.

## Verification

- Tech debt allocation is visible in sprint planning (10-30% of capacity).
- DORA metrics (change failure rate, lead time) are tracked monthly.
- Hotspot analysis runs quarterly with action items for the top 5 files.
- Critical dependencies are no more than 1 major version behind.
- Debt remediation impact is measured before/after (cycle time, incident
  rate).
- Post-mortem action items tagged as debt-related are tracked to
  completion.

## Related

- `documentation/categories/lessons/code-review-practices.md`
- `documentation/categories/lessons/change-management-engineering.md`
- `documentation/categories/monitoring/dora-metrics-tracking.md`

## Source URLs (verified 2026-08-16)

- Sourcegraph tech debt management — https://sourcegraph.com/blog/technical-debt-management
- Zylos tech debt research — https://zylos.ai/research/2026-02-07-technical-debt/
- ClickIT CTO guide — https://www.clickittech.com/ai/how-to-reduce-technical-debt/
- Coderio business risk framework — https://www.coderio.com/blog/software-development/technical-debt-strategies-business/
