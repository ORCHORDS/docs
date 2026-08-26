# polyrepo-vs-monorepo-tradeoffs

**Issue:** The engineering org has grown from one team with one service to five teams with fourteen services scattered across twenty-odd repositories. A rename of a shared auth library now takes nine coordinated PRs across three weeks, while two teams quietly maintain divergent forks of the same utility code. Leadership proposes "moving to a monorepo" and the room splits: half the leads cite Google and Uber, the other half predict CI meltdowns and lost ownership boundaries. Nobody has written down the actual tradeoffs, so the debate re-runs every quarter with anecdotes instead of criteria.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What each topology actually optimizes for

1. **Monorepo optimizes for change across boundaries.** One atomic commit can touch the API, the clients, and the shared library together, and CI validates the combined result. Uber reported roughly 60% lower build times and ~40% higher developer productivity after its monorepo migration, mostly from atomic cross-service changes.
2. **Polyrepo optimizes for autonomy and isolation.** Each team owns its repo, its release cadence, its access control, and its blast radius. Nothing another team does can break your build at 2am unless it flows through a published contract.
3. **Neither topology fixes Conway's law.** A monorepo over a fractured org just hides the seams; a polyrepo over a tightly coupled system just makes the seams hurt more. Match the repo layout to how work actually flows, not to how you wish teams were shaped.
4. **The default polyrepo is not neutral.** Most orgs did not "choose" polyrepo — they accreted it one service at a time. Its real costs (version skew, copy-pasted utilities, cross-repo change choreography) are paid silently, which is why the monorepo pitch keeps winning arguments on paper.

## Monorepo advantages (what you gain)

1. **Atomic cross-project changes.** A single PR updates the library and every caller, reviewed in one place with one CI run on the combined diff. This is the single biggest measured productivity driver in the Uber and Google accounts.
2. **Code sharing without publishing.** Shared utilities live next to consumers; you refactor them with IDE-wide visibility instead of cutting a new package version and hoping consumers upgrade someday.
3. **Unified tooling and standards.** One lint config, one CI definition, one CODEOWNERS map, one dependency policy. Standards are enforced by location rather than policed by review.
4. **Discoverability.** Engineers can grep the whole product, read adjacent services, and reuse existing patterns instead of reinventing them in repo #23 they did not know existed.
5. **Refactoring at scale.** Large-scale codemods and API migrations are mechanical when everything is in one tree; in polyrepo they are multi-quarter negotiation projects.

## Monorepo costs (what you sign up for)

1. **Build tooling becomes mandatory, not optional.** Past a handful of packages you need affected-change detection and caching (Nx, Turborepo, Bazel, Pants) or every PR builds the world. Google and Meta only make this look easy because they built dedicated internal build teams.
2. **CI cost and queue time creep.** Without path filtering and remote caching, the monorepo turns your CI bill into a platform line item and your queue into the new bottleneck.
3. **Access control is coarse.** Git gives you per-repo permissions; hiding a service's source from another team inside one repo requires tooling most orgs do not have. Regulated or M&A-sensitive code often forces carve-outs anyway.
4. **Clone and history weight.** Large binaries, vendored assets, and years of history make fresh clones slow; you end up managing partial clone, sparse checkout, or LFS as infrastructure.
5. **The commons can rot.** Without CODEOWNERS and per-directory ownership discipline, "everyone can touch everything" decays into "nobody owns anything," and the strongest team ends up maintaining the root config files for everyone.

## Polyrepo advantages (what keeps teams there)

1. **Clear ownership boundaries.** The repo list roughly maps to team ownership; access, CI health, and release responsibility are unambiguous.
2. **Independent versioning and release cadence.** Teams ship on their own schedule without coordinating a shared main branch or shared lockstep releases.
3. **Cheap per-repo CI.** Small repos mean fast pipelines with boring, standard tooling — no build-graph engineering required.
4. **Blast-radius isolation.** A broken main in one repo does not block every other team's merges, which matters when merge-equals-deploy.
5. **Natural security boundary.** Contractors, acquisitions, and regulated components slot in as separate repos without inventing visibility tooling.

## Decision framework and the hybrid middle

1. **Rate coupling, not taste.** If a typical change touches 2+ repos, the coupling tax is real and a monorepo (or merged subtree) pays for itself. If changes are overwhelmingly single-service, polyrepo friction is mostly theoretical.
2. **Count the coordination overhead.** Track how many cross-repo change "programs" ran last quarter and how long each took. This is the number the monorepo pitch has to beat.
3. **Prefer per-domain monorepos at mid scale.** A common 2025-2026 pattern is several monorepos aligned to bounded contexts (e.g. one for the product, one for platform tooling) rather than one org-wide repo or twenty-five tiny ones. You get atomic changes inside the domain without org-wide build infrastructure.
4. **Migration is incremental or it fails.** Move one service pair that changes together first, prove the CI setup, then absorb neighbors. Big-bang "monorepo week" migrations lose unfinished branches and goodwill.
5. **Write the decision down as an ADR.** Record the coupling evidence, the chosen topology, and the review trigger (e.g. re-evaluate when cross-repo changes exceed N% of changes). This kills the quarterly re-litigation.

## Related
- `monorepo-build-tools-2026.md` (tooling side: Nx/Turborepo/Bazel)
- `monorepo-affected-builds-2026.md`, `monorepo-ci-parallelization.md`
- `adr-architecture-decision-records.md`
- `codeowners-advanced-2026.md`
