# ITIL 4 Service Continuity Management Practice Governance

## Purpose

Govern the ITIL 4 service continuity management practice so that vital business services can continue or recover when disruption occurs, and so recovery capability is proven by exercise rather than assumed from documentation.

## Scope

The practice applies to every vital business service the studio operates, covering business impact analysis, recovery requirements, continuity strategy, and exercise validation. It does not cover incident-level response (incident management) or security-specific recovery (cyber event recovery).

## Workflow

1. Identify vital business services and the business activities they enable, ranked by the harm caused when they stop.
2. Conduct business impact analysis (BIA) per service: determine maximum tolerable outage, recovery time objective, and recovery point objective, with the business, not IT, signing off the numbers.
3. Map the full dependency chain for each vital service — upstream services, infrastructure, third parties, and people — so recovery plans cover actual dependencies.
4. Select continuity strategies per service (redundancy, failover, manual workaround, acceptance) and record the decision rationale.
5. Document continuity and recovery plans at the level of detail an unfamiliar responder can execute.
6. Exercise each plan on a recurring cadence, rotating scenarios, with success criteria defined before the exercise runs.
7. Feed exercise findings into plan revisions and, where the finding is systemic, into the risk register.

## Controls and evidence

- Vital service register with BIA sign-off, RTO, RPO, and dependency map.
- Continuity strategy decisions with rationale and alternatives considered.
- Exercise calendar and results, including scenario, success criteria, findings, and closure status.
- Plan revision history tied to exercise findings and organizational changes.

## Validation

- Confirm every vital service has a signed BIA no older than the agreed refresh cadence.
- Confirm each continuity plan has been exercised within its cadence and findings are closed or scheduled.
- Sample one dependency map and verify it still reflects the production architecture.

## Failure correction

- **BIA stale or unsigned** → re-run the BIA with the business owner and re-baseline RTO/RPO before the next change cycle.
- **Exercise finding open past its due date** → escalate to the service owner; a second missed date suspends the plan's "proven" status.
- **Dependency map diverges from production** → correct the map, trace the change that missed it, and close the configuration binding gap.

## Limitations

- Continuity is proven by exercise, not by plan existence; an unexercised plan is documentation, not capability.
- Third-party dependencies constrain recovery beyond the studio's control; contract and test them explicitly.
- BIA numbers are business judgments that decay as the business changes; the refresh cadence is the control.

## Scope note

This article is part of the operations leaf and pairs with incident management and cyber event recovery guidance. Cross-reference: `itil-4-incident-and-problem-management-practice.md`, `NIST_SP_800_184_GUIDANCE_FOR_CYBER_EVENT_RECOVERY_GOVERNANCE.md`, and `ISO_20000_1_2018_SERVICE_MANAGEMENT_AUDIT_GOVERNANCE.md`.

## Canonical sources

- AXELOS, *ITIL Foundation, ITIL 4 edition* (2019), service continuity management practice: https://www.axelos.com/certifications/itil-service-management
- ISO 22301:2019 — Security and resilience — Business continuity management systems — Requirements: https://www.iso.org/standard/75106.html
- NIST SP 800-34 Rev 1 — Contingency Planning Guide for Federal Information Systems: https://csrc.nist.gov/publications/detail/sp/800-34/rev-1/final
- NIST SP 800-184 — Guide for Cybersecurity Event Recovery: https://csrc.nist.gov/publications/detail/sp/800-184/final
- ISO 22317:2019 — Security and resilience — Business continuity management systems — Guidelines for business impact analysis: https://www.iso.org/standard/50095.html
