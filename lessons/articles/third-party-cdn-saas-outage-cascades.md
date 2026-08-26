# third-party-cdn-saas-outage-cascades

**Issue:** A single shared-infrastructure provider fails, and the blast radius instantly covers thousands of organizations that never bought anything from it. Cloudflare's November 18, 2025 outage (a Bot Management configuration bug) and its December 5, 2025 follow-on each took down a large slice of internet-facing sites — roughly a fifth of the web fronts through Cloudflare — and the disrupted services included many with no direct Cloudflare relationship, because their SaaS providers, payment flows, auth providers, or embedded scripts sat behind it. The same topology made Fastly's 2021 outage an estimated $100M+ loss across downstream customers and made CrowdStrike's 2024 defect a global IT event. The engineering failure isn't choosing a CDN — concentration on hyperscalers is rational — it's building as if a systemically critical dependency were infallible: no inventory of indirect dependencies, no degraded mode, no independent health signal, and status pages nobody watches until customers are already reporting the outage to you.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why cascades are structural, not exceptional

1. **Your dependency graph includes your dependencies' dependencies.** Teams track direct integrations (API keys, contracts) but not transitive ones: the widget that loads from a CDN, the SaaS tool that fronts through the same edge network, the status page hosted on the provider that is down. In the 2025 Cloudflare events, organizations discovered their outage was transitive only while writing the postmortem.
2. **Concentration makes provider failures internet events.** When ~20% of web properties share one edge network, a single config bug is a simultaneous, correlated outage at global scale — no amount of per-customer engineering diversifies that risk away. Analyses after November 2025 (Grant Thornton, Penligent) framed it correctly as systemic concentration risk, not one vendor's bad day.
3. **Embedded third-party scripts fail your page even when your origin is fine.** Analytics, chat widgets, A/B tools, and tag-manager payloads served from a failed CDN block rendering or hang interactions for users whose session your own servers never saw — the outage looks like "your site is down" in every support channel you have.
4. **Correlated outages defeat naive redundancy.** Two SaaS providers in the same region, two tools fronted by the same edge network, or a primary and a backup that both depend on the same identity provider all fail together. Redundancy purchased without checking the dependency tree of the redundant path is decorative.

## Know the blast radius before the incident

1. **Inventory indirect dependencies with a page-level audit.** Load every critical user journey in a clean browser profile and list every origin that participates: first-party, SaaS, CDN-fronted assets, scripts. Repeat for internal tools (dashboards, CI, on-call paging) — the November 2025-style event also knocked out the tooling teams needed to respond with.
2. **Classify dependencies by failure behavior, not by vendor tier.** For each: does the page still function if it fails (async/optional), degrade (fallback available), or hard-fail? This classification is the input to every mitigation below, and it changes — re-run it when tags and widgets change, which is constantly.
3. **Map shared-infrastructure overlap.** Explicitly record which providers sit on which edge/cloud/identity backbone, so "we have two vendors" can be checked against "but both fail when that backbone fails." The overlap map is what converts concentration risk from abstract to visible.
4. **Track the health of dependencies independently of your own dashboards.** Your uptime green while the edge is red is the signature of this incident class; watching major-provider status feeds (and third-party reachability monitors) gives you the first hint before customer tickets do.

## Build degraded modes that survive

1. **Make third-party scripts non-blocking and supervised.** Load analytics/widgets asynchronously with timeouts and hard failure: a hung tag must never gate rendering or interaction. Tag managers that can drop any tag at runtime turn a provider outage into a silent analytics gap instead of a front-page outage.
2. **Serve critical assets from origins you control or cache aggressively.** Fonts, core JS, checkout-critical assets: self-host or fall back to origin on edge failure. A static, cacheable core page delivered from anywhere keeps the business alive while the edge recovers.
3. **Design the revenue-critical path to have the fewest third-party hops.** Checkout and login are the paths where an edge/provider outage converts directly into lost money; each third-party hop there is a place to be deliberate — either eliminate it or have a tested fallback (direct API, secondary provider).
4. **Multi-CDN/active-active is a real option — priced honestly.** For properties where minutes of edge outage cost more than the engineering, DNS- or load-balancer-level multi-CDN with automated health failover works (Fastly itself publishes the resilience patterns). For most systems the honest choice is degraded-mode + fast comms, not full multi-CDN; the failure is choosing neither and calling the single provider "reliable."

## Operate the incident you can't fix

1. **Detect via customer-independent signals, communicate fast.** When a hyperscaler drops, your job is detection (external monitors, provider status) and a public acknowledgment within minutes — "we're up; our edge provider is down; tracking their recovery" — because silence during a shared outage reads as your outage and burns trust you can't buy back.
2. **Have the provider-status runbook ready.** Pre-written comms templates, a decision tree for "degrade vs. wait," and a named owner for watching the provider's status page convert a helpless hour into a managed one. The 2025 events were 25 minutes to hours long — enough time for comms to matter enormously.
3. **Afterwards, write your own postmortem of a provider's outage.** Which journeys failed, which dependencies were transitive, what the degraded mode actually did. The provider's root cause is theirs; your exposure analysis is the only part that changes your system.
4. **Feed findings back into vendor risk — including the boring vendors.** Third-party risk assessments that only cover data-security vendors miss the edge network everyone shares. Add "what happens when you are down, and prove it" to vendor reviews, and weight it as heavily as the security questionnaire everyone already ignores.
