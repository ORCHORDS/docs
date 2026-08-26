# multi-region-dns-failover-routing

**Issue:** Multi-region services fail over at the DNS layer only as well as their routing records, health checks, and TTL strategy allow. Teams routinely ship DNS failover that has never been tested and cannot work: TTLs of an hour mean resolvers keep serving a dead region; health checks probe TCP when the failure mode is application-level; and DNS is asked to carry traffic switching that belongs to a load balancer. 2025-2026 guidance (Route 53, Cloudflare, Google Cloud DNS routing policies) is consistent: low-but-realistic TTLs (30-60 seconds for failover records), application-level health checks tuned to the RTO, and DNS as one layer in a failover stack rather than the whole mechanism. This article covers the DNS slice; multi-region-deployment covers architecture and disaster-recovery-failover covers the DR plan.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Choosing a routing policy

1. **Match policy to topology.** Active-active with latency routing (Route 53 latency routing, Cloudflare proximity steering) suits symmetric regions; active-passive wants primary-secondary failover records where the secondary is served only when the primary's health check fails.
2. **Combine steering with failover.** The robust 2026 pattern is latency- or geolocation-steered records over health-checked endpoints: geography picks the region, health checks veto dead ones, so one mechanism does not have to do both jobs.
3. **Weighted routing for canary regions.** Weighted records let a new region take 1-5% of production traffic before it earns full membership; treat region onboarding like a deploy.
4. **Geolocation for data-residency.** Where regulation pins data to a jurisdiction, geolocation routing is a control, not an optimization — verify enforcement at the app layer too, since DNS geolocation is best-effort.
5. **Prefer managed policies over hand-rolled scripts.** Route 53 health-checked failover records, Cloudflare Load Balancing, and Google Cloud DNS health-checked policies exist precisely because scripted address-swap failover at 3 AM fails.

## TTL strategy

1. **30-60 seconds for failover records.** Current guidance converges on tens of seconds for records participating in failover (OneUptime: 30-60s; DigiCert: 60-300s as the upper band); the resolver-cache penalty is the price of a bounded RTO.
2. **TTL is not an SLA.** Recursive resolvers and clients can and do ignore TTLs; DNS failover bounds most traffic, not all. Anything requiring guaranteed sub-minute cutover needs a load-balancer or Anycast layer beneath DNS.
3. **Lower TTLs before planned work.** Drop TTLs ahead of scheduled cutovers and migrations so the changeover window matches the cache horizon; raise them again after stability returns.
4. **Do not set TTL to zero.** Ultra-low TTLs push real resolution load onto authoritative servers at scale; 30 seconds is the practical floor for most setups.

## Health check design

1. **Probe application-level endpoints.** A TCP handshake succeeding on a sick app is the classic false-healthy; checks should hit an endpoint that exercises critical dependencies (DB ping, queue reachable) without being so heavy it flaps.
2. **Tune thresholds to the RTO, not to defaults.** Interval, failure threshold, and (for Route 53) the roughly 18%-of-health-checkers consensus rule together determine detection time; compute detection plus TTL and compare it to the RTO on paper before an outage does the comparison for you.
3. **Use calculated checks for indirect conditions.** Route 53 calculated (computed) checks aggregate child checks and can gate on CloudWatch alarms, letting "region unhealthy" mean a composite of endpoint, alarm, and dependency signals rather than one URL.
4. **Check from outside the region.** Health checkers must not share fate with the target (same VPC, same LB); the vendors' globally distributed checker fleets are the point of using them.
5. **Monitor the checkers themselves.** Alert on health-check state changes — a checker that has been failing for a week means your failover records are one incident away from serving the wrong region, or already are.

## Layering DNS with other failover

1. **DNS chooses the region; the load balancer spreads inside it.** DNS records should point at regional load balancers or Anycast entries, never individual instances; instance-level churn must not be visible to DNS.
2. **Client-side retry complements DNS.** Mobile and SDK clients should retry across regions on failure; well-behaved clients close the gap that TTL-cached resolvers leave open.
3. **State must fail over too.** Steering traffic into a region that lacks the data is a worse outage than the original; DNS failover assumes data-layer replication lag is inside the RPO (see disaster-recovery-failover).
4. **One rehearsed action for evacuation.** Keep a documented, single, rehearsed switch for full region evacuation; multi-step manual DNS surgery during an incident is how DR plans die.

## Testing and operating

1. **Game-day the failover.** Periodically and deliberately fail a region's health check in staging (and, carefully, in production) and measure actual cutover time versus the paper RTO; untested DNS failover is a rumor.
2. **Watch cache behavior, not just records.** Verify from client vantage points (synthetic monitoring from multiple geographies) that traffic actually moves within the TTL window.
3. **Version and review DNS as code.** Routing policies belong in Terraform or the platform's IaC with change review; console-edited DNS records are unreviewed production config.
4. **Alert on post-failover asymmetry.** After failover the surviving region runs hot; autoscaling and capacity alarms need headroom sized for the failover scenario, not just the daily peak.
