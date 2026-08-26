# issue-staleness-automation

**Issue:** The backlog fills with issues that have had no activity for six months: bugs that may have been silently fixed by unrelated refactors, feature requests whose champions left, and questions answered in the comments but never closed. Nobody can tell living work from dead weight, so planning meetings drown in zombie issues and genuinely important old bugs hide among the clutter. The team reaches for a stale bot, but automated closers are widely hated — communities have open petitions to ban them — because an unattended bot closes confirmed bugs "as not planned" and locks out the people who still care. The problem is not whether to automate aging, but how to do it without torching reporter trust.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Aging policy design

1. **Define staleness before automating it.** Staleness means "no activity and no owner progression in N days", not "no comments in N days" — a quiet issue with an assigned owner mid-sprint is not stale, and a loudly bumped issue with no triage can be.
2. **Tier the windows by issue type.** Questions and support requests rot fast (30 days); unconfirmed bug reports age slower (60-90 days); confirmed bugs and roadmap-tagged items never auto-close at all.
3. **Distinguish stale from parked.** Issues deliberately waiting on upstream or a future milestone need an explicit `parked` or `roadmap` state so the robot can exempt them rather than guess.
4. **Let the first pass only label.** The consensus from the probot/stale issue threads: marking stale is fine for a machine, closing is a human act — a stale label plus a warning comment achieves most of the hygiene with none of the harm.
5. **Make activity mean signal, not noise.** A "+1" comment should not reset the clock indefinitely; configure the marking action so only substantive events (label changes, assignment, linked PRs, maintainer comments) count as activity.

## Safe automation configuration

1. **Long windows, generous grace.** Community guidance for actions/stale clusters around 60-90 days to stale and 14-30 days from warning to close; single-digit-day windows read as hostility and destroy good reports.
2. **Exempt labels are load-bearing.** Configure `exempt-issue-labels` for confirmed, security, pinned, roadmap, and good-first-issue-claimed so the bot never touches protected classes.
3. **Exempt milestones and assignees.** Anything scheduled into a milestone or assigned to a human is committed work; a bot closing it is a process violation, not hygiene.
4. **Custom, honest warning text.** The stale comment must say exactly what will happen, when, and how to prevent it ("comment or remove the label"), and must not claim the issue was resolved.
5. **Run the bot in dry-run first.** Every staleness rollout needs a reporting-only period where the bot comments but never closes, so the team can audit false positives before any irreversible action.
6. **Sandbox the credentials.** The workflow uses a dedicated token scoped to issue write; a misconfigured cron with a broad token can wreak remarkable damage overnight.

## The "not planned" trap

1. **Never auto-close confirmed bugs as "not planned".** GitHub renders closed-not-planned issues with a gray completed-strike treatment and locks further discussion — for a real, unfixed bug that is a lie plus a lock, and it is why ban-the-stale-bot petitions exist.
2. **Reserve "not planned" for human decisions.** Closing as not planned means a person weighed the request and declined; a timer doing it converts inactivity into an implied product decision nobody made.
3. **Prefer close-as-stale with reopen-friendly wording.** If auto-closing inactivity is truly needed, the closing comment must invite reopening if the problem persists, and reopenings must be honored without friction.
4. **Keep discussion unlocked.** Locking the thread of an auto-closed issue silences the exact people whose input would prove the issue alive; leave discussion open unless spam forces otherwise.
5. **Offer a rebuttal channel.** Some maintainers have stopped closing stale issues entirely and instead surface them in a periodic digest for human close/not-planned calls — slower, but it keeps the decision where it belongs.

## Measuring staleness health

1. **Track the stale-label population weekly.** A steadily growing stale count with a flat close count means the policy marks but nobody triages — finish the loop or shorten the funnel.
2. **Audit reopen rates.** A high share of auto-closed issues getting reopened and fixed means windows are too aggressive; near-zero reopens with no complaints means the policy is about right.
3. **Sample closed issues monthly.** Pull ten bot-closed issues and check whether each was genuinely dead; publish the result so contributors can trust the automation.
4. **Watch the silent-loss metric.** Compare bugs reported before and after staleness rollouts that never got fixed — auto-close policies that suppress resurfacing create invisible quality debt.

## Recovery and upkeep

1. **Re-open ruthlessly when wrong.** When a bot-closed issue turns out to be real, reopen, apologize in one line, and exempt the label going forward — the apology is cheap and the trust is not.
2. **Re-triage stale-closed issues at major releases.** Land a big refactor and a chunk of the closed-stale backlog may have silently fixed or worsened; batch-check the top symptoms.
3. **Keep the config in review.** The stale workflow file changes with the same scrutiny as production code, because on a busy tracker it effectively is.
