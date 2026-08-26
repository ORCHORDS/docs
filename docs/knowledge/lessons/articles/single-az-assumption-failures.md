# single-az-assumption-failures

**Issue:** Teams believe they are multi-AZ because their dashboard says instances run in two availability zones, then an AZ impairment takes them fully down and the postmortem finds the load-balanced, redundant front tier was sitting on hidden single-AZ dependencies: stateful services pinned to one zone, sticky sessions binding users to a zone that no longer exists, an EBS-backed volume that cannot move, a database whose "multi-AZ" standby failed to promote, or a dependency (internal or third-party) that quietly lived in the impaired zone. The October 20, 2025 AWS us-east-1 event sharpened this lesson at region scale — practitioners reported multi-AZ autoscaling groups that "did not stand up" to the failure, and the followup consensus (Censinet, Akamai, INE analyses) was blunt: redundancy you assumed is not redundancy you have, and a provider's postmortem is not your postmortem. Single-AZ assumption failure is not an architecture mistake so much as a verification mistake: the design says multi-AZ, but no one ever forced a zone to fail and watched what happened.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Where the hidden single points live

1. **State is the default single-AZ resident.** Databases, caches, message brokers, and anything with a disk tend to get deployed once, in one zone, and then survive every architecture review because "it's just the cache." When that zone degrades, the stateless tiers in other zones fail right behind it — multi-AZ compute with single-AZ state is a single-AZ system with extra steps.
2. **Sticky sessions silently re-introduce zone affinity.** Session affinity on the load balancer means each user is bound to a zone; a zone impairment ejects that user cohort entirely even though "half the fleet" is healthy. The same applies to zone-affine features: zone-local caches, zone-pinned queues, in-memory state that assumes the instance persists.
3. **Standby configurations fail at promotion time.** Multi-AZ databases are marketed as automatic-failover, but promotion depends on health detection, DNS/endpoint switchover, and the standby being genuinely current — each of which can silently break (lagging replication, frozen status checks) between the annual drills that never happen.
4. **Third-party and platform dependencies have zones too.** A SaaS auth provider, a payment gateway, or an internal shared service pinned to the impaired zone takes you down with it no matter how many zones your own stack spans. Your blast radius is the union of every dependency's blast radius.
5. **AZs are not equals during partial impairments.** Impairments are rarely clean outages; they are degraded networks, throttled EBS, or elevated error rates that health checks pass. Redundancy logic that triggers only on hard failure sits idle while users experience an outage the monitoring insists isn't happening.

## The verification gap

1. **Untested failover is fiction.** Every major 2025 postmortem commentary converged on this: failover paths must be exercised, not assumed. A failover that has never been rehearsed has unknown failure modes (stale config, DNS lag, cold caches, missing permissions) that only surface during the real event — stacked on top of the original failure.
2. **Health checks that don't check dependencies pass vacuously.** Instances in healthy zones report green while their calls to the zone-local dependency time out. If the health endpoint doesn't transitively verify the things the instance needs, the LB keeps routing traffic into a dead end.
3. **Capacity math assumes the surviving zone can absorb 100%.** Multi-AZ deployments sized at ~50% per zone handle a clean zone loss; but reconnect storms, retry amplification, and degraded-half traffic during partial impairments push the survivor past saturation. Failover capacity is a separate budget from steady-state capacity.
4. **The provider's postmortem cannot substitute for yours.** Knowing AWS's root cause does not tell you which of *your* dependencies failed, in what order, or why your failover didn't engage — and it commits you to nothing. Teams that only read the provider's writeup repeat their own failure the next time.

## Making zone-failure real before it happens

1. **Run scheduled AZ-exclusion exercises.** In staging and periodically in prod: cordon a zone (remove it from LB target groups or block its subnet), force database failover, and watch what actually breaks. The delta between what you expected and what happened is your real architecture documentation.
2. **Audit stateful services for zone residency annually.** A standing inventory of "every thing with a disk or a session and which zone it lives in" turns the question from "are we multi-AZ?" (meaningless, answered by the compute tier) into "what still lives in exactly one zone?" (answerable, actionable).
3. **Prefer zone-agnostic state or replicated state.** Managed multi-AZ datastores, replicated caches, or stateless session tokens (JWT) remove the class of failure instead of mitigating it. Where state must be zone-local, document it as an accepted single point with an owner and a failover plan.
4. **Instrument per-zone.** Dashboards and alerts sliced by availability zone make partial impairments visible as one zone's error rate diverging from its peers — the earliest signal of an event that aggregate metrics smooth over for minutes.
5. **Rehearse the degraded mode, not just the failed mode.** Practice operating at reduced capacity with elevated latency: shed load, serve cached/stale content, disable non-critical features. Systems that can degrade gracefully turn zone failures into brownouts; systems that cannot turn brownouts into total outages.

## Keep the levels straight

1. **Multi-AZ answers AZ failure; nothing else.** The October 2025 outage was a region-scale event (DNS/DynamoDB in us-east-1) where multi-AZ provided zero protection, and multi-region failover carried the day for the few who had genuinely built and tested it. Conflating the two levels produces systems that are redundantly wrong.
2. **Multi-region is a cost/consequence decision, not a default.** For most systems the honest options are: accept region risk explicitly (documented, with recovery-time expectations), or invest in tested multi-region for the small set of services whose downtime objective demands it. The failure mode is drifting into believing you have the second while paying for the first.
3. **Match dependency tiers to failure tiers.** A multi-region front end backed by a single-region database is single-region. The weakest tier in the stack defines the resilience of the whole — spend verification effort where the weakest tier is, not where the diagrams look impressive.
