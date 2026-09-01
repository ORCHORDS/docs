---
title: "Technology Vendor Selection"
owner: "Strategy Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Technology Vendor Selection

## Purpose

Establish the strategic criteria for selecting technology vendors so that the choice reflects long-term value, ecosystem fit, exit cost, and security posture rather than initial price or short-term convenience. Technology vendor selection decisions are notoriously prone to under-estimating the cost of lock-in and over-estimating the durability of vendor capability; this policy counteracts those distortions.

## Scope

This policy applies to the selection of technology vendors for capabilities that materially affect the strategy, operations, or risk profile of the organisation. It covers total cost of ownership, ecosystem fit, exit cost, security posture, and approval routing. It supplements procurement policy and is read alongside [Partnership vs Build Analysis](PARTNERSHIP_VS_BUILD_ANALYSIS.md) and [Strategic Vendor Dependency](STRATEGIC_VENDOR_DEPENDENCY.md).

## Requirements

- A technology vendor selection MUST begin with a documented statement of the capability required, the strategic context, and the constraints (regulatory, security, integration) that any candidate vendor must satisfy.
- Each candidate vendor MUST be evaluated against a common criteria set: total cost of ownership, ecosystem fit, integration cost, exit cost, security posture, vendor durability, commercial terms, and alignment with the organisation's strategic posture.
- Total cost of ownership MUST be modelled over a horizon appropriate to the asset and SHOULD include acquisition, integration, ongoing operation, governance, and exit; the model SHOULD use the organisation's standard discount rate.
- Ecosystem fit MUST include the vendor's compatibility with adjacent tools, the strength of its partner ecosystem, and the maturity of its community or standards alignment.
- Exit cost MUST be quantified; it SHOULD include data portability, skill retraining, contract termination, and stranded investment.
- Security posture MUST be assessed against the organisation's security baseline; vendors that do not meet baseline controls SHOULD NOT be approved regardless of functional advantage.
- Selection proposals that would create a strategic dependency MUST be reviewed by the strategy committee; routine selections within delegated authority may be approved at the appropriate level.
- The proposal SHOULD include a sensitivity analysis on the two most consequential assumptions; the analysis SHOULD demonstrate how the recommendation changes.

## Workflow

1. The originating sponsor prepares a capability brief and a candidate vendor set; the brief states the strategic context and the binding constraints.
2. The sponsor evaluates each candidate against the common criteria; finance validates the cost model; security validates the security posture assessment.
3. The sponsor prepares a recommendation that records the criteria scores, the dissent considered, the sensitivity analysis, and the conditions under which the recommendation would change.
4. The recommendation is reviewed by the appropriate authority; selections that create strategic dependency are routed to the strategy committee.
5. The decision is recorded with rationale; on approval, the sponsor executes the selection and reports progress at the agreed cadence.
6. At each review, the originating owner retests the decision against current evidence and reports any change in vendor posture.

## Controls

- Criteria discipline: scoring MUST use the common criteria set; ad hoc criteria introduced for a specific vendor are prohibited.
- Security gate: failure to meet the security baseline MUST result in disqualification regardless of other scores; the gate is binding.
- Exit readiness: a documented exit playbook SHOULD exist within ninety days of selection; absence of an exit playbook is an escalation event.

## Vendor posture over time

The vendor that was the right choice at selection will not necessarily be the right choice throughout the relationship. The committee SHOULD establish a cadence at which vendor posture is reviewed against the original selection criteria, including financial stability, product direction, security posture, and commercial behaviour. Drift on any criterion SHOULD be assessed for its impact on the original decision; some drift is tolerable and can be addressed through contractual remediation, while drift that affects the strategic rationale for the selection SHOULD trigger a more substantive response, up to and including the activation of the exit playbook.

Vendor concentration across the portfolio SHOULD also be reviewed at the cadence; even where each selection was defensible on its own terms, the cumulative portfolio of vendor relationships may have produced a concentration that the individual decisions did not intend. The committee SHOULD treat concentration as a strategic concern, and SHOULD consider portfolio-level constraints on future selections where concentration has become material.

## Canonical sources

- OECD, "Digital Economy Outlook" (general reference for digital procurement and vendor strategy). https://www.oecd.org/digital/digital-economy-outlook.htm
- ISO/IEC 27001:2022, "Information security management systems." https://www.iso.org/standard/27001
- NIST, "Cybersecurity Supply Chain Risk Management Practices." https://csrc.nist.gov/publications/detail/sp/800-161/rev-2/final
- McKinsey, "Sourcing Technology: A Total-Cost-of-Ownership Playbook." https://www.mckinsey.com/capabilities/mckinsey-digital/how-we-help-clients
