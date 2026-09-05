---
title: NIST SP 800-53A Rev. 5 Assessment Procedure Governance
owner: ORCHORDS Assurance
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: "NIST Special Publication 800-53A Rev. 5 (January 2025); https://csrc.nist.gov/pubs/sp/800/53/a/5/final"
---

# NIST SP 800-53A Rev. 5 Assessment Procedure Governance

## Scope

This card governs how ORCHORDS selects, executes, and documents security
and privacy control assessments against NIST SP 800-53A Rev. 5. It binds the
assessment-procedure catalogue, the determination statements, and the
assessment object taxonomy (specification, mechanism, activity, individual,
group, product, service, system, organisation, mission/business process,
other) to a single reviewable artefact.

## Why SP 800-53A Rev. 5 matters here

ORCHORDS products are deployed in US federal, state, and critical
infrastructure environments where FedRAMP and agency ATO packages require
assessments traceable to SP 800-53A Rev. 5. Even when a deployment is
commercial, the same assessment methodology gives customers a defensible,
reproducible audit trail. Assessment findings become the language of
residual-risk conversations, so consistency and traceability are not
optional.

## Standard identity

| Field | Value |
| --- | --- |
| Title | Assessing Security and Privacy Controls in Information Systems and Organizations |
| Revision | 5 (January 2025) |
| Originator | NIST Joint Task Force (Interagency Working Group) |
| Companion | SP 800-53 Rev. 5 control catalogue, SP 800-53B control baselines |
| Methodology | Examine, Interview, Test (EIT) — three assessment methods per determination |
| Output | Findings, satisfied-other-than-conformance, not-satisfied |
| Scope | Security and privacy controls across organisation, mission, system levels |
| Companion privacy | SP 800-53A Rev. 5 includes privacy assessment procedures mapped to SP 800-53 Rev. 5 Appendix J |

## Assessment object taxonomy

Each assessment procedure is performed against one or more assessment
objects. Reviewers must record the object type used:

- **Specification** — policies, plans, procedures, requirements.
- **Mechanism** — hardware, software, firmware, system element.
- **Activity** — process, action, operation.
- **Individual / Group** — people with assigned roles.
- **Product / Service / System** — the deliverable being assessed.
- **Organisation / Mission / Business Process** — enterprise context.
- **Other** — explicitly defined when none of the above apply.

## Assessment methods

- **Examine (EX).** Reviewer inspects an assessment object: read a policy,
  a configuration export, or a log sample. EX is the strongest method
  for specification-type objects.
- **Interview (IN).** Reviewer questions an individual or group with
  assigned responsibility. IN is the strongest method for activity-type
  objects and most personnel-related controls.
- **Test (TE).** Reviewer exercises a mechanism under defined conditions
  and observes the outcome. TE is the strongest method for mechanism-type
  objects and any control that depends on runtime behaviour.

A control is only marked satisfied when all required EX, IN, or TE
elements in its assessment procedure produce positive evidence.

## Determination statements

Each assessment procedure lists one or more numbered determination
statements that the assessor must answer with satisfied, satisfied-other-
than-conformance, not-satisfied, or not-applicable. Reviewers must:

1. Record the evidence source for every statement.
2. Map each statement to the system element that produced the evidence.
3. Capture the date of the evidence.
4. Note deviations from the planned assessment scope.

## Findings classification

- **Satisfied** — the assessor obtains sufficient evidence to meet the
  determination statement.
- **Satisfied-other-than-conformance** — the system meets the control
  intent via a compensating mechanism; the assessor documents the
  mechanism, why it is equivalent, and residual risk.
- **Not-satisfied** — evidence is insufficient or contradictory; the
  assessor must record the gap and the risk acceptor.
- **Not-applicable** — the control does not apply; the assessor
  documents the rationale with reference to the system description.

## Assessment lifecycle

1. **Scope.** Map the system boundary and the applicable control
   baseline (Low / Moderate / High for FedRAMP; organisation-defined
   for commercial).
2. **Plan.** Produce an assessment plan that lists every control, the
   assessment object, the methods, the assessor, and the schedule.
3. **Prepare.** Collect up-to-date artefacts (policies, configurations,
   evidence packets) and pre-validate their freshness.
4. **Execute.** Run the assessment; record findings against the
   determination statements.
5. **Report.** Produce a Security Assessment Report (SAR) that maps
   findings to risks and recommended remediations.
6. **Remediate.** Track remediation actions to closure with evidence.
7. **Continuous monitoring.** Re-assess changed controls annually or on
   significant change; sample unaffected controls on a rolling basis.

## Continuous monitoring alignment

SP 800-53A Rev. 5 procedures are reused for continuous monitoring under
NIST SP 800-137. ORCHORDS uses the same evidence packet format across
initial authorisation and continuous monitoring so findings can be
diffed over time.

## Interactions with other standards

- **SP 800-53 Rev. 5.** Assessment procedures reference control
  identifiers exactly as written in the catalogue.
- **SP 800-53B.** Baseline selection determines which procedures are
  required.
- **SP 800-30 Rev. 1.** Findings feed risk determination.
- **SP 800-37 Rev. 2.** Assessment drives the Authorise step in the
  RMF.
- **ISO/IEC 27001 / 27002.** Crosswalks must be recorded where
  ORCHORDS pursues dual certification.

## Deprecations and superseded work

- **SP 800-53A Rev. 4.** Superseded; legacy reports may cite it but new
  assessments must use Rev. 5.
- **Examine-only controls.** Removed where Test is now required; the
  Rev. 5 procedures must be followed verbatim for new work.
- **Manual-only assessment.** Remediated by supporting evidence
  automation but manual sign-off remains required for accountability.

## Reviewer checklist

- [ ] Assessment plan cites SP 800-53A Rev. 5 procedures by identifier.
- [ ] Every determination statement is answered with evidence.
- [ ] Assessment objects are classified using the SP 800-53A taxonomy.
- [ ] Findings use the four-tier classification.
- [ ] SAR maps findings to risks and remediations.
- [ ] Continuous monitoring reuses the assessment plan format.

## Source of truth

SP 800-53A Rev. 5 (January 2025) is the canonical assessment procedure
catalogue. SP 800-53 Rev. 5 is the control catalogue. SP 800-53B is the
baseline selection guide. SP 800-137 is the continuous monitoring
companion.
