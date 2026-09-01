# IEEE 1028-2008 Software Reviews and Inspections

## Purpose

IEEE 1028-2008 ("Standard for Software Reviews and Inspections") defines five review types—management reviews, technical reviews, inspections, walk-throughs, and audits—and prescribes the entry, exit, and general criteria each must satisfy. It is the primary authority for software-review governance in regulated and safety-critical environments and is referenced by dependent standards such as IEEE 1012 (verification and validation), IEEE 12207 (life cycle processes), and ISO/IEC/IEEE 42010 (architecture description). This article summarizes project-neutral engineering use of the standard; it does not claim conformance, certification, or audit outcomes for any specific project.

## Scope

The standard applies whenever a software product or service is being reviewed for fitness, correctness, conformance, or progress. It does not prescribe the underlying development process (that is IEEE 12207's role), nor does it specify how to gather requirements (IEEE 830), how to test (IEEE 29119), or how to design (IEEE 1016). It governs the review activity itself: who attends, what entry criteria must hold before the review begins, what the review must produce, and what exit criteria must hold before work continues.

Within the engineering knowledge base, this article covers:

- the five review types defined by IEEE 1028 and their distinct entry/exit criteria;
- the minimum roles required for each type (author, reviewer, leader, recorder, and—when applicable—moderator or manager);
- the evidence and reporting obligations that make a review auditable;
- failure modes that cause reviews to lose authority or produce unverifiable results; and
- limitations: IEEE 1028 governs review conduct and is not a process model, defect catalog, or quality-attribute standard.

## Workflow

A team adopting IEEE 1028 should align each planned review activity with one of the five defined types and record that mapping in the project plan. The generic workflow is:

1. Identify the work product under review and classify it (requirements, design, code, test plan, process, configuration item).
2. Select the appropriate review type from the standard's taxonomy based on the review's objective.
3. Document entry criteria before scheduling the meeting: completeness of the work product, availability of referenced materials, distribution of the review package to participants in advance, and confirmation of required roles.
4. Hold the review meeting using the standard's prescribed structure for the chosen type.
5. Capture issues, decisions, action items, and dispositions in a written report that names participants, version of the work product reviewed, and conclusions against entry and exit criteria.
6. Verify exit criteria before allowing the work product to advance in the life cycle.

For inspections, the standard mandates additional rigor: a trained moderator (distinct from the review leader), individual preparation by reviewers before the meeting, a logging recorder, and a documented inspection exit decision of accept, reject, rework, or rework-and-reinspect.

## Controls and evidence

Reviews conducted under IEEE 1028 produce auditable artifacts that demonstrate process discipline. Required evidence includes:

- a review plan that names the review type, scope, criteria, participants, and schedule;
- a review package consisting of the work product, the issue list or checklist used, and any supporting references;
- a review report recording the date, the version of the work product examined, attendees and roles, issues raised with severity, action items with owners and due dates, and the formal disposition against exit criteria;
- a sign-off record that records acceptance, rejection, rework, or follow-up actions;
- traceability from each issue raised to its resolution or accepted risk.

This evidence supports downstream audits (the fifth review type defined by the standard) by giving independent reviewers concrete material to examine against contractual, regulatory, or process requirements.

## Validation

Validation that the standard is being followed should include:

- spot-checks that every scheduled review has a matching entry-criteria checklist signed before the meeting begins;
- review of review reports to confirm that exit criteria were evaluated, not assumed, and that a disposition was recorded;
- periodic independent audits under the standard's audit type to confirm that prior reviews produced the evidence they claimed;
- comparison of the role assignments against the standard's minimum-role requirements for the chosen review type.

## Failure correction

Common failure modes the standard exposes, and the corrective actions each implies:

- holding "reviews" with no entry criteria, no advance distribution, and no written report—the corrective action is to refuse to schedule the next review until the missing artifacts exist;
- treating walk-throughs as inspections—the corrective action is to record the review type explicitly and apply the matching minimum-role and disposition rules;
- letting inspectors skip individual preparation—the corrective action is moderator enforcement of preparation logs before the inspection meeting;
- allowing work products to advance without an exit-criteria check—the corrective action is to gate the next life-cycle phase on the disposition record.

## Limitations

IEEE 1028 does not define how to perform technical analysis, code review, static analysis, or testing; it governs only the review process. It does not prescribe tools, tooling integration, or automation. It is silent on the depth of defect analysis or the methodology of defect classification. It is not a substitute for IEEE 1012 verification and validation, IEEE 12207 process definition, or ISO/IEC/IEEE 42010 architecture description. Conformance to IEEE 1028 demonstrates that reviews were conducted according to a defined process; it does not demonstrate that the underlying software is correct, secure, or fit for purpose.

## Scope note

This article summarizes project-neutral engineering use of IEEE 1028-2008. It does not claim implementation, conformity, certification, or audit outcomes for any specific software system or organization.

## Canonical sources

- IEEE 1028-2008 — Standard for Software Reviews and Inspections (IEEE Xplore): https://standards.ieee.org/ieee/1028/3811/
- IEEE Standards Association — Software Reviews and Inspections landing page: https://standards.ieee.org/project/1028.html