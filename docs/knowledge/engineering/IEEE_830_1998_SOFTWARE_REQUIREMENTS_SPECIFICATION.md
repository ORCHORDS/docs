# IEEE 830-1998 Software Requirements Specification

## Purpose

IEEE 830-1998 ("Recommended Practice for Software Requirements Specifications") defines the structure and quality attributes of a software requirements specification (SRS). It identifies five desirable properties—correctness, unambiguity, completeness, consistency, and ranked importance (verifiability, modifiability, traceability, and suitability) for individual requirements—and prescribes a template that distinguishes functional from non-functional requirements, external interfaces, system features, and constraints. This article summarizes project-neutral engineering use of the standard; it does not claim certification or conformance outcomes.

## Scope

IEEE 830 governs the requirements specification document, not the process of eliciting, negotiating, or validating requirements (which IEEE 12207, IEEE 29119, and IEEE 1012 address). It applies to systems whose requirements are recorded in writing and shared between stakeholders—suppliers, acquirers, regulators, and users. The standard does not prescribe how requirements are discovered, how stakeholders are interviewed, how prototypes are used, or how tools are selected. It defines what a good SRS looks like and how to organize one.

Within the engineering knowledge base, this article covers:

- the recommended SRS structure (introduction, overall description, specific requirements, appendices);
- the five core properties and the secondary quality attributes the standard assigns to individual requirement statements;
- the distinction between functional requirements, non-functional requirements, external interface requirements, and design constraints;
- validation that the SRS actually meets the standard's quality attributes; and
- limitations: IEEE 830 is a document-structure practice, not a process model, risk model, or testing methodology.

## Workflow

A team adopting IEEE 830 should treat the SRS as a living, versioned document under configuration control. The generic workflow is:

1. Establish the SRS scope (the software product or release) and identify its stakeholders, including acquirers, users, developers, maintainers, and any regulators.
2. Draft the introduction (purpose, scope, definitions, references, overview) and the overall description (product perspective, functions, user characteristics, constraints, assumptions).
3. Specify each requirement as a numbered, testable statement using the standard's recommended structure: unique identifier, source, priority, description, verification method or acceptance criterion.
4. Distinguish functional requirements (what the software shall do) from non-functional requirements (performance, reliability, usability, security, maintainability, portability) and from external interface requirements (user, hardware, software, communications).
5. Capture design and implementation constraints that limit the developer's freedom without prescribing a design.
6. Review the SRS against the five core properties and the secondary attributes before baseline; reject or rework drafts that fail any property.
7. Place the SRS under configuration management so subsequent change is tracked, reviewed, and traceable.

## Controls and evidence

A compliant SRS produces verifiable, traceable evidence. The standard expects:

- a unique, stable identifier for every requirement;
- a verification method or measurable acceptance criterion for every requirement;
- traceability from each requirement to its source, to design elements, to code, and to test cases;
- priority or stability ratings that let stakeholders rank requirements under change pressure;
- clear separation between requirements (what) and design (how), with constraints recorded explicitly;
- an issue list and change history for the SRS itself, since requirements evolve.

The traceability discipline makes the SRS auditable: an auditor can follow a single requirement from its origin through its implementation and verification.

## Validation

Validation under IEEE 830 reviews the document against its stated properties:

- Unambiguity: every requirement uses a single, definite interpretation. Vague words ("fast", "user-friendly", "robust") are replaced with measurable statements or removed.
- Completeness: every significant requirement of every interface, mode, and response is stated, including error and failure handling.
- Consistency: no two requirements conflict. If conflict is unavoidable, priority or precedence resolves it explicitly.
- Verifiability: every requirement has a stated or derivable method (test, inspection, analysis, demonstration) to confirm satisfaction.
- Traceability: every requirement can be traced forward to design, code, and test, and backward to origin.

A practical validation technique is to perform an inspection (per IEEE 1028) of the SRS, using a checklist derived from these properties.

## Failure correction

Common failure modes the standard exposes, and the corrective actions each implies:

- Requirements that combine design and intent ("the system shall use a microservices architecture to scale")—the corrective action is to split into a requirement (what capability) and a constraint (what must be honored).
- Untestable requirements ("the system shall be fast")—the corrective action is to add a measurable acceptance criterion or remove the requirement.
- Implicit assumptions about environment, user, or hardware—the corrective action is to make assumptions explicit and review them with stakeholders.
- Missing error-handling requirements—the corrective action is to require explicit specification of error paths before sign-off.
- Untraceable requirements—the corrective action is to enforce traceability matrix maintenance as part of the change-control process.

## Limitations

IEEE 830 does not define how to elicit requirements from stakeholders, how to negotiate priorities, or how to manage requirements risk; those belong to requirements engineering processes and to standards such as IEEE 12207 and IEEE 29119. The standard does not prescribe a database, a tool, or a lifecycle stage for the SRS. It does not cover use-case modeling or user-story formats, nor does it specify how to write requirements for machine-learning components, AI systems, or distributed-ledger systems. Conformance to IEEE 830 demonstrates the document is well-structured; it does not demonstrate that the requirements are the right requirements or that they will deliver value.

## Scope note

This article summarizes project-neutral engineering use of IEEE 830-1998. It does not claim implementation, conformity, or certification outcomes for any specific software system or requirements document.

## Canonical sources

- IEEE 830-1998 — Recommended Practice for Software Requirements Specifications (IEEE Xplore): https://standards.ieee.org/ieee/830/1227/
- IEEE Standards Association — Software Requirements Specifications landing page: https://standards.ieee.org/project/830.html