# ISO/IEC/IEEE 42010:2011 Architecture Description Governance

## Purpose

ISO/IEC/IEEE 42010:2011 defines requirements for the creation and maintenance of architecture descriptions of systems. The standard identifies stakeholders, concerns, viewpoints, and correspondence rules. Governance ensures that architecture descriptions are produced for systems of appropriate scale, that stakeholders and concerns are identified, and that architecture descriptions support review and decision-making.

## Current context and source status

ISO/IEC/IEEE 42010:2011 was published as a joint ISO/IEC/IEEE standard, replacing IEEE Std 1471-2000. The standard is an architecture framework standard, not a management system standard. It is widely used in safety-critical and infrastructure systems. Verify the current edition before treating any clause identifier as a current requirement.

## Governance workflow and controls

### 1. Identify when an architecture description is required

Produce an architecture description for systems of significant scale, complexity, or regulatory scope. Examples include safety-critical systems, large distributed systems, and systems under regulatory review.

### 2. Identify stakeholders and concerns

Identify stakeholders (users, operators, developers, regulators, maintainers) and their concerns (functional, performance, availability, security, safety, maintainability). Document concerns as the basis for selecting viewpoints.

### 3. Select viewpoints

Select one or more viewpoints that frame the concerns. Examples include functional, information, concurrency, development, deployment, operational viewpoints. Document the rationale for viewpoint selection.

### 4. Establish correspondence rules

Establish correspondence rules between architecture descriptions at different levels and across different viewpoints. For example, a functional element in the functional viewpoint corresponds to a component in the component viewpoint.

### 5. Document the architecture description

Use a consistent architecture framework (for example, TOGAF, DoDAF, MODAF) or a tailored framework. Document each viewpoint and the architecture decisions. Maintain version control.

### 6. Review and approve

Conduct architecture reviews with the identified stakeholders. Document review findings. Approve the architecture description before major development phases.

### 7. Maintain the description

Update the architecture description when significant decisions are made. Maintain traceability between architecture decisions and downstream artifacts.

## Validation and evidence

- Architecture description per system.
- Stakeholder and concern register.
- Viewpoint selection rationale.
- Correspondence rules.
- Architecture review records.
- Change log for architecture decisions.

## Failure correction

Common defects include architecture descriptions that omit stakeholders, viewpoints that don't address the concerns, and correspondence rules that are not enforced. Corrective actions include a stakeholder review workshop, a viewpoint coverage matrix, and a correspondence-rule check at architecture review.

## Limitations

- ISO/IEC/IEEE 42010 is a meta-standard; it requires translation to a concrete framework.
- The standard does not prescribe specific viewpoints.
- Architecture descriptions are costly to maintain; balance with risk.
- The standard does not cover non-functional qualities directly; those require additional frameworks.

## Canonical sources

- ISO/IEC/IEEE 42010:2011, Systems and software engineering — Architecture description, first edition.
- IEEE Std 1471-2000 (superseded).
- TOGAF Standard, current edition.

## Scope note

This article belongs to the standards leaf and cross-references the engineering leaf for architecture patterns, the operations leaf for operational architecture, and the security leaf for security architecture viewpoints.
