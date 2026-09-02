# IEEE 1012-2016 Independent Verification and Validation Governance

## Purpose

IEEE 1012-2016, "Standard for System, Software, and Hardware Verification and Validation," defines integrity levels (SIL 1 through SIL 4), the V&V activities required at each level, the minimum V&V tasks for new development, for inheritance, for an operation, for a maintenance, for a retirement, and the requirements for an independent V&V (IV&V) capability. This article maps the IEEE 1012 concepts onto an internal V&V program so engineering teams can choose and apply the right integrity level, document the activities, and demonstrate that selected V&V tasks are complete.

## Scope

The standard applies to systems, software, and hardware V&V in any domain where a project carries technical risk or is subject to external assurance. Within this knowledge base, the article covers integrity-level selection, the IV&V organizational and reporting requirements, the relationship between IEEE 1012 and a project quality plan, and the documentation of V&V results. It does not cover sector regulations that adopt the standard with specific extensions; readers must apply their own sector overlays.

## Workflow

1. Identify the V&V subject and classify it against the integrity criteria in IEEE 1012 to select a Software Integrity Level (SIL).
2. Map the selected SIL to the minimum V&V tasks required for the current life-cycle stage (new development, inheritance, operation, maintenance, retirement).
3. Determine whether independence is required. IEEE 1012 distinguishes the agent performing V&V (developer or operator) from an independent agent. Independence means the V&V agent is not the same organization as the developer or operator and reports outside the development chain.
4. Produce a V&V plan describing the selected integrity level, the V&V tasks to be performed, the independence arrangement, the schedule, the deliverables, and the acceptance criteria.
5. Execute V&V activities in parallel with development. Each task yields a defined output: an analysis report, a review record, a test report, an inspection record, or a validation statement.
6. Summarize V&V results in a final V&V report that supports a release decision. The report must state the integrity level, list each task, and identify any unresolved issues.

## Controls and evidence

Effective application of IEEE 1012 produces traceable V&V artifacts. The expected evidence includes the integrity-level selection rationale, the V&V plan, the V&V task outputs (analysis, review, test, inspection, validation), the issue list with severity classifications, and the final V&V report. Each V&V task must show what was examined, what method was used, what was found, and what is recommended. Independence must be demonstrated by reporting lines and by an organizational structure where the V&V authority cannot be overruled on V&V matters by the development team.

## Validation

Validation that the standard is being applied correctly should include confirming the integrity-level selection is documented with explicit criteria, the V&V plan covers all required tasks for the SIL, V&V task outputs are reviewed and traceable to requirements, the independence arrangement is actually independent in organization and authority, and the final V&V report addresses each task. Auditors should be able to follow a single requirement from the specification through its V&V record to the release decision.

## Failure correction

Common failure modes: integrity-level selection is missing or based on convenience rather than criteria (corrective: produce a selection record with explicit rationale and revisit it on scope changes); V&V is folded into development and reports up the same chain (corrective: separate the reporting line and document the independence arrangement); V&V activities are performed late as a gate rather than iteratively (corrective: schedule V&V tasks into each life-cycle stage and track them continuously); V&V findings are not closed before release (corrective: gate the release decision on V&V findings status with an explicit accept-with-risk mechanism).

## Limitations

IEEE 1012 is a process and task standard; it does not define the substantive correctness of a system. Conformance means the V&V program follows the standard's structure and minimum content; it does not certify functional correctness, safety, or fitness for purpose. The standard leaves substantive methods (the exact test technique or analysis approach) to other standards and to the project. Sector overlays may add requirements; this article addresses the common base.

## Scope note

This article summarizes project-neutral engineering use of IEEE 1012-2016. It does not assert any specific project's conformance or claim any independent V&V outcome.

## Canonical sources

- IEEE 1012-2016 — Standard for System, Software, and Hardware Verification and Validation: https://standards.ieee.org/ieee/1012/5809/