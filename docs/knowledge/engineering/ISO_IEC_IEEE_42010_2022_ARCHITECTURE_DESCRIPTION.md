# ISO/IEC/IEEE 42010 Architecture Description

## Purpose

ISO/IEC/IEEE 42010:2022 ("Systems and software engineering — Architecture description") is the international standard for architecture description. It defines the concepts of stakeholder, concern, stakeholder role, architecture viewpoint, architecture view, model kind, architecture description, and correspondence, and it specifies the minimum information an architecture description must contain to be considered conformant. It replaced IEEE 1471-2000 and gives engineering teams a rigorous, tool-neutral vocabulary for what an architecture document is and what it must express. This article summarizes project-neutral engineering use of the standard; it does not claim conformance or certification outcomes.

## Scope

ISO/IEC/IEEE 42010 governs architecture description: the artifacts that express an architecture. It applies to any system—software-intensive, hardware, organizational, or mixed—where stakeholders have concerns that architecture must address. It deliberately does not prescribe architecture processes (see ISO/IEC/IEEE 15288 and IEEE 12207), architecture evaluation methods (see ATAM or architecture reviews per IEEE 1028), notations (UML, SysML, C4, and AADL are all usable), or architecture styles and patterns.

Within the engineering knowledge base, this article covers:

- the core concept set and their relationships;
- the minimum contents of a conformant architecture description;
- identifying stakeholders and concerns, and establishing viewpoints;
- architecture viewpoints, views, and model kinds in practice;
- correspondence rules for maintaining consistency across views; and
- limitations: the standard governs description, not the architecture itself or its quality.

## Workflow

A team adopting ISO/IEC/IEEE 42010 should structure architecture work around stakeholders, concerns, and viewpoints. The generic workflow is:

1. Identify stakeholders and their concerns. Typical stakeholder roles include acquirer, user, maintainer, developer, security engineer, operations, regulator, and support. Concerns include functional behavior, performance, security, evolvability, resource consumption, deployment, integration, and regulatory constraints.
2. Establish an architecture description framework: the set of viewpoints the project will use, each defined by its stakeholder classes, concerns addressed, model kinds employed, and conventions.
3. For each viewpoint, produce architecture views consisting of one or more architecture models of the permitted model kinds.
4. Record the system of interest, its environment, and its mission or context, and any partitioning into subsystems or architecture entities.
5. Declare and maintain correspondences: recorded relationships between elements of different views, such as a component in a logical view corresponding to a deployment unit in a physical view.
6. Verify that each identified stakeholder concern is addressed by at least one view, and record how.
7. Version the architecture description under configuration control and re-validate it when stakeholder concerns or the system context change.

## Controls and evidence

A conformant architecture description produces the following evidence:

- identification of the system of interest and stakeholders with their concerns;
- a viewpoint register naming each viewpoint used, its purpose, the concerns it frames, its model kinds, and its source (established library, project-defined, or standard);
- the views themselves, each stated to conform to a named viewpoint;
- correspondence rules and recorded correspondence instances between views, enabling consistency checking;
- a rationale record for significant architectural decisions, including rejected alternatives;
- traceability from stakeholder concerns to views that address them;
- configuration-managed versioning of the description, with change history.

These artifacts make architecture review (per IEEE 1028) objective: reviewers evaluate whether concerns are addressed and correspondences hold, rather than debating diagrams in the abstract.

## Validation

Validation that an architecture description conforms to ISO/IEC/IEEE 42010 should include:

- confirming every stakeholder role identified has concerns recorded, and every concern has an owner;
- confirming each view is declared against a named viewpoint whose model kinds the view actually uses;
- checking that correspondences between views are declared and verified, not merely implied by naming similarity;
- confirming each concern is addressed by at least one view and that the coverage is explicit;
- reviewing model kinds for appropriateness: a viewpoint for runtime performance should use a model kind that expresses timing and resource behavior, not only static structure;
- verifying the description's identification of the system context and environment matches the operational reality of the deployed system.

## Failure correction

Common failure modes the standard exposes, and the corrective actions each implies:

- Producing one omnibus diagram intended for all stakeholders—the corrective action is to define separate viewpoints per concern class and produce views accordingly.
- Views that drift into inconsistency, such as logical components with no physical counterpart—the corrective action is to declare and verify correspondences.
- Undocumented stakeholders whose concerns surface late—the corrective action is to re-run stakeholder identification at each architecture revision.
- Viewpoints defined only by a tool template rather than by concerns and model kinds—the corrective action is to record viewpoint purpose, concerns, and model kinds explicitly.
- Architecture rationale lost as teams change—the corrective action is to capture decision records with alternatives and consequences under version control.

## Limitations

ISO/IEC/IEEE 42010 governs the description of architecture, not the architecture itself, and not architecture quality. A fully conformant description can still describe a poor architecture. The standard does not evaluate fitness, performance, or security; those require evaluation methods beyond its scope. It does not prescribe a documentation format, notation, or tool, so conformant descriptions vary widely in appearance. It does not replace design patterns catalogs, architecture evaluation methods, or the process standards that govern when architecture work occurs. The 2022 edition consolidated terminology but does not add normative requirements for architecture evaluation or for machine-readable architecture knowledge.

## Scope note

This article summarizes project-neutral engineering use of ISO/IEC/IEEE 42010. It does not claim implementation, conformity, or certification outcomes for any specific system, architecture description, or organization.

## Canonical sources

- ISO/IEC/IEEE 42010:2022 — Architecture description (ISO catalog): https://www.iso.org/standard/74393.html
- ISO/IEC/IEEE 42010:2011 — prior edition (IEEE Xplore): https://standards.ieee.org/ieee/42010/5974/