# platform-team-patterns

**Issue:** The company has 60 developers and no platform team — instead, four senior engineers scattered across product teams each maintain fragments of shared infrastructure (one owns CI templates, another the deploy scripts, nobody owns the observability stack). Every product team hand-rolls its pipeline, secrets setup, and scaffolding, so onboarding a new service takes three weeks and a support channel post. Product velocity bleeds out to repeated infrastructure work, and the 2025 State of Internal Developer Portals data lands uncomfortably close to home: developers losing 6-15 hours a week to tool sprawl and context hunting. Leadership approves "a platform team" without specifying what it does, how it measures itself, or how it avoids becoming a ticket queue.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What a platform team is (and is not)

1. **A product team whose customers are developers.** The platform builds an Internal Developer Platform (IDP) — the curated layer of self-service capabilities (scaffolding, CI/CD, environments, observability, secrets) on top of raw cloud. Gartner formalized this market in its March 2025 Market Guide for Internal Developer Portals; it is now mainstream practice, with portal adoption reported by ~94% of surveyed large orgs.
2. **Not an infrastructure ops team with a new name.** If the team's backlog is tickets ("grant me repo access", "restart my deploy"), it is a help desk for the cloud, not a platform. Ops work belongs to the platform only where it is productized into self-service.
3. **Not a standards police.** Mandating tools by decree fails; the platform wins adoption the way any product does — by being the easiest path, not the enforced one.
4. **Team Topologies framing applies.** Platform teams serve stream-aligned teams, ideally through X-as-a-Service interaction: product teams consume capabilities self-serve rather than filing requests. Enabling-team behavior (coaching, temporary embedding) is a bootstrap phase, not the steady state.
5. **Scale check first.** Below roughly 3-5 product teams, a dedicated platform team usually cannot gather enough internal customers to justify itself; shared ownership plus inner-source is the lighter-weight answer until the sprawl bill is real.

## Platform-as-a-product pattern

1. **Developers are customers with a choice.** The foundational 2024-2025 shift: treat internal developers as buyers who can go elsewhere (their own Terraform, a SaaS, a shell script). Every capability must compete on experience, not mandate.
2. **Fund a product manager for the platform.** Someone owns discovery (what do developers struggle with this quarter), a roadmap, and adoption metrics. The most common platform failure is a team of excellent engineers building what they find interesting instead of what unblocks the org.
3. **Run discovery like a product org.** Developer experience surveys, time-to-first-deploy measurements, support-channel mining, and interviews. The portal vendors' 2025 reports all converge on the same finding: the top cost is cognitive load and information hunting, not raw compute.
4. **Publish SLAs and a roadmap.** Self-service only works if it is reliable and predictable: stated response times for platform incidents, deprecation notices, and a visible roadmap turn the platform from a favor into infrastructure.
5. **Measure adoption, not output.** The health metric is "% of new services created via the golden path" and "% of org using the portal", not number of features shipped. A platform with 30% adoption is a hobby with a payroll.

## Golden paths pattern

1. **A golden path is a paved road, not a rail.** It is the preconfigured end-to-end workflow — scaffold a service, get CI, deploys, dashboards, alerts, and secrets wired by default — delivered through the IDP. Teams can leave the path; staying on it must simply be the cheapest option.
2. **The template is the interface.** Golden paths are usually embodied as service scaffolding (`backstage software template`, a repo cookiecutter, a `platform new service` CLI) that bakes in org defaults: languages and framework versions on the tech radar, security baseline, ownership metadata, and on-call registration.
3. **Paved roads beat gates.** The pattern that works: make the compliant path take 10 minutes and the manual path take 3 days, then never formally forbid the manual path. Adoption follows the gradient.
4. **Version the paths, not just the code.** Golden paths degrade when generated services cannot be upgraded; ship codemods and upgrade automation for each path version so the fleet converges instead of forking.
5. **Limit to two or three paths initially.** One web-service path, one worker/cron path, maybe one mobile path. Every additional path multiplies maintenance surface; the "thinnest viable platform" principle says cover the 80% case and let edge cases self-serve on raw infrastructure.

## Portal and tooling layer

1. **Backstage is the default open-source core.** Service catalog, software templates, and plugin ecosystem; expect real engineering effort to run it well (it is a framework, not a turnkey product). Commercial portals (Port, OpsLevel, DX, Cortex) trade that operating cost for license cost — a build-vs-buy decision, not a religion.
2. **The catalog is the minimum viable portal.** Even without templates or scorecards, a single place answering "what services exist, who owns them, where do they deploy, how do I page the owner" eliminates a large slice of the measured 6-15 weekly lost hours.
3. **Scorecards drive standards without police.** Ownership metadata, alert coverage, upgrade lag, and security posture surfaced per service create social pressure toward the standard — visibility as governance, which pairs naturally with a tech radar.
4. **AI assistance is the 2026 frontier, not the foundation.** Portal vendors are adding AI agents for scaffolding, doc lookup, and incident support; adopt where it removes toil, but do not let it substitute for the boring catalog-and-templates core that adoption actually depends on.

## Anti-patterns and failure modes

1. **The ticket-shaped platform.** Capabilities delivered as request forms instead of self-service; throughput caps at the platform team's size and everyone is unhappy. Every recurring ticket is a backlog item for productization.
2. **The unaccountable commons.** A platform "owned by everyone" via inner-source with no maintainers — contributions stall, the platform rots, and teams fork. Inner-source works for extensions; the core needs named owners with allocated capacity.
3. **Building the platform before the product.** Six months of portal engineering with zero developer touchpoints. Ship the catalog in week one, template in month one, and iterate in public with real users.
4. **Gold-plating.** A four-portal, twelve-golden-path platform at 60-developer scale. TVP discipline: if removing a capability would not cause an outage or a revolt, remove it.
5. **Ignoring the exit costs.** Platform choices (portal framework, template conventions, deploy abstraction) create lock-in for every service built on them; record ADRs for platform decisions and keep an escape hatch to raw infrastructure so the paved road never becomes a canyon.

## Related
- `tech-radar-governance.md` (what the golden path defaults to)
- `build-vs-buy-decision-framework.md` (Backstage vs commercial portals)
- `inner-source-guidelines.md` (contribution model at the edges)
- `engineering-kpis-dashboard.md`, `developer-productivity-metrics.md`
- `devcontainer-environment-standardization.md` (one concrete golden-path capability)
