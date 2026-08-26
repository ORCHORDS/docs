# backlog-grooming-cadence

**Issue:** Backlog refinement fails in two symmetric ways. Done too rarely, the backlog decays: items go stale, estimates no longer reflect reality, the top of the queue is never actually ready, and sprint planning turns into a two-hour archaeology session. Done as one marathon session, it exhausts the team — attention collapses after an hour, the top ten items get real discussion while item 200 gets a drive-by point value, and everyone learns to dread the meeting. Both failures trace to the same root: treating refinement as an event rather than a cadence. A deliberate, appropriately sized rhythm keeps one to two sprints of work genuinely ready, retires dead items before they accumulate, and keeps planning short. This article covers setting the cadence, running the sessions, and what "done" looks like for refinement.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Setting the cadence

1. **Default to once per sprint, mid-sprint.** The prevailing guidance across current agile references is a recurring session weekly or once per sprint — same day, same hour, treated as a standing obligation like standup. Mid-sprint placement matters: refinement conducted the day before planning is rushed, and refinement the day after planning has nothing new to refine. Mid-sprint gives discussion time to settle before items are pulled.
2. **Budget up to ten percent of capacity, with a floor.** Scrum Alliance guidance sets roughly three hours per sprint as a minimum for a typical team; Mountain Goat and 2025 agile guides frame the ceiling as five to ten percent of capacity. Below the floor, refinement is performative; above the ceiling, it is cannibalizing the building it exists to support.
3. **Split large sessions rather than stretching one.** Two 60-90 minute sessions beat one three-hour grind — attention economics dominate refinement quality, because estimation is judgment work and judgment degrades fast. The failure signature of the marathon is precise discussion of the first five items and reflexive pointing of everything after.
4. **Adjust frequency to team context, deliberately.** Weekly suits new teams, fast-moving products, or a backlog recovering from neglect; mature teams with a stable product often hold refinement less often because items need less repair. Atlassian's guidance is to start weekly and adjust on evidence — session length consistently ending early means the cadence can stretch, sessions overflowing every time means it cannot.
5. **Keep the cadence fixed even when the backlog feels clean.** The temptation to skip "because the queue is ready" is how the queue silently stops being ready; the session shrinks or ends early, but the slot survives.

## Running a refinement session

1. **Prepare the agenda before the meeting.** Current best practice consistently names this: the facilitator (typically the product owner with help) walks the backlog beforehand and brings the specific items needing discussion — new candidates, changed items, oversized ones, stale suspects. An unprepared refinement meeting spends its first half deciding what to talk about.
2. **Work the top of the backlog hardest.** The session's job is producing ready work — refined, estimated, sized-to-fit items with acceptance criteria — one to two sprints deep. Deep-backlog triage is out of scope except for the deletion pass below; precision-pointing item 400 is waste in a costume.
3. **Split anything that cannot fit comfortably in a sprint.** An item bigger than roughly half a sprint is a hazard: it cannot start late, it rolls when it slips, and its estimate is a guess. Refinement is where splitting happens — by capability slice, by workflow step, by spike-then-implement — not in planning under time pressure.
4. **Apply a quick deletion pass to the tail.** Each session ends with a fast review of stale candidates — superseded requests, items whose problem disappeared, duplicates the labeling and staleness rules flag. Explicit closure with a one-line reason keeps the backlog a working queue instead of an archive; this is the human complement to the staleness automation.
5. **Time-box per-item discussion.** A common rule: fifteen minutes of discussion, then either estimate with the uncertainty noted, or split the item, or park it for offline investigation. Open-ended per-item debate is what turns a 90-minute session into a three-hour one.

## What a healthy cadence produces

1. **A ready buffer of one to two sprints.** The concrete outcome of good refinement: planning pulls from prepared items and finishes in half the time, because the estimation and splitting already happened. When planning regularly overruns into estimation territory, refinement is underproducing.
2. **Estimates the team would give again today.** Items older than a couple of sprints with unchanged estimates are suspect — dependencies shifted, scope crept in conversation. A healthy cadence touches the ready buffer often enough that estimates stay fresh.
3. **A backlog the team can explain.** Anyone in the session can say why the top items are the top items. A queue only the product owner understands produces silent dissent and mid-sprint surprises.
4. **Shrinking session length at stable throughput.** A steady rhythm with a clean queue naturally shortens sessions — the maintenance mode of a healthy backlog. Sessions getting longer sprint over sprint is the early indicator of backlog decay or intake acceleration, visible weeks before planning feels it.

## Common cadence failures

1. **The emergency-cancel spiral.** Refinement gets cancelled for urgent work, the next planning runs long and messy, which generates confusion that eats more time, which cancels the next refinement. Break it by holding a deliberately short session — even 30 minutes — rather than skipping.
2. **Refinement as PO monologue.** The product owner reading items aloud while the room points is not refinement; estimation accuracy comes from engineers interrogating the item. The session needs the people doing the work, and their questions are the product.
3. **Grooming only new items.** Refining arrivals while never revisiting the existing queue produces a two-tier backlog: beautifully specified new items atop an ossified mass nobody trusts. The deletion and refresh passes exist to prevent exactly this.
4. **Mistaking grooming for planning.** Refinement prepares and orders the backlog; it does not commit work, assign people, or set sprint goals. Sessions drifting into planning commit the next sprint's capacity two weeks early and get invalidated by reality within days.
