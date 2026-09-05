---
title: "AI Provider Outage Response Playbook"
standard: "Google SRE Book (Chapter on Incident Management), NIST SP 800-61 Rev 3"
publisher: "Google / NIST"
category: "response-playbook"
subcategory: "ai-reliability"
canonical_url: "https://sre.google/sre-book/incident-response/"
status: "approved"
classification: "public"
audience: "SRE, AI engineering, customer success"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# AI Provider Outage Response Playbook

## Trigger

An upstream AI provider — model API, embedding service, vector store, speech provider, or fine-tuning endpoint — suffers degraded availability, elevated errors, or unexpected behaviour that affects production traffic. The trigger can come from error rate alerts, latency dashboards, vendor incident notifications, or customer reports.

## Scope

The playbook applies to:

- Calls to managed model APIs (LLM, embedding, vision, speech).
- Calls to managed vector databases and retrieval services.
- Calls to managed fine-tuning, evaluation, and content moderation services.
- Multi-provider failover paths and shadow traffic.

## Inputs

- Status page and incident feed for each vendor in use.
- Internal SLO dashboards showing error rate, latency, and saturation per provider.
- Failover configuration: secondary providers, cached responses, degraded modes.
- Customer-facing SLO and contractual commitments.

## Steps

1. **Confirm the outage scope.** Cross-reference internal telemetry with the vendor's status page. Determine whether the impact is regional, model-specific, or affecting all calls.
2. **Activate degraded mode.** Switch to the secondary provider, the cached response, or a smaller model as configured. Communicate the degraded experience internally and to customer success.
3. **Engage the vendor.** Open a support case with the provider; capture the vendor incident identifier. Track remediation cadence and escalate through the account team if SLAs are at risk.
4. **Protect customer SLOs.** Where the outage threatens contractual SLOs, apply credits per policy and notify customers proactively. Coordinate messaging with customer success and communications.
5. **Run shadow traffic.** If a failover path is exercised, capture the trace for post-incident review; do not silently shift customer load without logging.
6. **Restore primary path.** When the vendor confirms recovery, validate the primary path with shadow traffic or a small percentage rollout before restoring full load.
7. **Hold a review.** Convene a blameless post-incident review within ten business days; update the failover configuration, the vendor scorecard, and the multi-provider strategy as needed.

## Escalation

Escalate when:

- The outage exceeds the contractual SLO and triggers credits or notification obligations.
- All failover paths are exhausted and a manual response is required.
- The outage is correlated with a security incident (credential leak, account compromise).

Notify the SRE lead, the AI engineering owner, and the customer success lead. Engage the legal team if contract terms are triggered.

## Evidence

- Internal telemetry showing error rate and latency before, during, and after the outage.
- Vendor status page snapshots and incident identifiers.
- Failover decisions with timestamps and approvers.
- Customer communications and credit issuance with reference numbers.

## Completion Criteria

The incident closes when:

- The primary path is restored and validated.
- All customer-facing commitments (credits, notifications) are met.
- A post-incident review is filed with corrective actions and owners.
- The failover configuration, vendor scorecard, and multi-provider strategy are updated.

## Exceptions

- **Vendor-side planned maintenance.** Document the maintenance window in advance, communicate to customers, and skip the post-incident review if the maintenance was within published terms.
- **Internal degradation without external impact.** Where failover succeeded within SLO, capture the event as a near-miss and review for improvement without a full incident declaration.

## Related Documents

- Google SRE Book — Managing Incidents
- NIST SP 800-61 Rev 3 (Incident Handling)
- Site Reliability Engineering On-Call Response
- Disaster Recovery Failover Response
- Service Status Incident Communication
