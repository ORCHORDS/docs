# IEEE 828-2012 Configuration Management Governance

## Purpose

IEEE 828-2012, "Standard for Configuration Management in Systems and Software Engineering," defines the configuration management (CM) process and its activities (planning, identification, change control, status accounting, auditing). The standard is applicable to any project where configuration items (CIs) are managed across the system or software life cycle. This article governs the application of IEEE 828 so configuration management operates as a controlled discipline rather than as an ad-hoc tracking activity.

## Scope

The standard applies to configuration management in systems and software engineering. Within this knowledge base, the article covers the CM process activities, the relationship between CM and engineering processes, the selection of configuration items, the change-control process, and the documentation of CM records. It does not cover a specific CM tool; the standard is tool-agnostic.

## Workflow

1. Plan CM: define the CM scope, the CM policy, the CM organization, the tools, the schedule, the responsibilities, and the interfaces with other processes.
3. Identify the configuration items: select the items that warrant CM control (code, documents, models, tests, infrastructure, data). Each CI should have a unique identifier, a version, an owner, and a status.
3. Apply change control: each change to a CI is requested, analyzed for impact, approved, implemented, verified, and released under the change-control process.
4. Maintain status accounting: each CI has a current status (in development, in test, released, retired), a history of changes, and the associated records.
5. Audit the CM process and the CIs at planned intervals: confirm the baseline matches the documentation, confirm the change-control process was followed, and identify discrepancies.
6. Manage baselines: a baseline is a formally approved set of CIs at a point in time. Baselines are the reference for change control.

## Controls and evidence

CM evidence includes the CM plan, the CI list, the baselines, the change records (request, analysis, approval, implementation, verification, release), the status accounting records, and the audit results. Each change should be traceable from the request through the verification to the released baseline.

## Validation

Validation should confirm the CM plan is current, the CI list is complete, change control is followed for each change, status accounting reflects the current state, and audits are performed at the planned cadence. Discrepancies from audits should be tracked to closure.

## Failure correction

Common failure modes: CM is treated as a separate activity from engineering (correct: integrate CM into engineering with the change-control workflow); change control is bypassed for "minor" changes (correct: enforce change control for all changes, with explicit exceptions where warranted); status accounting is not maintained (correct: maintain status accounting as part of normal CM operation); audits are skipped or ceremonial (correct: schedule audits with concrete objectives and follow up on findings).

## Limitations

IEEE 828 defines the CM process; it does not prescribe a specific CM tool. The standard does not address the substantive engineering changes themselves; those are governed by the project's engineering practices. The standard does not guarantee project outcomes; it ensures the configuration baseline is maintained.

## Scope note

This article summarizes project-neutral operations use of IEEE 828-2012. It does not assert any specific project's CM conformance or claim any certification outcome.

## Canonical sources

- IEEE 828-2012 — Standard for Configuration Management in Systems and Software Engineering: https://standards.ieee.org/ieee/828/5264/