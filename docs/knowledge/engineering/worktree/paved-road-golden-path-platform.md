# paved-road-golden-path-platform

**Issue:** Every organization accumulates N ways to build, test, and deploy a service, and every new service owner must re-choose among them. The paved road (or golden path) answer — an opinionated, preconfigured, supported end-to-end workflow inside an internal developer platform, as defined by Red Hat and popularized through the platform engineering community — makes the recommended way the easiest way. The distinction that 2025 discourse keeps re-emphasizing is guardrails versus railroads: a paved road must be the fastest, safest default while remaining possible to leave, because a mandatory path nobody can deviate from gets routed around, and an optional pile of templates nobody maintains gets ignored. The engineering problem is choosing the road, paving it well, adoption through pull rather than mandate, and funding its upkeep as a product.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Choosing what to pave

1. **Pave the highest-frequency journey first.** The canonical golden path is create-a-new-service through deploy-and-operate: scaffold from a template, CI/CD wired in, secrets, observability, and on-call registration by default. Pick the workflow done most often by the most teams, because pavement value is frequency times pain.
2. **Opinionated, not configurable.** A golden path that offers twelve options per stage is a dirt road with signage. Choose one database driver, one deploy target, one logging shape. Deviations are deliberate exits, not configuration dimensions.
3. **Ship guardrails, never railroads.** Mia-Platform's widely shared framing separates guardrails (secure defaults you can step off with a documented reason) from railroads (hard mandates). Security and compliance belong in the road itself — signed builds, secret scanning, dependency policy — so the compliant path is the lazy path.
4. **Distinguish paved path from golden path scope.** Octopus Deploy's comparison treats the paved path as the well-maintained road across the platform and the golden path as one specific, templated end-to-end route on it. Decide your vocabulary once and write it down; most confusion in this space is definitional.
5. **One road per service archetype, not per team.** Backend services, frontend apps, and batch jobs get distinct roads; teams within an archetype share one. A road per team is bespoke infrastructure wearing platform clothing.

## Building and adopting

1. **Build on an internal developer platform, not a wiki.** The path must be executable — scaffolding CLI, service catalog, self-service actions — with Backstage-style portals being the common substrate. Documentation-only paths measure adoption in readers, not users.
2. **Run the road as a product with a roadmap.** Platform-as-a-product thinking means discovery interviews with consuming teams, a visible roadmap, deprecation policy, and a definition of success measured on the consumer side (time-to-first-deploy, incident rates on-road versus off-road).
3. **Adopt through pull: make the default win.** New services start on the road automatically; existing services migrate when they touch the road for a feature they want (canary deploys, managed secrets). Mandated migrations build resentment and forks; gravity works better.
4. **Make the off-ramp documented and cheap.** When a team must leave the road, they file a deviation record explaining why. Every deviation is free product research: a cluster of them in one area means the road is missing a demanded feature, and the fix is to pave that, not to police the exit.
5. **Instrument the road itself.** Track what percentage of new services were born on the path, how long the scaffold-to-production walkthrough takes, and where teams fall off. A road without telemetry is a template library.

## Sustaining the road

1. **Version and deprecate loudly.** Roads rot faster than the services on them. Semantic-version the templates and platform, announce breaking changes one minor version ahead, and run automated upgrade PRs against on-road services the way dependency bots do for packages.
2. **Fund maintenance headcount explicitly.** The paved road fails when its builders are reassigned the quarter after launch. A small persistent ownership rotation (or a dedicated platform squad) keeps the path updated with every security baseline and toolchain change.
3. **Measure cognitive load reduction, not usage alone.** The point of the road, per Team Topologies lineage, is lowering the cognitive load of stream-aligned teams. Survey teams on how much they must know to ship; if the number is not falling as adoption rises, the road is paving the wrong journey.
4. **Keep the road thinner than you want to.** Thin platforms evolve; fat platforms calcify. Every capability added to the road must displace something a consuming team does today, or it is speculative surface that will need lifetime maintenance.
5. **Retire pavement deliberately.** When two roads overlap after a merger or tooling change, deprecate one with a migration guide and a date. Parallel roads double maintenance and halve trust in either.
