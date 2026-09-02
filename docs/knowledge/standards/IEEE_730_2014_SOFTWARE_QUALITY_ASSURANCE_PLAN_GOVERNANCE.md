# IEEE 730-2014 Software Quality Assurance Plan Governance

## Purpose

Govern the application of IEEE 730-2014 (standard for software quality assurance processes) so that software quality assurance (SQA) operates as an independent, planned process with defined authority, documented SQA plans, and evidence-producing activities — not as informal testing or a developer self-check.

## Scope

Applies to every software project the studio runs with an SQA function, covering SQA planning, process assurance, product assurance, and the SQA plan's required content. Does not cover verification and validation execution (IEEE 1012 governs V&V) or the project's testing practice.

## Workflow

1. Charter SQA with independence: SQA reports outside the development management chain and has defined authority to initiate corrective action and escalate; a dependency that removes independence is a governance failure to record.
2. Produce an SQA plan per project per IEEE 730's content requirements: product scope, SQA processes, standards and procedures to be enforced, reviews and audits, documentation requirements, deviations and waivers handling, and SQA reporting.
3. Assure processes: verify development follows the defined software process (reviews held, artefacts produced, deviations handled); process assurance findings are recorded and tracked regardless of product outcome.
4. Assure products: verify work products conform to their defined standards (documentation, code, test artefacts); product assurance verifies conformance, not functionality — that is V&V's role.
5. Handle deviations and waivers through the plan's defined path: temporary waivers require documentation, expiry, and approval at the level the plan assigns.
6. Report SQA results to management on the plan's cadence: findings, trends, waiver status, and process compliance posture; the reports are the evidence SQA happened.
7. Review the SQA plan at project milestones: scope changes, process changes, or recurring finding patterns update the plan rather than leaving it stale.

## Controls and evidence

- SQA charter with independence and authority provisions.
- SQA plans per project with IEEE 730-required content.
- Process assurance records: activities verified, findings, and dispositions.
- Product assurance records: conformance checks against standards.
- Deviation and waiver register with approvals and expiries.
- SQA management reports on the plan's cadence.

## Validation

- Confirm each active project's SQA plan contains the IEEE 730-required sections.
- Sample five SQA findings and confirm each has disposition and closure evidence.
- Confirm waiver entries carry expiry dates and none expired silently.

## Failure correction

- **SQA independence compromised** → restore the reporting line or document the compensating escalation path; record the decision at governance level.
- **Plan missing required content** → complete the plan section, and review the plan template for the gap.
- **Finding closed without evidence** → reopen, collect evidence, and gate future closures on evidence presence.

## Limitations

- SQA assures process and conformance; product quality outcomes also depend on V&V and engineering practices SQA does not perform.
- Independence is organizational; small organizations implement it via separation of duties rather than separate departments.
- The standard's plan structure predates some modern delivery models; map its requirements onto current lifecycle artefacts deliberately.

## Scope note

This article is part of the standards leaf. Cross-reference: `IEEE_1012_2016_INDEPENDENT_VERIFICATION_GOVERNANCE.md` (engineering leaf), `IEEE_1028_2008_REVIEW_TYPES_SELECTION_GOVERNANCE.md` (engineering leaf), and `ISO_9001_2015_QUALITY_MANAGEMENT_SYSTEM_TEMPLATE_GOVERNANCE.md` (templates leaf).

## Canonical sources

- IEEE 730-2014 — IEEE Standard for Software Quality Assurance Processes: https://standards.ieee.org/ieee/730/4652/
- IEEE 1012-2017 — IEEE Standard for System, Software, and Hardware Verification and Validation: https://standards.ieee.org/ieee/1012/5610/
- IEEE 1028-2008 — IEEE Standard for Software Reviews and Audits: https://standards.ieee.org/ieee/1028/3438/
- ISO/IEC/IEEE 12207:2017 — Software life cycle processes: https://www.iso.org/standard/63712.html
- ISO 9001:2015 — Quality management systems — Requirements: https://www.iso.org/standard/62085.html
