# micro-frontends-module-federation

**Issue:** When many teams ship features into one frontend, deployment coupling becomes the bottleneck: every release goes through the same build, the same review queue, and one broken module blocks all of them. Micro-frontends split the app into independently developed and independently deployed units, and Module Federation (now a framework-agnostic standard with support beyond webpack — Rspack, Rsbuild, and the Vite plugin ecosystem) is the dominant runtime-integration mechanism, letting a host application load remote modules at runtime with negotiated shared dependencies. But the pattern trades merge conflicts for distributed-systems problems: duplicate framework copies, version-skew crashes between host and remotes, inconsistent design systems, cross-origin failures, and debugging across independently deployed bundles. The 2025-2026 consensus from practitioners is sober — adopt it only at genuine organizational scale, and when you do, invest heavily in contracts, shared-dependency discipline, and a unified design system.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## When to adopt (and when not to)

1. **Organizational scale is the real trigger.** The pattern pays off when multiple autonomous teams ship to the same product on independent cadences. A single team adopting micro-frontends adds coordination overhead with no ownership benefit — this is the most repeated warning in 2025 retrospectives on the pattern.
2. **Monorepo modularization is the cheaper alternative.** If the pain is code ownership rather than deployment independence, a well-bounded monorepo (see package-boundary enforcement) solves it without runtime distribution. Prove that path insufficient before adding federation.
3. **Incremental strangler migrations are the good use case.** Rewriting a legacy app page-by-page, with the new app federated into the old shell (or vice versa), is where federation shows concrete value — teams ship new pages in a new stack behind the existing URL.
4. **Budget for the operational cost up front.** Remote version matrices, cross-team contracts, design-system governance, and harder debugging are permanent costs, not one-time setup; if nobody owns that ongoing work, the architecture will decay.

## Integration approaches

1. **Build-time composition (monorepo packages).** Apps assemble from workspace packages at build time — simplest, best developer experience, but deployment is coupled. This is the default choice and covers most "we want shared code" needs.
2. **Runtime iframe isolation.** Strong isolation (own JS realm, styles, failures contained), but at the cost of routing, scroll, focus, and shared-state complexity. Reserve for truly foreign surfaces (third-party tools, legacy portals).
3. **Runtime module loading with Module Federation.** The host declares remotes and imports their exposed modules at runtime as ordinary components — native-feeling composition (same document, shared router possible) with independent deployment. This is the mainstream micro-frontend mechanism in 2025.
4. **Edge/server composition.** Route-level splitting (each route served by its own app behind an edge router or service-worker composition) keeps teams fully independent and avoids in-page federation entirely — the simplest runtime model when page-level granularity is enough.

## Module Federation mechanics (2025-2026)

1. **Framework-agnostic standard.** Module Federation outgrew webpack: Rspack and Rsbuild support it natively with comparable performance, and @module-federation/vite brings runtime federation to Vite builds. The official documentation at module-federation.io now covers the whole tool family plus runtime and dashboard tooling.
2. **Hosts, remotes, exposes.** A remote declares exposed entry points (e.g., ./Button, ./CheckoutPage); the host lists remote URLs and imports them by name. Exposes are the public API of a remote — treat them like package exports: versioned, reviewed, never broken casually.
3. **Shared dependency negotiation.** The shared config lets host and remotes agree on singleton dependencies (react, react-dom) so one copy loads; strictVersion and fallback control what happens on mismatch. Getting this wrong is the single most common production crash (two Reacts, invalid hook call).
4. **Dynamic remote URLs and manifest-driven loading.** Do not hardcode remote URLs at build time; load a manifest (per-environment JSON) that maps remote names to URLs so ops can roll a remote forward or back without rebuilding the host.
5. **Version contracts and previews.** Pin the contract (exposed module signatures, shared major versions) and give remote teams a way to test against the current host — a preview host build or contract tests in CI — before shipping.

## Shared dependency and design-system discipline

1. **Singleton the framework.** react/react-dom (or the framework core) must be shared as singleton with a shared major version across host and remotes; allow multiple only during deliberate major-version migrations, with an end date.
2. **Share the state library carefully or not at all.** Sharing a store singleton couples teams to one store shape — usually worse than passing props/args across the boundary. Prefer explicit props and events at the federation seam.
3. **Unified design system as a versioned package.** The consistent-UX guidance across 2025 sources is the same: all remotes consume one design-system package (from a monorepo or registry) with tokenized theming, so visual drift is a versioning problem, not a per-team problem.
4. **Theme via CSS custom properties, not JS context.** Design tokens delivered as CSS variables flow across federation boundaries for free (they inherit through the DOM); JS-based theming requires sharing the theme context object, which reintroduces version coupling.
5. **Audit bundle duplication continuously.** Track how many copies of the framework, the design system, and large utilities (charting, date) actually ship; duplication creeps back whenever a remote opts out of sharing.

## Operational concerns and failure handling

1. **Fail isolated.** A remote that fails to load must degrade to a boundary error UI in the host, never a blank page — wrap remote imports in error boundaries keyed by remote name, and alert on remote load failures per remote.
2. **Independent deployability with rollback.** Each remote deploys on its own pipeline to immutable URLs; the manifest points at the current version so rollback is a manifest edit. The host should tolerate remotes being seconds-old or minutes-old relative to each other.
3. **Cross-origin hygiene.** Remotes load from other origins: CORS headers, Subresource Integrity if URLs are pinned, CSP connect-src/script-src allowances, and cookie/auth propagation (token forwarding or a shared session service) must be designed, not discovered.
4. **Testing across the seam.** Contract-test the exposed modules (signature and behavioral smoke tests run in the remote's CI against a host harness), and run an integration environment that composes the current host with current remotes — the composition itself is a system under test.
5. **Tracing and debugging.** Propagate a correlation ID from host through remote calls and console instrumentation; source maps must be uploaded per-remote per-version, or production debugging across federated bundles becomes archaeology. Budget dashboard tooling (the Module Federation dashboard offerings) for visibility into which versions are actually live.
