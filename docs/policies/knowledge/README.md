---
title: "Knowledge Management"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# Knowledge Management

Company-wide governance for critical knowledge, authoritative sources, decision records, transfer, discoverability, quality, and content lifecycle.

## Documents

- [Knowledge Management Policy](KNOWLEDGE_MANAGEMENT_POLICY.md)
- [Knowledge Taxonomy Governance](KNOWLEDGE_TAXONOMY.md)
- [Authoritative Source Governance](AUTHORITATIVE_SOURCE_GOVERNANCE.md)
- [Authoritative Source Recertification](AUTHORITATIVE_SOURCE_RECERTIFICATION.md)
- [Knowledge Authority Conflict](KNOWLEDGE_AUTHORITY_CONFLICT.md)
- [Knowledge Ownership](KNOWLEDGE_OWNERSHIP.md)
- [Knowledge Owner Recertification](KNOWLEDGE_OWNER_RECERTIFICATION.md)
- [Critical Knowledge](CRITICAL_KNOWLEDGE.md)
- [Critical Knowledge Recertification](CRITICAL_KNOWLEDGE_RECERTIFICATION.md)
- [Role Knowledge Baseline](ROLE_KNOWLEDGE_BASELINE.md)
- [Knowledge Single-Point-of-Failure Governance](KNOWLEDGE_SINGLE_POINT_FAILURE.md)
- [Decision Records](DECISION_RECORDS.md)
- [Duplicate Knowledge Control](DUPLICATE_CONTENT_CONTROL.md)
- [Knowledge Search and Discoverability](KNOWLEDGE_DISCOVERABILITY.md)
- [Knowledge Access and Classification](KNOWLEDGE_ACCESS_CLASSIFICATION.md)
- [Knowledge Transfer](KNOWLEDGE_TRANSFER.md)
- [Succession Knowledge Transfer](SUCCESSION_KNOWLEDGE_TRANSFER.md)
- [Operational Knowledge Handoff](OPERATIONAL_KNOWLEDGE_HANDOFF.md)
- [Lessons-to-Knowledge Governance](LESSONS_TO_KNOWLEDGE.md)
- [Knowledge Gap Management](KNOWLEDGE_GAP_MANAGEMENT.md)
- [Knowledge Gap Aging](KNOWLEDGE_GAP_AGING.md)
- [Knowledge Usage Feedback](KNOWLEDGE_USAGE_FEEDBACK.md)
- [Knowledge Freshness](KNOWLEDGE_FRESHNESS.md)
- [Knowledge Review Cadence](KNOWLEDGE_REVIEW_CADENCE.md)
- [Knowledge Review Evidence](KNOWLEDGE_REVIEW_EVIDENCE.md)
- [External Knowledge Validation](EXTERNAL_KNOWLEDGE_VALIDATION.md)
- [AI-Generated Knowledge Review](AI_GENERATED_KNOWLEDGE_REVIEW.md)
- [Knowledge Content Lifecycle](CONTENT_LIFECYCLE.md)
- [Knowledge Deprecation Notice](KNOWLEDGE_DEPRECATION_NOTICE.md)
- [Knowledge Archive and Retirement](KNOWLEDGE_ARCHIVE_RETIREMENT.md)
- [Knowledge Exception Aging](KNOWLEDGE_EXCEPTION_AGING.md)
- [Knowledge Management Metrics](KNOWLEDGE_METRICS.md)

## Public knowledge import boundary

Reusable knowledge may be incorporated from other sources only after it has
been converted to project-neutral public documentation. The receiving
repository must not depend on private repository names, private paths,
credentials, internal endpoints, customer data, personal data, deployment
topology, or other source-specific operational context.

Bulk knowledge imports must fail closed unless all of the following are true:

- the source material has passed sensitive-data and public-neutrality scans;
- private/source-specific names and paths have been removed or generalized;
- duplicate and destination-collision checks have been completed;
- relative Markdown links have been rewritten where necessary and validate;
- a manifest accounts for the expected exported files;
- the reconstructed transfer matches its expected cryptographic checksum; and
- the normal documentation-quality and public-neutrality gates pass after
  import.

A prepared migration snapshot of 8,006 Markdown files has passed the
sanitization/public-safety and relative-link gates. Preparation does not equal
publication: those files become part of the public corpus only after the
receiving import and repository checks complete successfully.

Knowledge must remain usable without turning the public repository into a private system inventory.
