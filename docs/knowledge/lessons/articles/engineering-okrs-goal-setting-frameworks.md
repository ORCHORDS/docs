# Engineering OKRs and Goal-Setting Frameworks

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Engineering leadership sets ambitious OKRs each quarter. By week six, most
key results are red because they were outputs disguised as outcomes, the team
is shipping features unrelated to the OKRs, and nobody knows whether the
reliability goal ("reduce incidents") is better measured by count, MTTR, or
error budget consumption. At year-end the team retrospective produces: "we
delivered a lot but didn't hit our goals." The goals were the wrong shape.

Good engineering OKRs connect daily technical decisions to business outcomes,
create meaningful signals about whether the team is moving in the right
direction, and survive contact with reality without collapsing into vanity
metrics.

## Context

OKRs (Objectives and Key Results) were formalized at Intel by Andy Grove in
the 1970s and popularized at Google. The method is simple in theory: an
Objective states a qualitative direction ("be the most reliable payments
processor in our category"), Key Results are 3–5 measurable outcomes that
define success ("reduce P1 incident count by 40%", "achieve 99.95% uptime").

For engineering teams, three failure modes dominate:

1. **Output OKRs** — measuring deliverables, not impact. "Ship the v2 API"
   is an output. "Reduce integration latency by 50% for external partners"
   is an outcome.

2. **Unmeasurable KRs** — "improve developer experience" without a metric
   attached. What improves? By how much? How do you know when you're done?

3. **Misaligned OKRs** — engineering OKRs that have no connection to product
   or business OKRs. Teams optimize locally and miss the point.

This article gives structural templates, measurement strategies for common
engineering outcomes, and a quarterly cadence that keeps OKRs alive.

---

## The Objective: Direction Without Dictation

A good engineering Objective:
- States a direction, not a deliverable
- Is achievable in one quarter (ambition is fine; fantasy is not)
- Connects to something a non-engineer would care about
- Is uninspiring if fully achieved — the "score 0.7 not 1.0" rule applies

```
BAD: "Complete the infrastructure migration to Cloudflare Workers"
  → Output. Pass/fail. No signal about customer value.

GOOD: "Make our edge infrastructure so reliable and fast that customers
       stop mentioning performance as a concern in NPS surveys"
  → Direction. Connects to customer perception. KRs will define the metrics.

BAD: "Improve platform engineering"
  → Meaningless without definition. Any activity qualifies.

GOOD: "Eliminate the infrastructure bottlenecks that slow down every team's
       ability to ship"
  → A problem statement. KRs will quantify "eliminate" and "slow down."
```

Each team should have 1–3 Objectives per quarter. More than 3 means the team
has no actual priorities.

---

## Key Results: Measurement Templates for Engineering

### Reliability Key Results

```yaml
# Reliability KR templates

# Error budget-based (recommended for SRE/platform teams)
kr_reliability_1:
  statement: "Maintain 99.9% uptime for the Orders API (error budget: 43.8 min/month consumed)"
  baseline: "Current: 99.7% (consumed 2.2h error budget in Q2)"
  measurement: "CF Analytics / Datadog SLO dashboard"
  cadence: weekly

# MTTR-based (good for on-call-heavy teams)
kr_reliability_2:
  statement: "Reduce mean time to resolution for P1 incidents from 47 min to < 20 min"
  baseline: "Last 6 months median MTTR: 47 minutes"
  measurement: "PagerDuty incident reports, exported weekly"
  cadence: monthly

# Customer-impact-based
kr_reliability_3:
  statement: "Zero customer-impacting incidents caused by deploy errors (vs. 3 in Q2)"
  baseline: "Q2: 3 deploy-induced incidents"
  measurement: "Incident post-mortem root cause tagging"
  cadence: per-incident
```

### Performance Key Results

```yaml
# Performance KR templates

kr_performance_1:
  statement: "Reduce API p99 latency from 820ms to < 300ms for the /checkout endpoint"
  baseline: "Current p99: 820ms (30-day average)"
  measurement: "Cloudflare Analytics Engine / Grafana dashboard"
  cadence: weekly
  note: "p99 over p50 because the tail is what users notice"

kr_performance_2:
  statement: "Core Web Vitals: LCP < 2.5s for 90% of page loads on mobile (up from 67%)"
  baseline: "CrUX data: LCP < 2.5s for 67% of mobile loads"
  measurement: "Google Search Console + synthetic Lighthouse CI"
  cadence: weekly
```

### Developer Productivity Key Results

```yaml
# Developer productivity KR templates (DORA-aligned)

kr_devprod_1:
  statement: "Reduce CI pipeline duration from 14 min to < 6 min (deployment frequency unblocked)"
  baseline: "Current median CI duration: 14 minutes"
  measurement: "GitHub Actions timing, exported from Actions API"
  cadence: weekly

kr_devprod_2:
  statement: "Achieve deployment frequency of >= 5 deploys/day to production (up from 1.2)"
  baseline: "Current: 1.2 deploys/day average over 60 days"
  measurement: "wrangler deploy logs, counted by CI pipeline"
  cadence: weekly
  note: "DORA elite: > 1 deploy/day. We want elite tier by EOQ."

kr_devprod_3:
  statement: "Reduce change failure rate from 8% to < 2%"
  baseline: "Last 90 days: 8% of deploys required a hotfix or rollback"
  measurement: "Deploy + rollback event log, tagged in incident system"
  cadence: monthly
```

### Security and Compliance Key Results

```yaml
kr_security_1:
  statement: "Zero critical or high CVEs outstanding > 14 days in production dependencies"
  baseline: "Current: average 23 days to remediate high CVEs"
  measurement: "Dependabot / Snyk dashboard, SLA tracking"
  cadence: weekly

kr_security_2:
  statement: "100% of new production secrets rotated to Cloudflare Secrets Manager (from 60%)"
  baseline: "Current: 60% of secrets in managed store, 40% still in env vars"
  measurement: "Secrets inventory audit, maintained in Notion"
  cadence: monthly
```

---

## The Quarterly Cadence

OKRs fail when they are set and then reviewed only at the end of the quarter.
The cadence is the accountability mechanism.

```
Engineering OKR Calendar — 12-Week Quarter
--------------------------------------------

Week 1:
  - Draft Objectives (bottom-up from team leads, top-down from leadership)
  - Identify measurement sources for each proposed KR
  - Baseline collection: run the measurement NOW before the quarter starts

Week 2:
  - OKR review with cross-functional partners (PM, Design, Data)
  - Confirm alignment to business OKRs
  - Lock and publish to the team

Weeks 3–4:
  - First KR health check — are metrics moving at all?
  - If zero movement: either the KR is not measured correctly or
    the work isn't happening yet. Distinguish these.

Weeks 5–6:
  - Mid-quarter review (30 min team meeting)
  - Traffic light each KR: green (on track), yellow (at risk), red (off track)
  - For red KRs: is this a strategy failure or a measurement failure?
    Amend the KR metric if the measure was wrong; escalate if it's strategy.

Week 8:
  - Trajectory review: project final score based on current velocity.
  - Begin any wind-down or pivot conversations now, not week 12.

Week 11:
  - Final measurement collection
  - Write Q+1 draft OKRs informed by Q results

Week 12:
  - OKR retrospective: what did we learn about what moves the needle?
  - Publish final scores (not for performance review — for learning)
```

---

## Scoring and Calibration

Google's original OKR guidance suggests a 0.6–0.7 score is ideal — ambitious
enough to require real effort, achievable enough to be credible. Engineering
teams often miscalibrate in one of two directions:

```
Score Interpretation Guide
--------------------------

0.0 – 0.3  MISS
  Causes: KR was the wrong metric, goal was unrealistic given dependencies,
  major unplanned work absorbed the team (incidents, tech debt fires).
  Action: post-mortem the miss, not the team.

0.4 – 0.6  PARTIAL PROGRESS
  For stretch goals this is acceptable and expected.
  For baseline hygiene goals (e.g., "zero P0 security findings"), this
  is not acceptable — review why the floor was not reached.

0.6 – 0.7  TARGET ZONE
  The goal was ambitious. The team stretched. Celebrate this.

0.8 – 1.0  ACHIEVED (or sandbagged)
  Consistently hitting 1.0 means goals were not ambitious enough.
  Review whether goals are being set to be comfortable, not challenging.
  Exception: reliability and security targets (these should be 1.0).

> 1.0  EXCEEDED
  Either the baseline was too conservative or there was a measurement error.
  In either case, recalibrate the next quarter's baseline.
```

Separate hygiene KRs (security, compliance, data protection) from stretch KRs.
Hygiene KRs should score 1.0. A 0.7 on "zero critical CVEs > 14 days" is not
a success — it means something slipped through.

---

## Connecting Engineering OKRs to Business OKRs

The most common alignment failure: engineering OKRs are technically correct
but disconnected from what the business is trying to achieve this quarter.

Use this mapping exercise at the start of each quarter:

```
Business OKR Alignment Map
----------------------------

Business Objective (from CEO/CPO):
  "Expand into European markets and achieve first 1,000 EU customers"

↓ What does this require from Engineering?

Engineering Objective:
  "Make our platform fully EU-compliant and performant for European users"

↓ KRs that directly support this:

KR 1: Complete GDPR data residency implementation (EU data stays in EU)
  Measure: 100% of EU user data stored in Cloudflare R2 EU-West region
  Baseline: Currently 0% — all data in US-East

KR 2: EU user API latency p95 < 200ms
  Measure: Cloudflare Analytics Engine, filtered by CF-IPCountry: EU
  Baseline: Current EU p95: 890ms (routed via US origin)

KR 3: Zero GDPR compliance findings in external audit scheduled for Q3
  Measure: Audit report findings count (pass/fail)
  Baseline: Not yet audited — self-assessed compliant

↓ Engineering OKRs that do NOT support this and should be deferred:

  "Migrate from PostgreSQL to D1" → not EU-critical, defer to Q4
  "Add new analytics dashboard" → not EU-critical, defer
```

---

## Anti-patterns

- **Activity OKRs** — "Write 10 runbooks", "conduct 4 architecture reviews."
  Activities are trackable but do not measure outcomes. Replace with the
  outcome the activity produces.

- **100% target on stretch goals** — Setting a 100% target on an ambitious
  KR demoralizes teams when they hit 0.7. Reserve 100% targets for hygiene.

- **OKRs as performance reviews** — If KR scores feed directly into
  compensation review, teams sand-bag. OKRs must be psychologically safe to
  fail (and to report accurately).

- **Too many OKRs** — Five objectives with 4 KRs each = 20 KRs. The team
  cannot hold these in mind. Maximum: 2–3 objectives, 2–4 KRs each.

- **Set-and-forget** — OKRs without a weekly or bi-weekly health check
  become irrelevant noise. The check-in is the mechanism that makes them work.

- **Vanity metric KRs** — "Increase GitHub stars from 2k to 10k." Stars
  measure neither reliability, developer productivity, nor customer value.
  Vanity metrics feel like progress without being progress.

---

## Gotchas

- **Baseline collection is week 1, not week 12** — You cannot score an OKR
  without a starting measurement. If week 1 passes without baselining, the KR
  loses credibility by quarter end.

- **"Improve" is not measurable** — Every KR must have a number: "improve
  from X to Y." Even binary KRs should state both states.

- **Dependencies belong in the OKR doc** — If KR 2 requires a data pipeline
  from the Data team, that dependency should be explicit and the Data team's
  OKR should include delivering it. Unwritten dependencies become excuses.

- **Platform team OKRs are upstream OKRs** — Platform teams often feel they
  cannot own outcomes because they depend on product teams adopting their
  tooling. The correct measure is adoption rate, not the tool itself.

---

## Verification

At the end of each quarter, run this audit before finalizing scores:

```
OKR Quality Audit (run end of quarter)
---------------------------------------
[ ] Every KR has a numeric baseline collected in week 1
[ ] Every KR has an identified measurement source (dashboard, report, log)
[ ] Every KR is an outcome, not an output (test: does it describe impact?)
[ ] The team's OKRs map to at least one business OKR
[ ] At least one KR scored below 0.7 (if all green, goals were too easy)
[ ] At least one KR scored above 0.5 (if all red, goals were unrealistic)
[ ] Hygiene KRs (security, compliance) scored 1.0
[ ] OKR retrospective is scheduled and attendees confirmed
```

---

## Related

- `dora-metrics-engineering-measurement.md`
- `engineering-productivity-measurement-space.md`
- `sre-error-budget-policy-enforcement.md`
- `error-budget-policy-as-a-reliability-learning-loop.md`
- `technical-roadmap-communication-stakeholders.md`
- `team-topologies-organizational-design.md`
- `blameless-postmortem-incident-review.md`

## Sources

- Grove, A. *High Output Management* (1983) — original MBO/OKR framework
- Doerr, J. *Measure What Matters* (2018) — OKR at Google and beyond
- Forsgren, N. et al. *Accelerate* (2018) — DORA metrics as engineering KRs
- Google re:Work OKR Guide — rework.withgoogle.com/guides/set-goals-with-okrs/
- Marquet, D. *Turn the Ship Around* (2013) — intent-based leadership and goal alignment
- Wodtke, C. *Radical Focus* (2nd ed., 2021) — OKRs for teams in practice
