# ISO/IEC 14764:2022 Software Maintenance Governance

## Purpose

ISO/IEC 14764:2022, "Information technology — Software Maintenance," updates the maintenance process described in the ISO/IEC 14764 standard to provide a detailed maintenance reference model, including the process structure for problem and modification analysis, implementation, maintenance review/acceptance, and the migration process. This article governs the application of the maintenance process so that software maintenance activities are performed as controlled changes rather than as ad-hoc edits, and so the maintenance process is auditable.

## Scope

The standard applies to the maintenance of software systems during the operation and maintenance life-cycle stage. Within this knowledge base, the article covers the maintenance process activities (problem identification and analysis, modification implementation, review/acceptance), the migration process, and the relationship to configuration management, change control, and verification. It does not cover the substantive technical work of each maintenance change (which is governed by the project's engineering practices); it covers how each change is processed.

## Workflow

1. Identify the problem or modification request through the agreed intake mechanism (incident system, change request, scheduled modification). Capture it with sufficient context for analysis.
3. Analyze the problem or modification request: determine its scope, impact, urgency, priority, and the affected components.
3. Plan the maintenance activity: identify the configuration items affected, the verification activities required, the schedule, the responsibilities, and the acceptance criteria.
4. Implement the modification under the change-control discipline: design the change, code or update the configuration items, perform peer review and verification as the project's quality plan requires.
5. Perform a maintenance review/acceptance: confirm the change matches its plan, the verification has been completed, and the result is ready for integration.
6. Deploy the change into the operational environment under the deployment discipline, with rollback provisions and post-deployment verification.
7. Update the configuration baseline and the maintenance records (issue list, change log, lessons learned).

## Controls and evidence

Maintenance evidence includes the maintenance plan, the issue list with priorities, the change records (request, analysis, plan, verification results, acceptance decision), the configuration baseline, and the deployment records. Each change should be traceable from the original request through the verification results to the deployment decision. The evidence must support post-incident analysis and trend reporting.

## Validation

Validation should confirm each maintenance change has a complete record (request, analysis, plan, implementation, verification, acceptance), the change was processed under change control, the affected configuration items are identified and updated in the baseline, and the verification covered the change scope. Spot checks should verify that deployed changes match the accepted plans and that rollback provisions were tested where risk warrants.

## Failure correction

Common failure modes: maintenance changes are performed without an analysis step (corrective: require an analysis record before implementation, even for trivial changes); verification is performed ad hoc rather than against a defined method (corrective: assign verification methods to each change type and gate acceptance on completion); change records are not linked to the configuration baseline (corrective: tag each change with the affected configuration items and update the baseline with the deployment); rollback provisions are untested (corrective: include rollback in the maintenance plan and exercise it where the risk warrants).

## Limitations

ISO/IEC 14764 defines the maintenance process; it does not prescribe the technical approach to any specific maintenance activity. The standard assumes a project context that includes change control and configuration management; teams lacking those baselines cannot apply the maintenance process effectively. The standard does not address retire-and-replace decisions; project policy must cover that case.

## Scope note

This article summarizes project-neutral engineering use of ISO/IEC 14764:2022. It does not assert any specific project's maintenance conformance or claim any specific maintenance outcome.

## Canonical sources

- ISO/IEC 14764:2022 — Information technology — Software Maintenance: https://www.iso.org/standard/80681.html