# IEEE 1016-2009 Software Design Description Governance

## Purpose

IEEE 1016-2009, *Standard for Information Technology — Systems Design — Software Design Descriptions (SDD)*, defines the content and organization of software design descriptions: the design viewpoints and design entities a complete SDD addresses so that a design is communicated with enough structure for review, implementation, and maintenance.

Design practice should apply 1016's viewpoint model so that design documents systematically cover the perspectives stakeholders need (context, composition, logical, dependency, interface, structure, interaction, state dynamics, resource), instead of one diagram and prose.

## Scope

Applies to the studio's software design description practice. Covers SDD viewpoints, design entity content, and design view organization. Does not cover architecture description frameworks (IEEE 42010 governs architecture descriptions).

## Workflow

1. Select SDD viewpoints per the design's stakeholders and concerns: context, composition, logical, dependency, interface, structure, interaction, state dynamics, and resource — record the selection rationale; omitted viewpoints are deliberate decisions, not oversights.
2. Describe design entities with 1016's attribute set: identification, purpose, function, dependencies, interface, processing, and data — each entity's attributes complete enough for its role in the design.
3. Organize the SDD around design views: each view presents selected entities through a viewpoint, addressing identified stakeholder concerns — views without a stated concern are decoration.
4. Keep the SDD's abstraction level consistent: a design description communicates design decisions, not implementation transcription; code-level detail belongs in code and its generated documentation.
5. Record design rationale for consequential decisions: why this decomposition, why this dependency structure — the rationale is what review evaluates and maintenance needs.
6. Maintain SDD currency with the design it describes: design changes update the SDD in the same change; an SDD that lags its design misleads both reviewers and maintainers.
7. Review SDDs at design gates: reviews check viewpoint coverage and concern resolution, not stylistic preference.

## Controls and evidence

- Viewpoint selection record with rationale per SDD.
- Design entity descriptions with the standard's attributes.
- Design views with identified stakeholder concerns.
- Design rationale records for consequential decisions.
- SDD currency checks (last design change → SDD update).
- Design review records with viewpoint coverage outcomes.

## Validation

- Sample one SDD: confirm each included view states the concern it addresses.
- Confirm sampled design entities carry the required attributes.
- Confirm the SDD reflects the last design change (currency check).

## Failure correction

- **View without a stated concern** → state the concern or remove the view.
- **Entity missing required attributes** → complete the description; incomplete entities block design review.
- **SDD stale after design change** → update within the change and add currency checking to the release checklist.

## Limitations

1016 governs the design description artifact; design quality itself is the practice's outcome, not the document's. Viewpoint selection overhead is real — small components need fewer viewpoints; the standard's value scales with design complexity and stakeholder count. IEEE 42010 governs architecture-level descriptions; systems spanning both use each at its level.

## Scope note

This article is part of the engineering leaf. Cross-reference: `IEEE_42010_2011_VIEWPOINT_LIBRARY_GOVERNANCE.md`, `IEEE_29148_2018_REQUIREMENTS_ENGINEERING_GOVERNANCE.md`, and `ISO_IEC_IEEE_12207_2017_SOFTWARE_LIFECYCLE_PROCESSES.md`.

## Canonical sources

- IEEE 1016-2009 — Standard for Information Technology — Systems Design — Software Design Descriptions: https://standards.ieee.org/ieee/1016/3814/
- IEEE 42010 — Architecture description (ISO/IEC/IEEE 42010): https://www.iso.org/obp/ui/#iso:std:iso-iec-ieee:42010:ed-2
- IEEE 29148-2018 — Requirements and concepts (Requirements engineering): https://standards.ieee.org/ieee/29148/6057/
- ISO/IEC/IEEE 12207:2017 — Software life cycle processes: https://www.iso.org/obp/ui/#iso:std:iso-iec-ieee:12207:ed-2
- ISO/IEC/IEEE 15288 — System life cycle processes: https://www.iso.org/obp/ui/#iso:std:iso-iec-ieee:15288
