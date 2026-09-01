---
title: "Network Ingress Filtering with BCP 38"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-01"
review-cycle: "90 days"
next-review: "2026-11-30"
---

# Network Ingress Filtering with BCP 38

## Purpose

Network ingress filtering rejects packets whose source addresses are not legitimately reachable from the interface on which they arrive. RFC 2827, published as BCP 38, documents this control as a defense against denial-of-service attacks that use forged IP source addresses.

This guidance turns that principle into an operational control. It does not prescribe a vendor configuration or claim that filtering alone prevents denial of service.

## Control objective

At every appropriate network boundary, permit source addresses that are valid for the attached network and reject source addresses that should not originate there. Apply the same principle to customer, tenant, branch, access, and externally connected interfaces when the routing design provides enough information to make a safe decision.

Filtering close to the source provides the strongest containment because spoofed traffic is stopped before it crosses additional networks.

## Policy record

For each enforced boundary, record:

- the interface or logical attachment covered;
- the source prefixes expected from that attachment;
- the authoritative source for those prefixes;
- the validation technique and its failure behavior;
- explicit exceptions and their owners;
- monitoring, alerting, and review intervals; and
- the evidence retained after a change.

Do not infer legitimate source space from a single observed traffic sample. Derive it from controlled addressing, routing, and provisioning records.

## Deployment workflow

1. Inventory network edges and classify each attachment as single-homed, multihomed, transit, peering, tunnel, or shared infrastructure.
2. Identify where source-address validity can be determined without rejecting legitimate asymmetric traffic.
3. Generate candidate filters from authoritative prefix data.
4. Review aggregate and more-specific routes, failover paths, tunnels, and address translation.
5. Test in an observation or logging mode when the platform supports it.
6. Deploy progressively, beginning with boundaries whose valid source space is unambiguous.
7. Monitor rejects, routing changes, and customer-impact indicators.
8. Reconcile the deployed policy with its source data after every material topology or allocation change.

## Multihoming and asymmetric paths

Strict reverse-path assumptions can be unsafe when legitimate return routes differ from arrival paths. RFC 3704 provides additional guidance for multihomed networks, including feasible-path and loose reverse-path approaches. Select a method based on the actual routing design rather than enabling a strict check indiscriminately.

A documented exception is preferable to a silent global bypass. Exceptions should be narrow, time-bounded where possible, monitored, and reviewed after routing changes.

## Change and failure controls

Treat source-prefix data as production configuration. Validate generated rules before deployment, preserve a known-good version, and define rollback criteria. A stale allowlist can cause an outage; an overly broad allowlist can leave spoofing paths open.

When the policy source is unavailable, use a documented failure mode. Do not silently replace a precise policy with an unrestricted permit. Alert on synchronization failures and retain the last successfully validated policy only when that behavior has been approved.

## Verification evidence

Useful evidence includes:

- the approved boundary and prefix inventory;
- generated-policy diffs and reviewer approval;
- controlled tests using valid and invalid source addresses;
- counters for accepted and rejected traffic;
- sampled reject logs with sensitive payload data excluded;
- exception records and expiration reviews; and
- confirmation that routing or allocation changes triggered reconciliation.

Testing must be authorized and scoped. Do not generate disruptive traffic or attempt spoofing tests across networks that have not approved the activity.

## Failure modes

Common failures include deploying static rules that drift from address allocations, applying strict reverse-path checks to asymmetric routing, overlooking IPv6, filtering only at a distant perimeter, permitting all traffic when automation fails, and retaining exceptions without ownership.

## Sources

- [RFC 2827: Network Ingress Filtering: Defeating Denial of Service Attacks which employ IP Source Address Spoofing](https://www.rfc-editor.org/rfc/rfc2827)
- [RFC Editor information for RFC 2827 and BCP 38](https://www.rfc-editor.org/info/rfc2827)
- [RFC 3704: Ingress Filtering for Multihomed Networks](https://www.rfc-editor.org/rfc/rfc3704)
