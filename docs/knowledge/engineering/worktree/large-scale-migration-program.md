# large-scale-migration-program

**Issue:** Every engineering organization eventually runs a migration too big for a single quarter: monolith to services, one cloud to another, a deprecated framework out of every repository. The default failure mode is the big-bang rewrite — a parallel new system built over 18 months while the old one keeps moving — which Thoughtworks, Martin Fowler's Patterns of Legacy Displacement work, and the cloud vendors' strangler-fig guidance all describe as the highest-risk option available. The strangler fig pattern, canonically documented in the Azure Architecture Center and AWS Presitive Guidance, replaces the system incrementally by routing traffic around a facade, so the organization ships value continuously and can stop or redirect the program at any checkpoint. The engineering problem is program design: slicing the old system, keeping double-running honest, funding the finish, and resisting the halfway-abandoned state that consumes years of work.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Choosing the strategy

1. **Default to incremental, justify big-bang in writing.** Incremental strangler migration reduces risk, preserves the ability to ship features, and produces checkpoints where the program can be reassessed. A big-bang cutover is occasionally correct (tiny systems, hard technology incompatibility, contractual deadlines), but it should require a written decision record that names the risk owner.
2. **Build the facade before building the replacement.** Put a routing layer (reverse proxy, API gateway, event bus) in front of the legacy system first. Once traffic flows through the facade, functionality can be moved behind it one slice at a time with no customer-visible change — the essence of the pattern in both the Azure and AWS guidance.
3. **Slice by business capability, not by technical layer.** Migrating "all the data access" couples every team to every step; migrating "invoicing" ends-to-end delivers something demoable and reversible. Vertical slices keep each increment independently valuable.
4. **Prefer event-driven strangulation where reads must stay live.** For systems where dual-write consistency is the hard part, the event-streaming variant of the pattern (Conduktor's overview is representative) publishes changes from the legacy system as events that materialize the new system's state, then flips read traffic.
5. **Score each slice for value and difficulty.** Sequence early slices to maximize learning (one moderately hard, clearly valuable capability) so the program's real migration cost per slice is calibrated before the hard 20 percent arrives.

## Keeping the program honest

1. **Freeze scope expansion on the legacy path.** The strangler dies when new features keep landing in the old system faster than migration removes it. Institute a policy: changes to not-yet-migrated capabilities must either land in the new system or carry a migration-scope amendment approved by the program owner.
2. **Double-run with real traffic, not synthetic.** Shadow or parallel-run phases (the OneUptime implementation guide covers the common shapes) only build confidence when fed production traffic, with divergence between old and new paths measured and alarmed like a real SLO.
3. **Make progress visible with a migration dashboard.** A single chart — percentage of traffic, endpoints, or entities served by the new system, updated by telemetry rather than status meetings — keeps the program from becoming a quarterly estimate ritual.
4. **Fund the last mile at kickoff.** The final slices are always the hardest (the weird edge cases nobody owns). Reserve capacity for them in the original plan, and set an explicit finish-line definition: legacy code path deleted, not merely bypassed. A strangler that leaves the old system running "just in case" is an unfinished migration paying twice the cost.
5. **Checkpoint every slice with a kill/continue decision.** After each completed slice, the program owner should re-affirm continuation with data: actual cost per slice versus plan, feature velocity maintained, and risk discovered. Incremental migration's chief advantage is that stopping early is cheap.

## Organizing the work

1. **One accountable owner, many contributing teams.** A migration is a program, not a committee. A single owner controls sequencing, the scope-freeze policy, and the kill/continue decisions, while stream teams execute slices inside their normal backlogs.
2. **Budget feature work and migration work in the same heads.** Separate "migration team" and "feature teams" create an us-versus-them dynamic and a handoff problem at every slice. A fixed allocation per team (for example 20 percent to migration slices) keeps the knowledge in the teams that will operate the result.
3. **Write the displacement patterns down.** Document which legacy displacement technique (parallel run, expansion-contraction, event diversion, facade routing) applies to which slice class, so each new slice starts from a playbook rather than a debate.
4. **Treat data migration as its own workstream.** Schema moves, backfills, and dual-write windows are usually riskier than the code. They get their own rollback plans, their own game-day rehearsal, and their own slice-level metrics.
5. **Retire aggressively upon completion.** Decommissioned code, dashboards, alerts, and runbooks are removed on a dated schedule once traffic hits zero. The measure of a finished migration is deleted repositories and closed runbooks, not a memo.
