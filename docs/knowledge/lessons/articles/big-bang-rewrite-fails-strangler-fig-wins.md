# big-bang-rewrite-fails-strangler-fig-wins

**Issue:** A team inherits a working but ugly legacy system, decides to rebuild it from scratch on a modern stack, promises delivery in six months, and two years later is still "three months away" while the legacy system keeps running, the old team quit, and the business has paid twice for one product. This article captures the recurring failure pattern of big-bang rewrites — the second-system effect in modern dress — and the incremental alternative (strangler-fig migration) that ships value the whole way through. 2025-era case metrics reinforce the lesson: even incremental modernization programs stall ~68% of the time before 90 days without governance, so the pattern alone is not a silver bullet either.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How the failure unfolds

1. **The "six-month rewrite" estimate is written before anyone reads the old code.** The estimate covers what the team can see — the UI and the API surface — but the value of the legacy system lives in the accumulated edge cases nobody remembers: the weird tax rule, the customer with a nonstandard contract, the workaround for a deprecated partner API. Every one of these is rediscovered only in production, after launch.
2. **Feature freeze on the old system rots it.** To "focus", the team stops maintaining the legacy system, so every urgent business change gets pushed onto the rewrite's backlog, which grows the rewrite's scope and pushes the finish line further out. The old system gets blamed for decaying, but the freeze caused the decay.
3. **The rewrite must reach 100% parity before it can replace anything.** Because the new system was designed as a whole, none of it is usable until all of it is done — an all-or-nothing delivery risk where the project delivers zero value for its entire duration. The business watches two years of engineering salary produce nothing shippable.
4. **Sunk-cost pressure forces a bad launch.** Around month 18, leadership demands a date. The team launches with known gaps, then runs both systems in parallel to patch the gaps, doubling operational cost precisely when morale is lowest. The postmortem later shows the cutover incident was the most expensive outage of the year.
5. **Requirements drift splits the design.** The business does not stop evolving while you rewrite. Halfway through, the new system's architecture no longer matches what the product now needs, so the team either re-plans (delay) or ships an already-outdated design (re-rewrite next year).

## Root causes

1. **The old system looks simpler from outside than it is.** Code you haven't read feels like a weekend of work; the irreducible complexity of years of bug fixes is invisible in a demo. Joel Spolsky's classic observation holds: the legacy code is the specification, and throwing it away throws away the only working spec.
2. **The second-system effect inflates the design.** The rewrite adds every feature the old system "should have had" — plugin architecture, multi-tenancy, real-time everything — instead of copying what exists. Scope the rewrite to what is demonstrably used, not to what is imaginable.
3. **Estimates are anchored on greenfield velocity.** A rewrite starts fast (scaffolding, CRUD, demos) which anchors everyone's expectations, then hits the long tail of edge cases where velocity drops 5-10x. Nobody re-baselines the estimate when the tail appears.
4. **Political incentives reward starting a rewrite, not finishing one.** Announcing a modernization wins budget and headcount; grinding through migration tooling for month 14 wins nothing. Whoever inherits the project mid-way has no ownership of the original vision and quietly deprioritizes it.
5. **No feedback loop exists until the end.** Because nothing ships until cutover, the first real signal about correctness arrives at the worst possible moment. A 2025 case-study analysis of modernization programs found a majority of efforts stall within 90 days precisely when early governance signals are missing.

## What to do instead: strangler-fig migration

1. **Put a facade in front of the legacy system first.** Route all traffic through a proxy or routing layer you control, then move routes one by one to new implementations behind it. The facade is the single most important artifact — it converts "replace the system" into "replace one endpoint at a time".
2. **Migrate by vertical slice, not by layer.** Replace one complete user-facing capability (e.g. "invoice PDF generation") end to end, not "the data layer" or "auth everywhere". A vertical slice is shippable, observable, and revertable on its own; a horizontal layer is none of those.
3. **Ship each slice to production behind a flag with dual-run comparison.** Run old and new implementations side by side, compare outputs on real traffic, and cut over per-slice only when the diff is clean. This turns the migration into dozens of small reversible bets instead of one irreversible one.
4. **Delete legacy code as you go.** The fig must strangle: every migrated slice removes the corresponding old code path immediately. Teams that leave the old path "just in case" end up maintaining three systems — old, new, and the switching layer.
5. **Time-box a kill decision at 90 days.** Because even incremental programs stall (the 2025 metrics show ~68% stalling before 90 days), set an explicit checkpoint: if less than ~10% of traffic has migrated by day 90, stop and re-plan rather than letting the effort zombie on for years.

## If a rewrite is truly unavoidable

1. **Write down the kill criteria before you start.** Define the budget ceiling, the calendar ceiling, and the parity bar in advance, and agree who has authority to cancel. A rewrite with no pre-agreed exit becomes uncancellable by construction.
2. **Freeze the old system's scope, not its maintenance.** Keep the legacy system patched, monitored, and deployable — you may be married to it far longer than planned — but route all new features to the new system so the rewrite has a forcing function.
3. **Budget for the long tail explicitly.** Reserve 50-100% of the "visible work" estimate for edge cases discovered during parity testing, because that is the historical ratio, not pessimism.
4. **Keep the old team or the old code reachable.** Re-writes fail on tribal knowledge, not on syntax. Pair a legacy maintainer with the rewrite team, or pay for archaeology (tests written against the old system's behavior) before deleting anything.
5. **Deliver partial value early.** Even in a rewrite, find a way for the new system to serve some real traffic within the first quarter — a new module, a new tenant, a new region. A rewrite that cannot show value in 90 days will not show it in 900.
