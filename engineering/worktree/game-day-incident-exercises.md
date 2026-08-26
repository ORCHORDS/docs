# game-day-incident-exercises

**Issue:** An incident response process that has never been rehearsed is a hypothesis, not a capability. Game days — structured exercises ranging from discussion-based tabletop scenarios to live fault injection in production-like environments — are how teams convert runbooks and role definitions into practiced muscle memory before a real 3 a.m. page does it for them. The 2025-2026 practice converge on clear guidance: set objectives and hypotheses up front, establish ground rules and blast-radius limits before injecting anything, let participants drive detection and response rather than following a script, introduce realistic complications mid-exercise, and close every game day with a blameless debrief that feeds runbook and tooling improvements. Tooling has matured alongside (AWS Fault Injection Service, Harness GameDays, incident simulators), but the engineering problem remains organizational: cadence, safety, scenario design, and turning exercise findings into tracked work.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Formats and when to use them

1. **Tabletop first.** A facilitated, discussion-based walkthrough of a scenario ("the primary database fails over during peak traffic — what do you do in the first five minutes?") as described in Uptime Labs' tabletop guides. It is cheap, safe, and exposes missing runbooks and unclear ownership faster than any technical drill.
2. **Live-fire drills in a staging or production-like environment.** Actually break something (kill a pod, drain a region, throttle a dependency) and watch the real dashboards. This is where silent assumptions — alerts that never fire, dashboards that assume an operator who left — surface.
3. **Fault-injection game days with managed tooling.** Platforms such as AWS FIS and Harness's GameDay orchestration let you run defined experiments with automatic halt conditions, giving live-fire realism with safety rails. Use them once your team has graduated from tabletops.
4. **Simulator-based practice for individuals.** Incident simulators (mykeels' game-day engineering writeup surveys the space) let a single engineer rehearse incident command and triage decisions daily, and double as onboarding material for new responders.
5. **Degraded-mode walkthroughs for product and support.** Not every game day needs engineers breaking things; walking support and product peers through what customers see during each failure mode is its own exercise class and often the one with the biggest payoff.

## Running the exercise

1. **Define objectives and a falsifiable hypothesis.** "If the primary region is drained, the on-call will detect and route around it within ten minutes using existing runbooks" is an objective; "test our resilience" is not. Upstat's incident-simulation guidance and the chaos engineering canon agree on this as step one.
2. **Publish ground rules and blast radius before starting.** Who can call an abort (everyone), what the manual and automatic halt conditions are, which environments and customer segments are in scope, and how real customer-impact risk is excluded. Nobody thinks clearly in an exercise they fear.
3. **Start the clock at detection.** The scenario should begin with only the signals a responder would really get — an alert, a customer ticket, a graph anomaly — not with the answer. The most practiced skill in incident response is recognizing that something is wrong at all.
4. **Let the team drive; the facilitator complicates.** Resist scripting the response. The exercise controllers inject realistic complications mid-drill (the incident channel is degraded, a second alert fires, the deploy pipeline is frozen) and observe whether roles and escalation paths hold.
5. **Rehearse the roles, not just the tech.** Rotate the incident commander, comms lead, and scribe in every game day so the role is not owned by whichever senior engineer happens to be present. Manager and onboarding variants of game days are increasingly used exactly for this.

## Closing the loop

1. **Blameless debrief immediately.** Run the same blameless postmortem format used for real incidents, while the exercise is fresh: what was expected, what happened, what the exercise revealed about tooling, runbooks, and roles.
2. **Convert findings into tracked issues.** Every game day produces a handful of action items — a missing alert, a stale runbook, an undocumented dependency. They enter the normal backlog with owners and dates, and the next game day's scenario selection checks whether they closed.
3. **Fix the runbook before the tool.** Most game-day findings are documentation-shaped: the alert exists but the runbook for it does not. Cheap, high-leverage fixes first.
4. **Keep a regular cadence tied to risk.** A quarterly game day per service area is a common baseline, plus one exercise after any significant architecture change and one after every real incident that revealed a gap. Annual-only exercises are theater.
5. **Track readiness trends, not pass/fail.** Measure time-to-detect and time-to-mitigate across successive exercises on the same failure class and watch the trend. The goal is a shrinking gap between how the team performs in a drill and how it must perform in a real page.
