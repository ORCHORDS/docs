---
title: "Business Case Evidence Trace"
owner: "Customer Success Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Business Case Evidence Trace

## Purpose

Establish an accountable, evidence-based approach to traceability between customer-success business cases — for expansion, retention, adoption investment, or remediation — and the source data, owners, assumptions, and outcomes that justify them. The objective is to ensure that every significant commercial or service decision taken by customer success can be defended by an auditable chain of evidence, and that the lessons of past decisions flow forward into future cases.

## Scope

This policy applies to any formal business case authored, sponsored, or co-authored by the customer-success function. It covers cases for expansion, contraction, renewal terms, service-tier change, investment in adoption, escalation-driven commitments, and hand-off or transition commitments. It does not apply to ordinary operational notes, internal status updates, or informal pre-decision discussion artefacts, which remain governed by routine communication standards.

## Requirements

- A business case MUST identify the customer outcome it supports, the decision it asks for, the accountable owner, the approval path, and the date by which the decision is needed.
- A business case MUST be traceable to the underlying evidence: success-plan baseline, value-realisation evidence, health-score snapshot, renewal-risk view, expansion-readiness assessment, or equivalent artefact. The link MUST be a durable reference (system identifier plus version), not a free-text description that can drift.
- Assumptions used in a business case MUST be enumerated. Each assumption MUST identify the source, the confidence level, the sensitivity (how the conclusion changes if the assumption is wrong), and the date the assumption was last tested.
- A business case MUST distinguish observed evidence from inferred conclusion. Inferences MUST be supported by reasoning that a second reviewer can follow; reasoning chains that rely on unstated premises MUST be expanded or removed.
- Quantitative claims in a business case MUST reference the underlying data set, the calculation method, the as-of date, and any caveats (for example, small sample size, imputed values, missing data). Reports MUST NOT present unverified numbers as authoritative.
- A business case MUST record the alternatives considered, the trade-offs, and the reason the recommended option was preferred. Alternatives that were considered and rejected MUST be retained, not discarded, so that the decision can be revisited in light of new evidence.
- A business case MUST be reviewed and re-baselined at a documented cadence. Reviews MUST compare the predicted outcome against the observed outcome, record the variance, and either confirm the case or trigger a correction.
- The owner of a business case MUST be the person accountable for the case's outcome, not the person who wrote it by default. Where ownership transfers, the transfer MUST be recorded and acknowledged by the receiving party.
- A business case MUST include an explicit sunset or review trigger. Cases without a sunset MUST be flagged in the next governance review and either renewed with new evidence or closed.
- A business case MUST be classified for sensitivity. Cases that touch confidential customer information, pricing, security posture, or competitive strategy MUST be handled with the access controls that classification requires, regardless of the channel through which the case is shared.
- A business case MUST NOT contain personal medical information, identity-document data, financial account numbers, or any other data class that is not directly necessary to the decision. Redaction MUST be applied before a case is shared beyond the named approvers.
- A business case MUST be stored in a system of record. Storage MUST preserve the case, the evidence links, the approval chain, and any later revisions for at least the longest applicable retention period.
- A business case whose evidence is later found to be materially incorrect MUST be corrected, and downstream decisions taken in reliance on it MUST be reviewed. Corrections and follow-up actions MUST be logged.

## Workflow

1. The case author drafts the business case from a documented evidence base, enumerating assumptions, alternatives, and the recommended decision.
2. A peer reviewer verifies the evidence links, the calculations, and the assumptions. The reviewer MUST be independent of the author and SHOULD be independent of the case's outcome.
3. The case owner signs as accountable; the approver signs as decision-maker. Both signatures are captured with a timestamp and a stated role.
4. The case is stored in the system of record with durable evidence links. Sensitive content is reclassified before circulation beyond the named approvers.
5. At the documented review date, the case is reopened, the predicted outcome is compared with observed evidence, and the variance is recorded. The case is either renewed, modified, or closed.

## Canonical sources

- ISO/IEC 27001:2022, Information security management — Requirements: https://www.iso.org/standard/27001
- ISO 9001:2015, Quality management systems — Requirements: https://www.iso.org/standard/62085.html
- NIST SP 800-53 Rev. 5, Security and Privacy Controls for Information Systems and Organizations: https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- PMBOK Guide (Project Management Institute, public summary): https://www.pmi.org/pmbok-guide-standards
- ISO 21505:2017, Project, programme and portfolio management — Context, concepts and definitions: https://www.iso.org/standard/63546.html
- OECD, Good governance for critical infrastructure resilience: https://www.oecd.org/governance/risk-management/good-governance-for-critical-infrastructure-resilience/
- Customer Success Network, Business case standards (public guidance): https://www.customersuccessnetwork.com/
- ISO/IEC 27002:2022, Information security, cybersecurity and privacy protection — Information security controls: https://www.iso.org/standard/75652.html