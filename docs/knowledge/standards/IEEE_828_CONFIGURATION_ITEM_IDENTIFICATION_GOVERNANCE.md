# IEEE 828 Configuration Item Identification Governance

## Purpose

Govern the application of IEEE 828 (configuration management in systems and software engineering) to configuration item identification so that every artefact under configuration management has a controlled identity: a naming scheme, owner, and versioning that make change traceable and baselines reconstructable.

## Scope

Applies to every artefact the studio places under configuration management: requirements, designs, code, test artefacts, build scripts, deployment definitions, and documentation. Covers identification (naming, numbering, versioning), baselining, and the configuration management record. Does not cover change control boards (organizational process) or IT service configuration management (ITIL CMDB practice).

## Workflow

1. Define the configuration item (CI) selection criteria: which artefacts are managed as CIs (anything needed to rebuild, re-verify, or audit the system) and which are working artefacts outside control; the criteria are documented, not per-project improvisation.
2. Assign each CI an identifier from a documented scheme: unique, stable across the CI's life, and encoding nothing that will change (no dates or owner names inside identifiers).
3. Version CIs consistently per the scheme: version increments follow the documented semantics (draft, revision, released) and released baselines are immutable.
4. Establish baselines at defined lifecycle points (functional, allocated, product): each baseline records the CI set, their versions, and approval; a baseline without a recorded CI set is not a baseline.
5. Maintain the configuration management record per IEEE 828's plan structure: what is controlled, who administers it, the schedule of CM activities, and the resources assigned.
6. Trace changes to CIs: every change to a baselined CI references the change authority (ticket, request) that authorized it.
7. Audit configuration against baselines periodically: verify the actual CI set matches the recorded baseline and record discrepancies with resolution.

## Controls and evidence

- CI selection criteria document applied per project.
- Naming and versioning scheme documentation with examples.
- Baseline records: CI set, versions, approval, and date per baseline.
- Configuration management plan per IEEE 828's content requirements.
- Change-to-CI trace records and configuration audit results.

## Validation

- Sample 10 baselined CIs and confirm each identifier follows the scheme and each change traces to an authorization.
- Attempt to modify a released baseline artifact and confirm the process prevents silent change (immutable baseline or change-control gate).
- Confirm the most recent configuration audit ran and its discrepancies were resolved.

## Failure correction

- **CI identifier scheme violation found** → correct the identifier, update references, and record the exception and correction in the CM record.
- **Baseline changed without authorization** → restore the baseline content, trace the unauthorized change to its source, and close the control gap.
- **Audit overdue or discrepancies unresolved** → run the audit, resolve discrepancies, and escalate recurring discrepancies to the CM plan review.

## Limitations

- Identification precision costs effort; over-granular CI selection multiplies management overhead without traceability benefit.
- IEEE 828 defines the CM plan and practice; tool enforcement (git, artifact registries) implements it and needs its own configuration.
- Baseline immutability is procedural in many toolchains; verify the enforcement actually holds.

## Scope note

This article is part of the standards leaf. Cross-reference: `ITIL_4_SERVICE_CONFIGURATION_MANAGEMENT_PRACTICE_GOVERNANCE.md` (operations leaf), `IEEE_828_2012_CONFIGURATION_MANAGEMENT_GOVERNANCE.md` (operations leaf), and `SLSA_PROVENANCE_CONSUMER_VERIFICATION.md` (standards leaf).

## Canonical sources

- IEEE 828-2012 — Standard for Configuration Management in Systems and Software Engineering: https://standards.ieee.org/ieee/828/4329/
- ISO 10007:2017 — Quality management — Guidelines for configuration management: https://www.iso.org/standard/61834.html
- MIL-HDBK-61A — Configuration Management Guidance: https://www.dsp.dla.mil/
- ISO/IEC/IEEE 12207:2017 — Systems and software engineering — Software life cycle processes: https://www.iso.org/standard/63712.html
- NIST SP 800-128 — Guide for Security-Focused Configuration Management of Information Systems: https://csrc.nist.gov/publications/detail/sp/800-128/final
