# IEEE 12207-2017 Software Life Cycle Processes

## Purpose

ISO/IEC/IEEE 12207:2017 ("Systems and software engineering — Software life cycle processes") is the umbrella process standard for software engineering. It defines a comprehensive set of processes spanning the full life cycle—from business or mission analysis through retirement—organized into agreement, organizational project-enabling, technical management, and technical processes. It is the parent standard to which IEEE 15288 (system life cycle processes), IEEE 12207's own process outcomes, and most sector-specific software standards trace. This article summarizes project-neutral engineering use of the standard; it does not claim conformance or certification outcomes.

## Scope

IEEE 12207 defines what processes exist and what outcomes each must achieve. It deliberately does not prescribe how to perform them, in what order, or with which methodology (waterfall, incremental, agile, or DevOps are all compatible). It governs process definition and tailoring, not document templates, not tooling, and not the technical content of design or code.

Within the engineering knowledge base, this article covers:

- the four process groups and representative processes in each;
- the concept of process outcomes as the unit of conformance;
- tailoring: how to justify omissions and modifications for a specific project;
- the evidence needed to demonstrate a process was performed; and
- limitations: IEEE 12207 is a process framework, not a methodology, quality model, or assurance standard.

## Workflow

An organization adopting IEEE 12207 typically establishes an organizational process architecture, then tailors it per project. The generic workflow is:

1. Adopt the standard's process taxonomy as the vocabulary for the organization's process asset library.
2. For each process, define the outcomes the standard requires and map them to the organization's existing procedures, artifacts, and tools.
3. Tailor per project: document which processes apply, which are modified, which are omitted, and why. Record the tailoring rationale for later audit.
4. Execute the applicable processes across the life cycle:
   - agreement processes: acquisition and supply, including solicitation, proposal, contract, and acceptance;
   - organizational project-enabling processes: life cycle model management, infrastructure management, portfolio management, human resource management, quality management, and knowledge management;
   - technical management processes: project planning, project assessment and control, decision management, risk management, configuration management, information management, measurement, and quality assurance;
   - technical processes: business or mission analysis, stakeholder needs and requirements definition, system requirements definition, architecture definition, design definition, system analysis, implementation, integration, verification, transition, validation, operation, maintenance, and disposal.
5. Generate process outcomes as evidence: each executed process must produce the artifacts and results the standard names for that process.
6. Review tailoring and process performance periodically, adjusting the process asset library as lessons accumulate.

## Controls and evidence

Conformance to IEEE 12207 is demonstrated by process outcomes, not by ritual. Controls and expected evidence include:

- a documented life cycle model, showing which processes are applied and how they interact across the project's phases;
- a tailoring record listing omissions, modifications, and their justifications;
- per-process outcome records: for example, risk management produces a risk register with identified, analyzed, treated, and monitored risks; configuration management produces baselines, change records, and release records;
- quality assurance records confirming planned processes are being followed and nonconformities are dispositioned;
- measurement records for the measurement process, showing defined measures, collection, and analysis;
- information management records ensuring information is retrievable, protected, and retained for its required lifetime.

Because outcomes—not document titles—are the unit of conformance, an agile project may satisfy a process through different artifacts than a plan-driven project, provided the outcomes are demonstrably achieved.

## Validation

Validation that a process architecture conforms to IEEE 12207 should include:

- mapping each organizational procedure to the standard's process and its required outcomes, identifying gaps;
- auditing completed projects for evidence that each claimed process produced its outcomes;
- reviewing tailoring decisions for validity: omissions must be justified by project characteristics, not convenience;
- confirming interfaces between processes, such as requirements flowing to architecture, verification, and configuration management, actually function;
- periodically re-assessing the process asset library against standard revisions.

## Failure correction

Common failure modes the standard exposes, and the corrective actions each implies:

- Adopting the process names without producing the outcomes—the corrective action is to audit for outcomes, not artifacts named identically to the standard.
- Skipping tailoring and applying the full process set indiscriminately—the corrective action is to record a tailoring decision for every project.
- Treating risk management or configuration management as optional—the corrective action is to check which outcomes are missing and either implement them or justify their absence in tailoring.
- Losing process interfaces, so requirements do not flow to verification—the corrective action is to strengthen traceability and integration reviews between technical processes.
- Allowing the process asset library to drift from the standard—the corrective action is scheduled review against the current standard edition.

## Limitations

IEEE 12207 is deliberately methodology-neutral. It does not define how to run an agile iteration, how to design software, how to test, how to review, or how to write requirements; those are covered by companion standards including IEEE 29119 (testing), IEEE 1028 (reviews), and IEEE 830 (requirements). It is not a quality model—ISO/IEC 25010 fills that role—and it is not an assurance or V&V standard—IEEE 1012 fills that role. It does not prescribe security controls (NIST SP 800-53 or ISO/IEC 27001 apply there), nor accessibility (W3C WAI applies there). Declaring conformance to IEEE 12207 demonstrates that a defined set of processes with defined outcomes exists; it does not demonstrate that the resulting software is correct, secure, usable, or fit for purpose.

## Scope note

This article summarizes project-neutral engineering use of ISO/IEC/IEEE 12207:2017. It does not claim implementation, conformity, or certification outcomes for any specific organization, project, or software system.

## Canonical sources

- ISO/IEC/IEEE 12207:2017 — Systems and software engineering — Software life cycle processes (IEEE Xplore): https://standards.ieee.org/ieee/12207/6471/
- ISO — ISO/IEC/IEEE 12207:2017 catalog entry: https://www.iso.org/standard/63712.html