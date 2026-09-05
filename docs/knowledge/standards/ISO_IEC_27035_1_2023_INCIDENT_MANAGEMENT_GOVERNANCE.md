# ISO/IEC 27035-1:2023 Incident Management Governance

## Purpose

ISO/IEC 27035-1:2023 (Principles and process) defines principles for information security incident management. Governance ensures that ORCHORDS plans, detects, reports, assesses, responds to, learns from, and improves incident handling in line with the standard, and that the related parts 27035-2 and 27035-3 are aligned with part 1.

## Current context and source status

ISO/IEC 27035-1:2023 supersedes the 2016 edition. Part 2 (Guidelines to plan and prepare for incident response) and part 3 (Guidelines for ICT incident response operations) follow the same structure. Verify the current edition before relying on a specific clause.

## Governance workflow and controls

### 1. Plan and prepare

- Establish an information security incident management policy and obtain management approval.
- Define roles, responsibilities, and authority for the incident response team.
- Establish a documented scheme for categorizing and prioritizing incidents.
- Provide training, awareness, and exercises for the incident response team.

### 2. Detection and reporting

- Detect events through monitoring and notification channels.
- Report events to the incident response team with enough context for triage.
- Record every event with timestamp, reporter, and source.

### 3. Assessment and decision

- Assess the event to determine whether it is an incident and classify its severity.
- Decide on the response posture: contain, eradicate, recover, or escalate.
- Engage stakeholders and external parties according to the documented escalation matrix.

### 4. Response

- Contain the incident to limit impact; record containment actions.
- Eradicate the root cause and validate with re-scan or re-test.
- Recover affected systems and verify they meet documented security baselines before re-introduction to service.

### 5. Lessons learned

- Conduct a post-incident review with root cause, contributing factors, and improvement actions.
- Feed lessons back into the plan and prepare phase; update playbooks and policy.

## Validation and evidence

- Incident management policy with current approval.
- Categorization and prioritization scheme.
- Event and incident records with timestamps and decisions.
- Post-incident review records and improvement backlog.

## Failure correction

Common defects include missing policy approval, ad hoc categorization, and skipped post-incident reviews. Corrective actions include policy attestation review, categorization completeness check, and post-incident review coverage report.

## Companion documents

- ISO_IEC_27001_2022_VERSION_TRANSITION_GOVERNANCE.md
- NIST_SP_800_61_INCIDENT_HANDLING_GOVERNANCE.md
- ISO_IEC_27005_2022_RISK_MANAGEMENT_GOVERNANCE.md
