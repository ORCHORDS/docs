# IEEE 1012-2016 Software Verification and Validation

## Purpose

IEEE 1012-2016 ("Standard for System, Software, and Hardware Verification and Validation") defines verification and validation (V&V) processes, tasks, and minimum activities proportionate to the integrity level of the system or software under development. It defines four integrity levels (I through IV, from low to high consequence) and specifies minimum V&V tasks for each activity across the life cycle, from concept through retirement. This article summarizes project-neutral engineering use of the standard; it does not claim conformance, certification, or assurance outcomes for any specific program.

## Scope

IEEE 1012 applies whenever V&V independence and rigor must be demonstrated: safety-critical, mission-critical, security-critical, and regulated software, as well as commercial software where contractual or regulatory obligations require objective evidence that requirements are met. It governs the V&V process and its tasks; it does not replace the development process (IEEE 12207), the review process (IEEE 1028), or the testing standard (IEEE 29119). It defines what V&V evidence must exist, not how to write code or design architectures.

Within the engineering knowledge base, this article covers:

- the four integrity levels and how to assign one to a system or component;
- the minimum V&V tasks mapped to life-cycle activities (concept, requirements, design, implementation, test, installation, operation, maintenance, retirement);
- critical software V&V tasks and hazard analysis integration;
- the evidence trail that makes V&V auditable; and
- limitations: IEEE 1012 is an assurance process standard, not a defect-prediction model or a substitute for development quality.

## Workflow

A program adopting IEEE 1012 should begin by establishing integrity level and V&V scope before defining tasks. The generic workflow is:

1. Determine the integrity level for the system and its software using consequence-of-failure analysis across safety, security, mission, and financial dimensions.
2. Establish the V&V program: objectives, organization, independence requirements, and the V&V plan documenting tasks selected from the standard's minimum set for the assigned integrity level.
3. Execute V&V tasks per life-cycle activity:
   - concept: evaluate the concept document, operational scenarios, and integrity-level assignment;
   - requirements: verify requirements for the IEEE 830 properties, validate them against user needs, and trace them;
   - design: evaluate architecture and detailed design against requirements, perform interface analysis, and verify design decisions and assumptions;
   - implementation: perform code reviews, static analysis, unit verification, and component verification;
   - test: verify test plans, procedures, and environments; validate system behavior against requirements; and confirm anomaly resolution;
   - installation and operation: verify installation procedures, validate operational readiness, and evaluate change impact.
4. Maintain hazard and security analysis integration where integrity level I or II applies.
5. Generate V&V reports, anomaly reports, and task reports as evidence of completion.
6. Confirm all exit criteria for the assigned integrity level are met before progression.

## Controls and evidence

The standard requires that V&V be objective, and the degree of independence scales with integrity level. Evidence expected at each activity includes:

- the V&V plan, recording the integrity level, task selection rationale, independence, and acceptance criteria;
- task reports for each executed task, recording inputs examined, analysis performed, findings, and conclusions;
- anomaly reports for every deviation from requirements, design, or expected behavior, including classification and disposition;
- hazard analysis results, updated as design and implementation reveal new hazards;
- interface control documentation, verified against actual interfaces;
- a traceability matrix linking requirements to design, code, and test evidence;
- a final V&V report summarizing task completion, anomalies, residual risks, and a recommendation regarding acceptance.

Independence is a core control: at higher integrity levels, V&V should be performed by an organization or person independent of development. The standard defines degrees of independence and permits technical, managerial, and financial independence to be considered separately.

## Validation

Validation that the V&V program itself conforms to IEEE 1012 should include:

- confirming the integrity level is documented with a consequence rationale and re-evaluated when mission, environment, or criticality changes;
- auditing task selection against the standard's minimum V&V tasks for the assigned integrity level;
- verifying that anomaly reports are closed or explicitly accepted as risk;
- checking that independence requirements claimed in the V&V plan are reflected in actual staffing and reporting lines;
- confirming V&V reports are objective, that is, they report findings against requirements rather than developer assertions.

## Failure correction

Common failure modes the standard exposes, and the corrective actions each implies:

- Assigning integrity level by habit rather than analysis—the corrective action is to redo the consequence analysis and re-map minimum tasks.
- Performing V&V only at test time—the corrective action is to schedule V&V tasks at every life-cycle activity, particularly concept and requirements.
- Treating anomaly closure as developer discretion—the corrective action is to require independent disposition of anomalies affecting integrity-level-critical functions.
- Losing traceability as change accumulates—the corrective action is to update the traceability matrix under change control, not at release time.
- Claiming independence without organizational separation—the corrective action is to document the actual degree of independence and adjust task selection if independence is weaker than planned.

## Limitations

IEEE 1012 does not guarantee the absence of defects; it structures how V&V evidence is produced and how much is required. It does not prescribe specific testing techniques, static analysis tools, formal methods, or metrics; these are covered by IEEE 29119 and related standards. It does not replace hazard analysis standards such as IEEE 1228 or system safety engineering; it integrates with them. The standard's minimum task sets are floors, not ceilings: high-integrity programs commonly exceed them. Conformance to IEEE 1012 demonstrates that a defined V&V process was followed with appropriate independence; it does not demonstrate that the software is correct, safe, or secure.

## Scope note

This article summarizes project-neutral engineering use of IEEE 1012-2016. It does not claim implementation, conformity, certification, or assurance outcomes for any specific system, software, or organization.

## Canonical sources

- IEEE 1012-2016 — Standard for System, Software, and Hardware Verification and Validation (IEEE Xplore): https://standards.ieee.org/ieee/1012/6463/
- IEEE Standards Association — Verification and Validation landing page: https://standards.ieee.org/project/1012.html