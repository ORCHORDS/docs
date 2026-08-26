# focus-time-over-velocity

**Issue:** Engineering velocity — what's measured
**Date:** 2026-08-09
**Status:** documented

## Symptom
Sprint after sprint, story points go up. Features
are still late. Bugs multiply. On-call is paged.
You realize velocity is a local planning input, not
a health metric.

## Root cause
**Measure outcomes, not motion.** DORA + SPACE.

**Source:** DORA + SPACE + DevEx 2026.

## The "DORA" concept

DORA:
- **Deployment Frequency:** How often
- **Lead Time:** Commit to prod
- **Change Failure Rate:** % of changes fail
- **MTTR:** Recovery time
- **Use:** Pipeline health

The DORA is the pipeline.

## The "SPACE" concept

SPACE:
- **Satisfaction:** Happiness
- **Performance:** Outcome
- **Activity:** Motion (count + value)
- **Communication:** Quality
- **Efficiency:** Flow
- **Use:** Sustainability

The SPACE is the human.

## The "DevEx" concept

DevEx:
- **Feedback loops:** Fast
- **Cognitive load:** Low
- **Flow state:** Protected
- **Use:** Developer experience
- **Why:** Layer above DORA/SPACE

The DevEx is the layer.

## The "DX Core 4" concept

DX Core 4:
- **Four pillars:** Speed, Quality, Impact, Sentiment
- **Collapses:** DORA + SPACE + DevEx
- **Use:** Standard measurement
- **2026:** Nicole Forsgren et al.

The Core 4 is the standard.

## The "focus time" pattern

For focus:
- **Goal:** 4+ hours/day
- **Result:** ~50% more features
- **Method:** Clump meetings
- **Why:** Deep work default
- **Don't:** Reward overwork

The focus is protected.

## The "WIP limit" pattern

For WIP:
- **Less:** Concurrent items
- **Faster:** Each finishes
- **Why:** Finishing, not starting
- **Anti-pattern:** 5 in flight, none shipped
- **Fix:** Cap

The WIP is capped.

## The "context switching" pattern

For context:
- **Per day:** 12-15 switches
- **Recovery:** 23 minutes each (UC research)
- **5 interrupts:** -40% productivity
- **Fix:** Batch notifications
- **Async:** Default

The switch is a cost.

## The "outcomes vs motion" pattern

For outcomes:
- **Track:** Cycle time, deployment freq
- **Not:** Story points
- **Velocity:** Local planning only
- **Cross-team:** Don't compare
- **Why:** Different units

The measure is outcome.

## The "platform engineering" pattern

For platform:
- **Maturity:** High
- **Cognitive load:** -40 to -50%
- **Invisible to:** DORA
- **Compounds:** Yes
- **Use:** Paved roads

The platform is the unlock.

## The "AI as amplifier" pattern

For AI:
- **Amplifier:** Not replacement
- **Strong DORA:** More value
- **Poor DORA:** Amplified chaos
- **Invest:** First in process
- **Then:** AI tools

The AI amplifies.

## The "meeting tax" pattern

For meetings:
- **Per week:** ~10.9 hours
- **Per sprint:** ~21.8 hours
- **% of capacity:** ~27%
- **Cut:** 30-50% no effect
- **Audit:** Quarterly

The tax is real.

## The "velocity as target" anti-pattern

For target:
- **Issue:** Inflation
- **Fix:** Don't set goals
- **Why:** Looking busy
- **Use:** Planning only

The target is not KPI.

## The "cross-team comparison" anti-pattern

For compare:
- **Issue:** Different units
- **Fix:** Don't compare
- **Why:** Estimation culture
- **Per:** Team only

The compare is local.

## The "meetings default" anti-pattern

For default:
- **Issue:** 27% capacity
- **Fix:** Audit + cut
- **Why:** Most unnecessary
- **Cadence:** Quarterly

The meeting is audited.

## The "single-metric dashboard" anti-pattern

For one:
- **Issue:** Misses dimensions
- **Fix:** Balanced panel
- **DORA:** Pipeline
- **SPACE:** Human
- **DevEx:** Experience

The panel is balanced.

## The "reward motion" anti-pattern

For motion:
- **Issue:** PRs, commits
- **Fix:** System outcomes
- **Why:** Vanities inflate
- **Per:** Team, not person

The reward is outcome.

## The "interruptions as is" anti-pattern

For interruptions:
- **Issue:** 5 = -40%
- **Fix:** Budget, batch
- **Why:** Not free
- **Method:** Async

The interrupt is budgeted.

## The "AI without process" anti-pattern

For AI-only:
- **Issue:** Short bump + rework
- **Fix:** Process first
- **Why:** Amplifier
- **Sequence:** Process → AI

The order is process.

## The "velocity checklist" pattern

For checklist:
- [ ] DORA tracked
- [ ] SPACE tracked
- [ ] DevEx considered
- [ ] Focus time protected
- [ ] WIP limited
- [ ] Outcomes measured
- [ ] Platform investment
- [ ] Meetings audited
- [ ] AI as amplifier
- [ ] Cross-team not compared
- [ ] No motion reward

The checklist is 11.

## The "focus protection" pattern

For protect:
- **Calendar:** Block 4h/day
- **Meetings:** Tue PM block
- **Slack:** Batched replies
- **PRs:** Async
- **No:** Quick syncs

The protect is structural.

## The "interruption budget" pattern

For budget:
- **Per day:** 3 max
- **Per person:** Async first
- **Slack:** Off hours
- **Why:** Recovery
- **Track:** Workplace analytics

The budget is set.

## The "WIP limit per team" pattern

For team:
- **WIP:** Per team (e.g., 3)
- **Per person:** 1-2
- **Pull:** Don't push
- **Visualize:** Kanban
- **Why:** Finishing

The WIP is visualized.

## The "outcome metrics" pattern

For metrics:
- **Cycle time:** Commit to done
- **Deployment freq:** Per day
- **Time-to-impact:** Feature to user
- **MTTR:** Recovery
- **CFR:** Quality

The metric is outcome.

## The "DORA 2026 findings" pattern

For 2026:
- **Elite:** < 1hr lead, < 5% CFR
- **AI:** Amplifier
- **Platform:** Cognitive load
- **Trust:** Per team
- **Update:** 2026 report

The 2026 is current.

## Verification
- **Test:** Focus time > 4h
- **Test:** WIP bounded
- **Test:** Outcomes measured
- **Audit:** Quarterly

## Gotchas
- **The "velocity target" anti-pattern.** Local only.
- **The "meetings default" anti-pattern.** Audit.
- **The "AI only" anti-pattern.** Process first.

## Related
- `lessons/lazy-fail-evidence-discipline.md`
- `lessons/scope-discipline.md`
- `lessons/when-to-ask-vs-push.md`
- `lessons/decision-records-lightweight.md`
- `lessons/blameless-postmortem-2026.md`
- `patterns/dora-metrics.md`
- DORA: https://dora.dev/research/
- SPACE: https://dora.dev/space/
- Stack Overflow: https://stackoverflow.blog/2023/01/26/the-developer-productivity-engineering-space-handbook/
- LeadDev: https://leaddev.com/measuring-engineering-productivity
- McKinsey: https://www.mckinsey.com/capabilities/mckinsey-digital/our-insights/yes-you-can-measure-software-developer-productivity
