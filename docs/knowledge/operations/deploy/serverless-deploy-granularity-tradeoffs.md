# serverless-deploy-granularity-tradeoffs

**Issue:** example project's serverless backend grew by copy-paste: 60+ Cloudflare Workers and Lambda functions now exist, several of which are actually one logical API split across a dozen single-route functions with duplicated shared code and duplicated pipelines. Meanwhile a rival team runs one big "lambda monolith" and their whole API goes down whenever one route's deploy is bad. Nobody chose either granularity deliberately; both emerged. This article records how to decide how many deployable functions a serverless system should have, and what each choice costs.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The Granularity Spectrum

1. **One deployable per API (the "monolith function").** A single Worker or Lambda receives all routes and dispatches internally — AWS's own operator guidance discusses this "Lambda monolith" pattern as legitimate, especially for teams consolidating from microservice sprawl.
2. **One deployable per domain/service.** A handful of functions, each owning a bounded slice (auth, billing, content), routing internally within the slice.
3. **One deployable per route/handler.** Every endpoint its own function with its own pipeline — maximum isolation on paper, maximum sprawl in practice.
4. **Granularity is a deploy-time decision, not a runtime one.** At request time a fat Worker dispatching internally is nearly indistinguishable from many thin ones; the differences that matter are deploy blast radius, cold-start profile, permission scoping, and pipeline count — all delivery concerns.

## Coarse-Grained (Few Functions) Tradeoffs

1. **One pipeline, one deploy surface.** A single function means one build, one config, one deploy to reason about; cross-route refactors ship atomically without coordinating N deploys or version-skew protocols.
2. **Wider blast radius.** A bad deploy or a crash loop in any route takes down every route sharing the function — the monolith failure mode. There is no partial outage, only full ones.
3. **Cold-start cost scales with bundle size.** Package size is a documented determinant of cold-start latency; a monolith carrying every route's dependencies initializes slower than a thin handler carrying one route's. For Lambda this shows up as init time; for Workers it shows up as startup CPU and memory pressure on free-tier-constrained plans.
4. **Shared, coarse permissions.** One function means one IAM role / one binding set with the union of all routes' needs — a read-only route effectively holds write access it never uses, which is exactly the over-privilege auditors flag.
5. **Best fit when:** routes are tightly coupled, share most dependencies, change together, and have modest traffic where a full-API blast radius is survivable.

## Fine-Grained (Many Functions) Tradeoffs

1. **Small, well-scoped deploys.** Shipping one route never risks the others; per-route canary and rollback become trivial because the unit of deploy matches the unit of change.
2. **Tight per-function permissions.** Each handler gets exactly the bindings it needs — least privilege enforced by construction, and AWS guidance calls out per-action IAM scoping as the main blast-radius control in fine-grained layouts.
3. **Operational multiplication.** 60 functions means 60 pipelines (or one mega-pipeline with 60 matrix legs), 60 sets of env config, 60 things to monitor, and N×(N-1) version-skew combinations when routes call each other.
4. **The distributed-monolith trap.** If the "many functions" all share one database schema and must deploy in lockstep anyway, you have monolith coupling with microservice overhead — the worst of both; splitting did not contain the blast radius, it only scattered it.
5. **Cold starts can improve or worsen.** Thin handlers start fast individually, but a single user journey touching 6 routes pays 6 cold starts; and duplicated framework code across functions multiplies total memory footprint fleet-wide.

## Sizing Heuristics

1. **Split along change patterns, not URL structure.** Group routes that change together (same owner, same repo path, same review thread) into one deployable; routes that different teams change independently get separate ones. Deploy granularity should mirror coordination boundaries.
2. **Split along risk boundaries.** Anything with distinct compliance, availability class, or traffic shape (e.g., the payment webhook versus the marketing pages API) deserves its own function regardless of coupling.
3. **Split along dependency weight.** Keep heavy native/ML/PDF dependencies isolated in dedicated functions so their cold-start and bundle cost is not imposed on every lightweight route — this is the packaging logic extended to architecture (see `lambda-deploy-package-optimization.md`).
4. **Merge along duplication.** When two functions share more than ~70 percent of their code and config and always deploy together, they are one function wearing two names; merge them.
5. **Prefer "few per domain" as the default.** For most teams the sweet spot is single-digit functions per API area: monolith-grade simplicity inside a domain, blast-radius isolation between domains.

## Pipeline and Dependency Implications

1. **Pipeline count is the hidden cost curve.** Each new deployable adds a workflow, a config surface, a secrets copy, and an on-call runbook entry; before adding function N+1, name the pipeline it will use and who will own it.
2. **Shared code needs a versioning contract.** Extract common logic into a versioned internal package consumed by all functions; ad-hoc copy-paste of helpers across functions is how the same bug gets fixed 12 times — and missed the 13th.
3. **Cross-function calls are cross-deploy calls.** When function A invokes function B, A must tolerate B being one version ahead or behind (expand-contract, tolerant readers); event-driven coupling via queues absorbs this better than synchronous invokes — see `event-schema-compat-deploys.md`.
4. **Shared resources gate independent deploys.** One database migration can force coordinated deploys across every function touching that schema; keep migrations compatible so functions deploy in any order (`database-migration-deploy-strategy.md`).
5. **Re-evaluate at incident time.** The postmortem question "why did the whole API go down / why did fixing it take 12 deploys" is the granularity decision giving you feedback; act on it — merge or split deliberately, not by drift.
