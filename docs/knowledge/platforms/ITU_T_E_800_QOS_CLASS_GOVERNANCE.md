# ITU-T E.800 Quality of Service Class Governance

## Purpose

Govern the application of ITU-T E.800 quality of service and quality of experience terminology, together with ITU-T Y.1541 network performance classes, so that network performance commitments are stated in standard vocabulary, measured against defined parameters, and mapped to service objectives rather than advertised informally.

## Scope

Applies to every service the studio operates or procures where network performance commitments exist: latency, jitter, packet loss, availability, and their measurement. Covers QoS parameter definitions, Y.1541 class selection, and measurement interpretation. Does not cover SLO engineering practice (covered by SRE guidance) or transport protocol behavior.

## Workflow

1. State performance commitments using ITU-T E.800 vocabulary: quality of service as the collective effect of service performance determining user satisfaction, distinguished from quality of experience as measured user perception.
2. Select a Y.1541 network performance class per service based on its sensitivity: class 0 (real-time, high sensitivity to loss), class 1 (real-time, high packet loss tolerance examples as defined in the recommendation), through classes for transactional, short transactions, bulk transfer, and default traffic.
3. Record the selected class with the four Y.1541 parameters — IPTD (packet transfer delay), IPDV (delay variation), IPLR (packet loss ratio), IPER (error ratio) — and their upper bounds as the engineering target.
4. Measure against the selected class using consistent measurement points; define where in the path the measurement is taken so results are comparable over time.
5. Where a carrier commitment exists, reconcile the carrier's measured performance with internal measurements and record divergences with both parties' measurement points.
6. Review class selection when the service's workload profile changes (new real-time features, changed traffic mix) and re-baseline the targets.
7. Report QoS achievement against the class bounds, not against best-effort averages; average-only reporting hides tail behavior that users experience.

## Controls and evidence

- Service-to-class mapping register with each service's Y.1541 class and the four parameter bounds.
- Measurement configuration record: measurement points, method, sampling, and reporting window.
- QoS achievement reports showing per-parameter compliance against class bounds.
- Carrier reconciliation records with divergence analysis where applicable.

## Validation

- Confirm each performance-committed service has a recorded Y.1541 class and all four parameter bounds.
- Sample one service and confirm its reported measurements come from the documented measurement points.
- Confirm the reporting shows per-parameter tail behavior (e.g., 95th percentile delay), not only averages.

## Failure correction

- **Parameter bound breached persistently** → open a performance investigation: verify the class still matches the workload, then examine path congestion, routing, or carrier performance.
- **Measurement points inconsistent with documentation** → re-establish the measurement configuration and re-baseline the reporting.
- **Class selection no longer matches workload** → reclassify the service, republish the bounds, and notify consumers of the change.

## Limitations

- Y.1541 class bounds are network-layer targets; they do not include application processing time, which dominates in many services.
- Measurement methodology materially affects results; comparisons across organizations are only meaningful with aligned methodology.
- The recommendation defines classes for IP networks; other technologies (e.g., optical transport) use different parameter frameworks.

## Scope note

This article is part of the platforms leaf. Cross-reference: `ITU-T` guidance in the reference leaf, `SRE_RELEASE_COORDINATION_ERROR_BUDGET_GOVERNANCE.md` (operations leaf), and `monitoring/network-latency-monitoring.md` (operations leaf).

## Canonical sources

- ITU-T Recommendation E.800 — Definitions of terms related to quality of service: https://www.itu.int/rec/T-REC-E.800
- ITU-T Recommendation Y.1541 — Internet protocol aspects: IP network transfer parameters ... network performance objectives for IP-based services: https://www.itu.int/rec/T-REC-Y.1541
- ITU-T Recommendation Y.1564 — Ethernet service activation test methodology: https://www.itu.int/rec/T-REC-Y.1564
- IETF RFC 3393 — IP Packet Delay Variation Metric for IP Performance Metrics (IPPM): https://datatracker.ietf.org/doc/html/rfc3393
- IETF RFC 7680 — A One-Way Loss Metric for IP Performance Metrics (IPPM): https://datatracker.ietf.org/doc/html/rfc7680
