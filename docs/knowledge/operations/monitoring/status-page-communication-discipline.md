# status-page-communication-discipline

**Issue:** When production is down, the status page is often the worst-monitored system in the company: updates arrive late or never, they describe internal causes instead of user impact, and the page still says "all systems operational" while social media fills with screenshots proving otherwise. Poor incident communication doubles the perceived length of an outage, destroys trust built by good engineering, and generates support load that the incident team cannot absorb. This article covers the operating discipline for status pages: fast first posts, honest cadence, user-impact framing, severity routing, automation guardrails, and post-incident follow-through.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The first update

1. **Post within five minutes of a confirmed-impact detection, even with no diagnosis.** "We are investigating reports of elevated login failures" beats a silent page; the goal is to prove the team knows before users conclude the company does not.
2. **Separate detection from declaration.** Trigger the status page on impact signals (error-rate SLO burn, failed synthetic checks, support volume spike), not on root-cause certainty — waiting for understanding before acknowledging is the single most common communication failure.
3. **Write the first post for someone with 10 seconds.** State what is affected, who is affected, whether there is a workaround, and when the next update comes; internal architecture has no place in it.
4. **Do not downgrade to save face.** If impact is uncertain, open at the higher severity; shrinking an incident later is cheap and expanding it after users were told "minor" is not.

## Cadence discipline

1. **Commit to a next-update time in every post.** "Next update by 14:30" converts silence from a trust failure into a schedule; a 2025-2026 consensus across Atlassian Statuspage, PagerDuty, and incident.io guidance is 15-30 minute intervals for major incidents.
2. **Post even when there is no news.** "We are continuing to work on mitigation; no change since the last update" resets the clock and stops customers from assuming the worst; only-posting-on-progress pages read as abandoned during long waits.
3. **Scale cadence to severity.** Major outages get 15-30 minute updates; degraded-performance incidents can run 60-120 minutes; a published severity table makes the cadence a policy rather than each commander's judgment call.
4. **Post resolution within an hour of the fix.** Delayed "resolved" posts strand users who already worked around the problem, and they make the incident look longer in every retrospective timeline.

## What to write

1. **Lead with impact, not cause.** "Checkouts are failing for approximately 30% of EU customers" is actionable; "a connection pool exhausted in the payments service" is a postmortem draft.
2. **Name the user-visible symptom precisely.** Partial impact statements ("search autocomplete is delayed, search itself works") prevent all-or-nothing readings and reduce duplicate support tickets.
3. **Include workarounds when they exist.** A working workaround converts a sev1 perception into an inconvenience and measurably reduces ticket volume during the incident.
4. **Never speculate publicly on cause or ETA you cannot support.** Wrong early root-cause claims live forever in customer memories and regulator screenshots; "we do not yet know" is a legitimate, professional sentence.
5. **Keep components truthful.** Mark only impacted components as degraded; a page that flips everything red teaches customers to ignore the page.

## Severity routing and audience

1. **Map severity to channels mechanically.** SEV1 pages notify all subscribers and update social; SEV3 updates the page only; making this a table removes per-incident decisions and inconsistencies.
2. **Separate internal and external narratives.** The status page is for users; the internal incident channel carries cause hypotheses and forensic detail — leaking the wrong register into the other audience causes confusion both directions.
3. **Assign communication as a role, not a side task.** The incident commander who is debugging cannot also write updates on cadence; a communications deputy owns the page for SEV1 and SEV2.

## Automation and guardrails

1. **Wire monitoring to the page for the acknowledge-and-resume path.** Auto-open an "investigating" incident when burn-rate or synthetic alerts fire so the first post happens in seconds, then require a human to confirm or close; auto-resolve without human confirmation has publicly embarrassed many companies and should be banned.
2. **Alert on status-page staleness itself.** A timer that pages the comms deputy when an active incident passes its promised next-update time treats missed updates as an operational error, not a social one.
3. **Rehearse in game days.** Practice the first-5-minute post template during incident drills; templates for acknowledge, update, and resolution remove blank-page delay under stress.
4. **Track communication metrics.** Time-to-first-update, percentage of updates posted by their promised time, and incident-to-first-post delta belong in the retro alongside MTTR.

## After resolution

1. **Publish the postmortem link within the promised window.** Stating "RCA within 5 business days" and meeting it is a trust-building move; missing a self-imposed deadline reads worse than never promising.
2. **Keep the incident history honest.** Never delete or rewrite past incidents; the history page is evidence of operational maturity and the first thing serious customers audit.
3. **Feed communication failures into the retro separately from technical ones.** A flawless technical response with a silent status page is a failed incident by user perception, and the retro should treat it that way.
