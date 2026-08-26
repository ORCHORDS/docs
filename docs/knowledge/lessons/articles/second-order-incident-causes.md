# second-order-incident-causes

**Issue:** Postmortems routinely stop at the trigger — the deploy, the config change, the traffic spike — because the trigger is the most visible event and the easiest to name. But the trigger is almost never the cause. Safety science (James Reason's active failures vs latent conditions, Richard Cook's "How Complex Systems Fail") and a decade of SRE postmortem practice show that outages happen when a trigger lands on latent weaknesses that were baked into the system long before: drifted configs, accumulated toil, undocumented dependencies, or knowledge that lives in exactly one head. Fixing only the trigger means the next trigger reactivates the same latent condition and the incident "repeats" — not from bad luck, but because the second-order cause was never touched.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Telling the trigger from the latent condition

1. **The trigger is the match; the latent condition is the dry forest.** Ask of every contributing factor: "did this exist before the incident, silently?" If yes, it is a latent condition — the trigger merely found it. A restart that exposed a config drift is a trigger; the drift itself sat there for months.
2. **Apply the substitution test.** Swap the trigger for a plausible alternative (a different deploy, a failover, a traffic spike). If the incident still would have happened, the thing you're looking at is a trigger, not the cause — and the real cause is the latent condition underneath.
3. **"Human error" is a trigger, never a root cause.** The correct question is what latent condition made the error possible and gave it impact: missing validation in the pipeline, no staged rollout, an alert that fires too late, an on-call with no runbook. People do not err into a resilient system and cause an outage.
4. **The Swiss Cheese framing for engineering defenses.** Code review, CI gates, canary deploys, monitoring, and rollback plans are defense layers with holes. An incident means the holes aligned. The postmortem's job is to find which holes were chronic (latent) versus which one opened on the day (the trigger).

## Common latent conditions in software systems

1. **Configuration drift.** Environments that were identical at launch diverge silently over years. The drift causes nothing until a failover or restart makes the drifted node take live traffic — then it causes everything. GitLab's 2017 database loss is the canonical example of long-dormant process/config weaknesses activated by a bad day.
2. **Single-person knowledge.** When exactly one engineer understands a subsystem, that concentration is a latent failure in your org chart. It activates the day that person is on vacation, asleep, or has left — and the incident drags for hours that a documented system would have resolved in minutes.
3. **Toil accumulation.** Every manual workaround that "only takes ten minutes" is a latent condition: it survives until the person doing the toil is busy, the script rots, or the workaround masks a degrading dependency. Toil is unexploded ordnance with a timer you can't see.
4. **Alert and dashboard debt.** Alerts that were muted "temporarily," dashboards nobody trusts, and SLOs that no longer match the product all count as latent. They activate when they fail to warn — turning a slow degradation into a surprise outage discovered by customers instead of monitors.
5. **Implicit dependency knowledge.** Service X calls service Y only during failover, or only on the last day of the month. Nobody currently on-call knows this. The dependency is real, undocumented, and waiting for its trigger.

## Surfacing latent conditions in the postmortem

1. **Require a "latent conditions found" section distinct from the timeline.** The timeline records events; this section records pre-existing weaknesses with the date each one entered the system ("drift introduced ~2024-11 during the migration"). Naming when the hole opened redirects analysis away from the last actor.
2. **Ask "how long has this been true?" for every factor.** Anything true for weeks before the incident is latent by definition. The answer also estimates your detection gap — the time a weakness existed before an incident exposed it.
3. **Write action items against latent conditions, not triggers.** "Add a validation rule so this config cannot be pushed invalid" beats "be more careful with config pushes" precisely because it closes the chronic hole instead of reflexively flinching away from the last match struck.
4. **Distinguish preventing this trigger from preventing this class of incident.** Blocking the exact bad deploy is cheap and nearly worthless; fixing the missing gate that let it through prevents the class. Class-level fixes are the only ones that survive the next quarter.

## Watching for latent-condition accumulation before incidents

1. **Run drift detection on config and infrastructure continuously.** Diff production against intended state on a schedule and alert on divergence, so drift surfaces as its own event instead of as a contributing factor in someone's postmortem.
2. **Track bus factor as an operational metric.** "Services with exactly one person who has modified them in 12 months" is a latent-failure inventory. Review it quarterly; schedule pairing or documentation sprints for the top of the list.
3. **Cap workaround age.** Every manual workaround gets an owner and an expiry date. When it expires, it either gets automated or escalates — silently aging workarounds are latent conditions compounding interest.
4. **Treat near-misses as free samples of the future.** The failover that worked but exposed a stale config is the same incident as the real one, minus the damage. Investigate near-misses with the same latent-condition lens and the real incident often never arrives.
