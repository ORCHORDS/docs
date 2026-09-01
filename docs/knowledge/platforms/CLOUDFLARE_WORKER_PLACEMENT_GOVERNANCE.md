# Cloudflare Worker Placement Governance

## Purpose

Cloudflare Workers normally execute near the incoming request, but applications that make repeated calls to centralized back-end infrastructure can be faster when Worker execution is moved closer to those back ends. Cloudflare supports both Smart Placement and explicit placement hints.

## Placement options

Cloudflare documents mutually exclusive placement choices:

- `mode = "smart"` for automatic placement based on observed latency;
- `region` for infrastructure in a known AWS, GCP, or Azure region;
- `host` for a single-homed layer-4 endpoint; and
- `hostname` for a single-homed layer-7 endpoint.

Workers still run on Cloudflare's network; a cloud-region hint selects a nearby Cloudflare location rather than moving execution into the cloud provider itself.

## Decision pattern

1. Measure whether back-end round trips materially dominate request latency.
2. Use Smart Placement when there are multiple or changing back ends and the optimal location is not known in advance.
3. Use an explicit region when the primary back end is in a known supported cloud region.
4. Use host or hostname placement only for infrastructure that is actually single-homed and suitable for Cloudflare's probes.
5. Compare user-to-Worker latency and Worker-to-back-end latency before and after enabling placement.
6. Re-evaluate the choice when the back-end topology, replication model, or traffic distribution changes.

## Smart Placement

Smart Placement analyzes observed traffic and execution duration to choose whether forwarding a request to another Cloudflare location would reduce total latency. It only affects fetch handlers and requires enough traffic to make a placement decision.

Because Smart Placement is adaptive, performance should be monitored after deployment rather than assumed from configuration alone.

## Explicit placement hints

Region hints are appropriate for single back ends in known cloud regions. Host and hostname hints use probes to estimate proximity to external services.

Cloudflare documents host-based placement as experimental and warns that placement probes are intended for single-homed resources. Anycast, multicast, broadcast, or replicated services can produce misleading placement decisions.

## Governance checks

- Keep placement configuration in version control.
- Record the back-end dependency that justified the placement decision.
- Verify that placement does not conflict with data-localization or regional-processing requirements.
- Test failure and failover paths; low latency to a primary service is not a substitute for resilience.
- Review placement after database migration, region changes, new replicas, or major traffic shifts.
- Do not use performance placement as evidence that data is legally restricted to a jurisdiction; Cloudflare provides separate localization controls for that purpose.

## Sources

- Cloudflare Workers Docs — Placement: https://developers.cloudflare.com/workers/configuration/placement/
- Cloudflare Changelog — New Placement Hints for Workers: https://developers.cloudflare.com/changelog/post/2026-01-22-explicit-placement-hints/
- Cloudflare Workers Wrangler configuration: https://developers.cloudflare.com/workers/wrangler/configuration/

## Scope note

Cloudflare placement behavior and supported region identifiers can change. Validate current platform documentation and measure application latency before treating a placement configuration as optimal.