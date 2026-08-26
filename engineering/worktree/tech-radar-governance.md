# tech-radar-governance

**Issue:** Technology decisions at the org happen by entropy: one team adopts a new ORM, another picks a different one, a third rolls a bespoke version of both, and eighteen months later the same three problems are solved three ways with three sets of CVEs to patch. When someone proposes consolidating, there is no record of why any choice was made or who decided it. Leadership wants "some governance," but the only model anyone can name is the ThoughtWorks radar, and importing a publication's opinion list does nothing for internal decision-making. The org needs its own radar with its own process — without turning it into a change-control board.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What a tech radar is (structure worth copying)

1. **Two axes: quadrants and rings.** ThoughtWorks' format — in continuous publication, with Vol. 32 in April 2025 and Vol. 33 in October 2025 — sorts blips into four quadrants (Techniques, Tools, Platforms, Languages & Frameworks) and four rings (Adopt, Trial, Assess, Hold). The structure is the durable idea; the specific blips are theirs, not yours.
2. **The rings are adoption stages, not quality grades.** Adopt means "proven here, use it by default." Trial means "worth using on projects that can absorb risk." Assess means "worth exploring to understand impact on us." Hold means "proceed with caution or avoid new use" — a ring that only makes sense relative to your own context.
3. **A blip is a decision with a date.** Each entry records what it is, which ring it sits in, why, and when it moved. That timestamping is what turns opinion into auditable governance.
4. **It is a snapshot, not a law book.** The reference radar publishes twice a year; the value is the regular re-decision, not the artifact. An internal radar updated once and left to rot is worse than none, because it lends stale choices false authority.

## Building the internal process

1. **Start from observed reality, not aspiration.** Seed the radar by inventorying what is actually in production today and placing those technologies in rings — including the embarrassing Hold entries. A radar that only lists approved tech gets ignored by people running the unapproved tech.
2. **Define who can propose a blip.** The healthy default: any engineer proposes, the radar council (a rotating group of senior engineers plus security and platform representation) dispositions. Restricting proposals to leads kills the bottom-up signal the radar exists to capture.
3. **Give every blip an owner and a review date.** Assess entries especially need a named owner who will run the evaluation and a date by which the entry moves or dies. Unowned Assess blips are where radars go to accumulate cruft.
4. **Require evidence for ring movement into Adopt.** The bar should be: one production use inside the org, one team willing to be the reference, and a support story (who patches it, who answers questions at 3am). Trial requires only a sandbox and a volunteer.
5. **Publish decisions where developers already are.** The radar must live in the internal portal or repo READMEs, not a PDF behind a wiki login; link each ring entry to its ADR so the reasoning is one click away.

## Ring movement rules (the governance teeth)

1. **Default to Trial, not Adopt.** The failure mode of new radars is fast-tracking a favorite tool straight to Adopt on one team's enthusiasm. Trial exists to collect organizational evidence first.
2. **Hold is about pacing, not bans.** Marking a technology Hold means "no new first use without a waiver" — existing systems are grandfathered with a documented exit. Using Hold as a silent ban drives usage underground where the radar cannot see it.
3. **Everything in Hold or Adopt needs an escape hatch.** A one-paragraph waiver process (owner, reason, expiry) keeps the radar honest; zero waivers granted in a year means the rings are either perfect (unlikely) or ignored.
4. **Demotions are mandatory and public.** When a tool fails us, gets acquired and enshittified, or stops shipping security patches, move it to Hold with a note. A radar that only promotes loses credibility with exactly the skeptics governance needs to win.
5. **Two strikes for orphaned blips.** If an Assess entry misses two consecutive review cycles with no owner activity, delete it. Pruning is what keeps the radar readable enough to be consulted.

## Operating cadence

1. **Quarterly council, twice-yearly publication.** Disposition proposals quarterly (fast feedback for proposers); publish the consolidated radar twice a year. This mirrors the cadence proven by the reference radar and fits normal planning rhythms.
2. **Batch review by quadrant.** Reviewing all Tools blips together surfaces contradictions (four overlapping observability tools) that item-by-item review misses — the radar's real power is pattern visibility, not item adjudication.
3. **Feed the radar from incidents and audits.** Dependency audits, postmortems, and license scans are automatic blip-proposal sources; a tech that keeps showing up in incident reports belongs in front of the council regardless of who proposed it.
4. **Track a small set of metrics per Adopt blip.** Number of production uses, mean upgrade lag, and open CVE exposure. These make the next ring decision data-driven instead of vibes-driven.
5. **Time-box the whole mechanism.** A council that meets more than ~2 hours a quarter per quadrant has become a change board; cut scope, delegate Trial decisions to teams, and keep council attention for Adopt/Hold moves.

## Anti-patterns

1. **The veto board.** If the radar's practical output is "no" with six weeks of lead time, teams route around it and shadow tech spreads faster than before. Governance by paved road beats governance by gate.
2. **Copying ThoughtWorks rings verbatim.** Their Adopt is an opinion for their client contexts. A startup that treats their Hold list as its own will reject tools perfectly suited to its scale, and vice versa.
3. **The 300-blip radar.** Coverage of every npm library makes the artifact unusable; scope to choices with switching costs — databases, frameworks, cloud services, paid tools, cross-team standards.
4. **Radar as resume policy.** Entries promoted because a senior engineer wants to learn the tech on work time. The Trial ring exists partly to sandbox exactly this energy — let it, but with the evaluation owner accountable for the verdict.
5. **No linkage to ADRs or budget.** A ring assignment that does not connect to a written decision record, and to who pays for the license or the migration, is decoration. Every Adopt entry should answer "who funds this and who undoes it."

## Related
- `adr-architecture-decision-records.md` (per-decision reasoning)
- `rfc-request-for-comments-process.md` (the proposal pipeline)
- `dependency-management-2026.md`, `sbom-licenses-2026.md` (automatic blip feeds)
- `inner-source-guidelines.md` (council as enabling, not gating)
