# incident-handoff-cross-timezone

**Issue:** Follow-the-sun rotations end the era of one engineer carrying an incident from page to resolution — and introduce the moment where incidents go to die: the handoff. When the EU shift ends mid-incident, everything the responder learned (which hypotheses are dead, which mitigations were tried and reverted, which logs are the useful ones) exists only in their head and their 3 a.m. Slack messages. The incoming region restarts debugging from zero, re-runs the dead ends, and hands back an incident that is now four hours older. Cross-timezone incident response succeeds or fails almost entirely on handoff discipline, not on any region's individual debugging skill.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The baton-pass rule

1. **One named owner at every moment, across all regions.** "The incident" is never owned by a team or a channel; it is owned by a person, and the handoff is an explicit transfer of that ownership ("you have the baton as of 14:02 UTC") — acknowledged before the outgoing responder signs off. Ambiguous ownership is how an incident sits unwatched through two time zones.
2. **Stabilize before handing off; never bounce mid-flight.** If a mitigation is half-applied or a risky rollback is mid-execution, finish or safely pause it before the transfer. Passing an unstable system plus a partial action is handing the next region a live grenade; passing a stable-but-broken system is handing them a solvable problem.
3. **Hand off forward, not sideways.** If the incoming region lacks the expertise to receive the baton, that is an escalation now, not a discovery an hour later. Route to whoever can actually hold ownership, even if it means waking someone — a deliberate wake is cheaper than an unowned incident.
4. **The outgoing responder stays reachable for a defined window.** Fifteen to thirty minutes of overlap after handoff catches the "wait, which dashboard?" questions while they're cheap. After that window, the handoff doc is the only interface — which is why the doc must be complete.

## The handoff document

1. **Write it in the incident channel, from a template, every time.** The 2026 on-call guides converge on the same fields: current status, customer impact, full timeline of actions taken (including what was tried and reverted), current hypothesis, evidence gathered (links to dashboards, logs, queries that mattered), explicit next steps, and open questions. A two-minute checklist beats an exhaustive essay — completeness of fields, not length, is the standard.
2. **Dead ends are the most valuable section.** "We ruled out the CDN and the auth service; the 503s correlate with worker restarts" saves the next region an hour. A handoff doc that omits what failed converts two regions' work into one region's work plus a rerun.
3. **State the hypothesis with its confidence, not as fact.** "We believe it's the queue consumer (60% confident, based on lag correlation)" lets the incoming owner re-verify cheaply. Stating hypotheses as facts is how a wrong early guess hardens into an incident-long detour across three time zones.
4. **Include the customer-comms state.** What has been posted to the status page, what the support team has been told, and when the next update is due. An incoming region that misses this either goes silent (customers panic) or contradicts the last update (customers leave).

## Scheduling and time-zone fairness

1. **Build handoff overlap into the rotation, not into heroics.** Shift boundaries should sit where regions naturally overlap by an hour so the handoff conversation can be verbal (video or voice) at least for SEV1/SEV2 — spoken handoffs catch gaps that written ones hide, and the overlap makes them free.
2. **Rotate who gets the ugly hours.** If a region's shift end always lands mid-incident, that team absorbs all the handoff writing burden and the interrupted dinners. Rotate shift boundaries periodically so handoff pain is shared rather than structurally assigned to one geography.
3. **Timeboxed incidents that cross two handoffs get an incident commander appointed explicitly.** After 16+ hours, no individual context survives intact; someone must own the written record as their primary job, because the record — not any person — is now the continuity of the response.

## Verifying the handoff landed

1. **Read-back at transfer.** The incoming owner summarizes the situation back in two or three sentences before the outgoing owner leaves. Misunderstandings surface in sixty seconds of read-back that would otherwise surface an hour into a wrong debugging path.
2. **Keep the canonical doc in one shared place, updated at every handoff.** Not three regional channels and a DM thread. Every region must open the same link and see the same current state; regional side-channels are for discussion, the doc is for truth.
3. **Run a handoff fire-drill quarterly.** Stage a synthetic incident that must survive two handoffs end-to-end. Drills expose the predictable failures — stale escalation paths for the incoming region, template fields nobody fills in, overlap windows that don't actually overlap — before a real incident pays for the lesson.
4. **Score handoff quality in the postmortem.** For any multi-region incident, ask: did the next region re-run dead ends? Did ownership gap at transfer? Treat a bad handoff as a contributing cause with its own action items — it is a process failure, not regional incompetence.
