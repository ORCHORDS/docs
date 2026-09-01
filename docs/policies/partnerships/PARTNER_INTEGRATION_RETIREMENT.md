---
title: "Partner Integration Retirement"
owner: "Partnerships Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Partner Integration Retirement

## Purpose

This policy establishes how partner integrations are retired at end of life, including the communications, customer migration, data handling, credential and certificate revocation, deprecation timeline, archival evidence, and the records that demonstrate a clean retirement. It ensures that customers and internal stakeholders are informed in advance, that alternatives are available, that no data or access lingers beyond the agreed sunset, and that the retirement is auditable.

## Scope

This policy applies to every partner integration that is being retired for any reason, including end of product life, partnership termination, strategic substitution, technology obsolescence, regulatory change, or consolidation of redundant integrations. It covers deprecation announcement, customer communications, migration assistance, credential and certificate handling, data return or destruction, archival, and post-retirement verification. It does not cover routine integration maintenance or version upgrades that do not retire the integration.

## Requirements

- The Partnerships Lead MUST publish a deprecation announcement at least six months before retirement for stable integrations, and a shorter notice may be acceptable only with documented business justification and customer impact assessment.
- The deprecation announcement MUST state the retirement date, the affected customers, the migration path or replacement, the support window, and the contact for assistance.
- The organization MUST provide migration assistance proportionate to customer impact, including documentation, tooling, and direct support during the transition window.
- All credentials, certificates, and tokens issued to the partner for the integration MUST be revoked at or before the retirement date, with evidence retained.
- Customer data held by the partner for the integration MUST be returned to the organization or destroyed under the data-processing addendum, with attestation provided.
- The Partnerships Lead MUST verify post-retirement that no production traffic, scheduled jobs, or background processes continue to use the retired integration.
- A retirement record MUST be retained per the records-retention schedule and include announcements, communications, migration evidence, credential revocation, data disposition, and verification.
- The organization SHOULD conduct a post-retirement review to capture lessons and update the integration lifecycle checklist.
- The organization MAY require partner cooperation during the retirement window and document such obligations in the partnership agreement.

## Workflow

1. **Retirement decision.** The Partnerships Lead records the decision to retire, the rationale, and the proposed timeline.
2. **Impact assessment.** A customer impact assessment identifies affected customers, the migration path, and the assistance plan.
3. **Announcement.** The deprecation announcement is published to customers and internal stakeholders.
4. **Migration window.** The migration window is operated; the partner and the organization assist customers moving to the replacement.
5. **Pre-retirement verification.** A pre-retirement verification confirms that production traffic is at or near zero and that migration is largely complete.
6. **Retirement.** On the retirement date, the integration is disabled, credentials are revoked, and the partner is notified.
7. **Data disposition.** Customer data held by the partner is returned or destroyed under the data-processing addendum with attestation.
8. **Post-retirement verification.** A final verification confirms that no traffic, jobs, or background processes continue against the retired integration.
9. **Records.** The retirement record is archived per the records-retention schedule.

## Controls

- A retirement record exists for every retired partner integration, including announcements, migration evidence, credential revocation, and data disposition.
- A pre-retirement and post-retirement verification is performed with evidence retained.
- Customer communications are issued in line with the deprecation timeline.
- Archival evidence is retained for the period required by the records-retention schedule.

## Customer segmentation

Customer impact for retirement decisions varies by segment, deployment model, criticality, and contract terms. The customer impact assessment MUST identify each affected customer, classify the impact by segment, and tailor the assistance plan accordingly. Customers in regulated industries, customers with mission-critical deployments, and customers with contractual commitments that extend beyond the proposed retirement date MUST be reviewed by Legal before the retirement date is announced. The migration plan for high-impact customers MAY include extended support, dedicated engineering assistance, or extended financial terms where appropriate.

## Sunset variants

Retirements take several forms and each is handled with an appropriate combination of communications, migration assistance, and evidence retention. End-of-product retirements retire the underlying product as well as any partner integration that depends on it. Partnership-termination retirements retire the integration even though the underlying product continues, because the partner is no longer authorized to integrate. Substitution retirements retire the integration in favor of a replacement, with the partner and customers expected to migrate to the replacement within the announced window. Regulatory-change retirements retire the integration because a change in law or regulation makes the integration non-compliant. Each variant is identified in the retirement record and the workflow is adjusted accordingly.

## Canonical sources

- IETF, RFC 8594, "The Sunset DNS RR Type" and RFC 8996, "Deprecating TLS 1.0 and TLS 1.1," on graceful retirement of cryptographic artifacts: https://www.rfc-editor.org/rfc/rfc8594.html
- ISO/IEC 20000-1:2018, "Service management," requirements for service retirement and transition: https://www.iso.org/standard/70636.html
- NIST SP 800-57 Part 1 Rev. 5, "Recommendation for Key Management," on cryptographic key retirement and revocation: https://csrc.nist.gov/publications/detail/sp/800-57-part-1/rev-5/final
- Project Management Institute, "A Guide to the Project Management Body of Knowledge (PMBOK Guide)," 7th edition, project closure practices: https://www.pmi.org/pmbok-guide-standards