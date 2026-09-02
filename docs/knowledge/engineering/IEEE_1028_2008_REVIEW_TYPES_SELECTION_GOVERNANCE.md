# IEEE 1028-2008 Software Review Types Selection Governance

## Purpose

IEEE 1028-2008, "Standard for Software Reviews and Inspections," defines five review types — management reviews, technical reviews, inspections, walkthroughs, and audits — and specifies the entry, preparation, conduct, exit, and reporting criteria for each. This article governs how an engineering team chooses among the five types and how it executes the chosen review with the discipline the standard requires, so that review records are usable as evidence for assurance activities.

## Scope

The standard applies to the review of software products at any life-cycle stage. Within this knowledge base, the article covers the criteria for selecting each review type, the roles each requires (author, moderator, reader, recorder, reviewer), the minimum entry and exit conditions, the recording obligations, and the use of review results. It does not cover the detailed checklists used for any specific artifact; those must be derived from the project's domain and quality requirements.

## Workflow

1. Decide which review type fits the purpose:
   - Management review: evaluating the project's progress, plans, and process conformance for management decision.
   - Technical review: evaluating a technical artifact for correctness, completeness, and adherence to standards.
   - Inspection: a systematic, metrics-based peer review using defined roles, entry criteria, and a defect taxonomy.
   - Walkthrough: an author-led review to surface defects and to share understanding among the team.
   - Audit: a formal review against an external standard, contract, or regulation by an independent agent.
2. Before the review, confirm the entry criteria: the artifact is complete enough for the chosen review type, materials are distributed, and the participants are qualified.
3. Conduct the review using the role assignments specified in the relevant clause of IEEE 1028 (e.g., moderator and recorder for inspections). Apply the conduct rules (timeboxing, defect classification, anonymity where appropriate).
4. Record the review output using the forms implied by the standard: a log of defects, a list of decisions, and a status recommendation.
5. Confirm the exit criteria (for inspections: defect counts and rework completion; for management reviews: decisions taken; for audits: conformance findings).
6. Feed the review output back into the artifact's revision history and the project's quality records.

## Controls and evidence

Evidence that IEEE 1028 is being followed includes the choice of review type for each artifact, the entry-criterion checklist used to start the review, the role assignments during the review, the recorded defects with classification, and the exit decision. Inspections produce the richest evidence: defect logs, rework records, and rate metrics. Management reviews produce records of decisions and action items. Audits produce findings classified as conformity, observation, minor non-conformity, or major non-conformity.

## Validation

Validation that IEEE 1028 is being applied correctly should include confirming the chosen review type matches the purpose (a technical review is not used to make a management decision; an audit is not used to surface design defects), the entry criteria are checked, the prescribed roles are present, and the exit criteria are met before the artifact moves forward. Inspections specifically should show preparation effort (individual defect logging prior to the meeting), the meeting itself as a defect-clarification step rather than the only step, and rework records.

## Failure correction

Common failure modes: every review is treated as an informal walkthrough (corrective: classify by purpose and apply the matching entry/conduct/exit rules); inspections are run without preparation (corrective: enforce the entry criterion that reviewers log defects individually before the meeting); review outputs are not linked to the artifact's revision (corrective: append the review record to the artifact's history and gate promotion on review status); reviews happen after release as justification rather than before as a check (corrective: schedule reviews into the project plan and gate release on review exit criteria).

## Limitations

IEEE 1028 defines review types and the conduct rules; it does not prescribe domain-specific defect taxonomies, checklists, or quality criteria. The standard does not cover every kind of review: code reviews done within a pull-request workflow can be designed to satisfy a walkthrough or inspection, but the team must document the mapping. The standard does not replace sector-specific review requirements where a regulation demands a different process.

## Scope note

This article summarizes project-neutral engineering use of IEEE 1028-2008. It does not assert any project's conformance or specific review outcomes.

## Canonical sources

- IEEE 1028-2008 — Standard for Software Reviews and Inspections: https://standards.ieee.org/ieee/1028/3713/