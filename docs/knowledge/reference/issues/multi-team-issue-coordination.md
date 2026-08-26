# multi-team-issue-coordination

**Issue:** Team A's launch issue is stuck, and nobody on A knows why — the blocker lives in Team B's tracker, expressed as a B-side ticket that mentions the launch only in a comment. A discovers this two weeks late by word of mouth, B's standup has been deprioritizing the ticket because "nobody's waiting on it", and the launch date silently slips. Multiply by every cross-team interface and the org runs on surprise: dependencies surface at integration time instead of planning time, priorities collide in hallway conversations, and each team's board tells a flattering, local story. The failure is structural — dependency state is not modeled anywhere both teams can query. The fix combines native tooling (GitHub issue dependencies shipped August 2025, cross-repo references) with an explicit ownership and escalation contract between teams.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Modeling dependencies

1. **Use native blocked-by/blocking relationships.** GitHub's issue dependencies feature (Relationships section in the issue sidebar, live since the Aug 2025 changelog; up to 50 links per issue) makes "blocked by #N" a queryable fact instead of prose — every cross-team dependency gets recorded this way.
2. **Link issues, not people.** "Ping Maria when B is done" fails the moment Maria is on leave; a linked issue auto-surfaces on close and survives personnel changes.
3. **One edge per real dependency.** If A needs B's API and B's API needs infra's migration, model the chain explicitly (A → B → infra) rather than compressing it into one issue; compressed chains hide the actual critical path.
4. **Mark the strength of the block.** Distinguish hard blocks (cannot start) from soft ones (can build behind a flag) in the issue body, because a team that sees only hard blocks either ignores real ones or gold-plates fake ones.
5. **Cross-repo goes through references too.** For dependencies spanning repositories, linked issues with the same canonical title plus a shared tracking label or Project keep the chain visible from either side; third-party tools (e.g. ZenHub-style dependency graphs) remain the fallback for orgs needing heavyweight visuals.

## Ownership and interface contracts

1. **Every dependency has one accountable team.** The blocked issue names the owning team in the link's target; dependencies without an owner are risks, not plans, and get escalated at discovery.
2. **Write the interface, not just the need.** The blocking issue states exactly what artifact unblocks the waiter (schema, endpoint, flag, contract test) so "done" is checkable by both sides without a meeting.
3. **Two-way priority visibility.** The blocking team must be able to see who waits on the ticket and how hard (customers? launch? compliance?) — priority collisions need that data, and hidden waiters get silently deprioritized every time.
4. **No silent re-scoping.** If the blocking team changes scope or ETA on a linked issue, the change is commented on the blocked issue in the same session; the link exists precisely to broadcast this.
5. **Record agreed ETAs on both issues.** A date promised in a sync call is invisible to every future reader; a date written into both linked issues survives the call, the quarter, and the reorg.

## Escalation flow

1. **Define the aging ladder in advance.** For example: blocked >5 working days → team leads sync; >10 → sprint-level replan with the waiter informed; >20 → named arbitrator decides; printed in the coordination doc so escalation is process, not conflict.
2. **Escalate the dependency, not the person.** The escalation artifact is the linked pair of issues plus the SLA breach — it should read like a milestone slipping, not an accusation.
3. **Give the waiter a plan B lane.** A blocked team must always be able to show what it ships instead; a team that is 100% blocked by another has a planning failure of its own.
4. **Escalations end in writing.** Whatever is decided lands as edits on the issues (new dates, descoping, unblocking workaround) or it did not happen.

## Cadence and planning

1. **A shared view above the teams.** One org-level Project or board aggregating cross-team-linked issues, reviewed in a recurring cross-team sync, is where collisions get caught while they are still cheap.
2. **Plan against the dependency graph, not the local board.** During planning, each team pulls its issues' blocked-by states first; scheduling work whose blocker is red is how launches "suddenly" slip.
3. **Reconcile links at the boundary.** When work transfers between teams (component handoff, service split), the handoff PR or doc includes re-pointing every dependency edge — orphaned links are the multi-team version of stale labels.
4. **Keep a dependency review in retro.** Each retro asks: which blocks lasted longer than the ladder allowed, and which were discovered late; both answers feed the coordination doc.

## Anti-patterns

1. **Duplicate tracking.** Filing a copy of the other team's ticket "so it's on our board" creates two sources of truth that diverge within a sprint; reference and link instead of cloning.
2. **Comment-only dependencies.** "Depends on what B is doing" in a comment is invisible to every query, every automation, and every new team member — if it matters, it is a linked relationship.
3. **The mega tracking issue.** One giant cross-team launch issue with a checklist hides per-team ownership and blocks fine-grained dependency edges; use it only as an umbrella over properly linked children.
4. **Weaponized blocking.** Linking seventeen blockers to shield a team from commitment makes the graph noise; audit links for real block-strength during planning.
5. **Assuming tooling solves culture.** Native dependency links make the state visible, but the escalation ladder, the two-way priority visibility, and the written-ETAs rule are what make anyone act on it.
