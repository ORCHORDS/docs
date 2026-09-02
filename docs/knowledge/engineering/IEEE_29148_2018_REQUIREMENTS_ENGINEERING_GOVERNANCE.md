# IEEE 29148-2018 Requirements Engineering Governance

## Purpose

IEEE 29148-2018, "International Standard — Systems and Software Engineering — Life Cycle Processes — Requirements Engineering," defines the requirements engineering activities across stakeholder needs, requirements analysis, architectural design, verification, and validation, and specifies the structure and content of stakeholder requirements, system requirements, and software requirements specifications. This article governs how engineering teams plan, perform, and document requirements engineering so that requirements are unambiguous, traceable, and verifiable.

## Scope

The standard applies to requirements engineering for systems and software in any domain. Within this knowledge base, the article covers the construction and content of stakeholder requirements, system requirements, and software requirements specifications, the traceability relationships among them, the verification and validation activities tied to requirements, and the change-control discipline that keeps a requirements baseline usable. It does not cover detailed notation (UML, SysML, formal methods) for expressing requirements; the standard is notation-agnostic.

## Workflow

1. Identify and represent stakeholder needs and the resulting stakeholder requirements in a stakeholder requirements specification (StRS). Each stakeholder requirement should be uniquely identified, expressed in stakeholder language, and traceable to its source (an interview, a regulatory clause, a market analysis).
2. Derive system requirements from the stakeholder requirements and express them in a system requirements specification (SyRS). Each system requirement should be uniquely identified, testable, traceable to one or more stakeholder requirements, and free of implementation detail.
3. Derive software requirements from the system requirements and express them in a software requirements specification (SRS). Each software requirement should be uniquely identified, testable, traceable to one or more system requirements, and complete against the criteria the standard lists.
4. Maintain requirements traceability: each requirement has a forward trace to design, implementation, and verification, and a backward trace to the requirement it satisfies.
5. Define verification (are we building the system right?) and validation (are we building the right system?) activities against the requirements. Each requirement should map to at least one verification method (inspection, analysis, demonstration, test) and to at least one validation activity that confirms the requirement meets a stakeholder need.
6. Apply change control to the requirements baseline. Each change is reviewed for impact on cost, schedule, design, verification, and downstream requirements.

## Controls and evidence

Evidence that IEEE 29148 is being applied includes the existence of the StRS, SyRS, and SRS documents with the structural elements the standard lists, the bidirectional traceability among requirements and downstream artifacts, and the change-control records that show how the baseline evolved. Each requirement should be reviewable in isolation: the identifier, statement, rationale, source, verification method, and trace links are present. Reviews of requirements should check for ambiguity, completeness, verifiability, and consistency.

## Validation

Validation should confirm the structural elements of each specification are present and correct (unique identifiers, correct precedence relationships between specifications, no orphan requirements, no circular references), the traceability matrix is bidirectional and current, the verification methods listed are appropriate to each requirement, and the change-control records show that the baseline has been actively maintained. Spot checks should confirm a sample of requirements can be traced in both directions.

## Failure correction

Common failure modes: stakeholder requirements are conflated with system requirements (corrective: separate the specifications and enforce the precedence rules); requirements are written as implementation directives rather than capabilities (corrective: rephrase in capability form and move implementation choices to design); requirements lack verification methods (corrective: assign a verification method to every requirement and refuse to accept unverifiable requirements); traceability is one-way (corrective: maintain a bidirectional matrix); requirements baseline drifts without change control (corrective: gate promotion of changes through a change-control process and update the matrix with each accepted change).

## Limitations

IEEE 29148 defines requirements engineering process and document structure; it does not prescribe the engineering techniques (use cases, user stories, formal specification) used to elicit or express requirements. The standard does not guarantee that requirements are correct, only that they are expressed, traced, and verifiable. Sector overlays may impose additional requirements (e.g., safety standards requiring additional traceability or specific phrasing); this article addresses the common base.

## Scope note

This article summarizes project-neutral engineering use of IEEE 29148-2018. It does not assert any specific project's conformance or claim any requirements outcome.

## Canonical sources

- IEEE 29148-2018 — Systems and Software Engineering — Life Cycle Processes — Requirements Engineering: https://standards.ieee.org/ieee/29148/7068/