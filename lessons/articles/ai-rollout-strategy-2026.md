# ai-rollout-strategy-2026

**Issue:** New agent or prompt ships to 100% traffic on day one. Day two: a 30% escalation spike, a 4x cost increase, and a customer-base-wide incident. Rollback is theoretically possible but untested.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

AI deployments behave differently from software deployments. Two production requests with the same input can produce different outputs. The blast radius of a bad prompt is a function of the entire user base, not a single user. "Deploy and watch dashboards" is not a rollout strategy.

## Root cause

Three structural differences from traditional software:

1. **Output is non-deterministic.** Same input, different answer, different cost, different latency distribution.
2. **Quality is a probability, not a boolean.** The metric you care about (resolution rate, escalation rate, hallucination rate) is a distribution; you need samples to know if the distribution shifted.
3. **Failure modes are domain-specific.** Wrong tone, missed escalation, hallucinated policy, unsafe action — none of these surface in a 5xx rate or a latency p99.

Skipping stages is the failure pattern. Teams that go canary → full in one jump ship a production incident on every other change.

## The four-stage gate

The discipline that holds: shadow → canary → percentage → full, with a numeric promotion gate at each transition.

| Stage | Traffic | User impact | Question it answers | Promotion gate |
|---|---|---|---|---|
| 1. Shadow | 100% mirrored, 0% served | Zero | Does the candidate behave wildly differently on real traffic? | Per-rubric distribution within 1 point of production over 24-72h |
| 2. Canary | 1-5% live, tier-stratified | Small live cohort | Is the candidate at least as good with users in the loop? | Containment × (1 - False Resolution) within noise floor of baseline |
| 3. Percentage | 10, 25, 50% live | Broad | Are per-rubric deltas statistically significant? | Welch's t-test p > 0.05 on each rubric vs. 7-day baseline |
| 4. Full | 100% live | All | Does it hold the line under load with auto-rollback armed? | Guardrail trip rate, rubric rolling mean, p99 latency hold for 48-72h |

Each stage has a different question. Each gate is numeric, not vibes.

## The shadow mode discipline

Shadow mode duplicates every production request to the candidate. Production answers the user; the candidate runs in parallel; candidate output is scored offline and discarded. Zero user effect at full traffic coverage.

What shadow catches:

- Cost blow-ups (token deltas, output length regressions)
- Refusal rate changes
- Hard errors (5xx, timeouts, schema violations)
- Output distribution shifts

What shadow does NOT catch:

- Quality deltas a user would perceive
- Tone, context, escalation judgment

Shadow is a smoke test, not a quality test. Five business days is the minimum; below that, distribution shift cannot be distinguished from natural variance.

## The canary gate math

At canary, the metric is Containment Rate × (1 - False Resolution Rate), where Containment is "agent handled without human escalation" and False Resolution is "agent claimed resolved but user reopened." Both are measured on the live cohort and compared to the trailing 24-hour production baseline.

If the candidate's score is within the noise floor (typically ±2 percentage points at 5% traffic after 24 hours), promote. If it breaches by more than 10% for 24 hours, roll back automatically. The "roll back if it looks bad" rule is not a rule. The number is.

The reason for tier-stratified canary: enterprise customers behave differently from free-tier users. Without stratification, you might conclude the candidate is "fine" on 5% blended traffic while it tanks on the cohort that actually pays the bills.

## The percentage ramp with Welch's t-test

Welch's t-test is the right tool because production baseline and canary cohort are independent samples (different users, different times, different distributions of inputs). The null hypothesis is "no difference in rubric score between candidate and baseline." The gate is p > 0.05 on each rubric; below that, the difference is statistically significant, and you hold at the current step.

Ramp schedule:

- 10% for 12-24 hours, depending on traffic
- 25% for 12-24 hours
- 50% for 12-24 hours
- 100% (full)

Each step holds until all rubric t-tests clear, then advances. If any step fails, hold (don't roll back yet); investigate, fix, retry. Roll back only on guardrail trip or sustained failure.

## The 30-day plan that actually works

For a team rolling out a first production agent, the 30-day schedule:

- **Week 1 — Shadow.** 500+ shadow interactions, agreement rate ≥85% with human, stable failure taxonomy, latency/cost baselined.
- **Week 2 — 10% canary.** Paired human baseline; escalation rate within ±2pp of human; complaint count flat.
- **Weeks 3-4 — 50% canary.** Welch's t-test on every rubric; guardrail metrics; cost per interaction confirmed under human equivalent.
- **Day 30+ — Full with armed rollback.** Pre-written rollback trigger; auto-rollback tested; on-call briefed.

The rule: write the rollback trigger before launch day, not after the first incident.

## Verification

Tell that the four-stage gate is working: the last 10 prompt changes went through shadow → canary → percentage → full without a customer-base-wide incident. The team can name which prompt is at which stage right now. Rollback is a routine exercise, not a war room.

Tell that it isn't: a single prompt change shipped to 100% and triggered an outage. Rollback was theoretical, never tested, and took 4 hours to complete manually.

## Gotchas

- **Don't skip shadow because the change is "small."** The smallest prompt edit can break tone. Shadow costs almost nothing; the alternative is canary on actual users.
- **5% canary is the floor, not the ceiling.** Below 5% you don't get signal fast enough. Above 20% you've skipped canary and called it one step.
- **Tier-stratification matters at canary.** Without it, you can miss a cohort-specific regression and promote a model that breaks the cohort that matters.
- **Welch's t-test, not Student's.** Different sample sizes, different variances. Student's t-test assumes equal variance and gives you the wrong answer here.
- **Auto-rollback is not optional at full.** The "roll back if it looks bad" rule fires 30 minutes after the bad thing, not 5 minutes after. Arm the trigger.

## Related

- `patterns/agent-eval-2026.md` — building the rubric set that the gates use
- `lessons/agent-failure-modes-2026.md` — what fails at each stage
- `lessons/eval-driven-development-2026.md` — the eval set the gates gate on

## Source URLs (verified 2026-08-10)

- https://futureagi.com/blog/agent-rollout-strategies-2026/
- https://www.dataknobs.com/agentic-ai/14-ai-agent-deployment.html
- https://aiadvisorypractice.com/blog/model-deployment-strategies-enterprise
- https://entropyand.co/blog/ai-agent-rollout-plan
- https://micheallanham.substack.com/p/the-10-rule-scale-ai-agents-to-production
- https://alicelabs.ai/en/insights/ai-production-deployment-checklist
- https://ai-engineering.academy/learn/17-infrastructure-and-production/20-shadow-canary-progressive/
