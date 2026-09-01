# ISO/IEC/IEEE 15289 Lifecycle Documentation Template Governance

## Purpose

Systems and software engineering projects produce many documents across the lifecycle: plans, requirements, architecture descriptions, interface documents, test documentation, review records, and completion reports. ISO/IEC/IEEE 15289 ("Systems and software engineering — Content of life-cycle information items (documentation)") defines the content requirements for each of these information items so that each is complete, traceable, and useful to its intended audience.

This article provides a public, project-neutral method for governing lifecycle documentation templates: deciding which information items to produce, what content each must contain, how items relate to each other, and how to correct failures. It does not claim conformance for any specific project.

## Scope

The scope covers the information items defined by ISO/IEC/IEEE 15289:2019 and the lifecycle processes of ISO/IEC/IEEE 12207:2017 and ISO/IEC/IEEE 15288:2023 to which those items correspond. It covers:

- the document kinds the standard enumerates, including plans (for example, project, configuration management, quality assurance, verification, validation, and maintenance plans), specifications (for example, system requirements, software requirements, interface), descriptions (architecture, design), and reports (test, review, audit, completion, anomaly);
- the required content of each item — its purpose, expected content outline, and the tailoring that applies depending on the information item's purpose and audience;
- the relationships among items, including traceability from requirements through design, implementation, and verification to completion evidence;
- the information item management controls: identification, version, status, approval, distribution, change control, and retention; and
- the distinction between information items and records, since a completed and approved item becomes a record subject to retention.

## Workflow

Governing lifecycle documentation follows the standard's own logic: decide which items are needed, define their content, produce them under control, and retire them deliberately.

1. **Determine the information item set.** Not every project needs every item. Select the items based on the lifecycle model in use, the criticality of the system, contractual and regulatory obligations, and the needs of the acquirer and other stakeholders. Record the rationale for including and excluding each item.
2. **Tailor each item's content.** For each selected item, apply the standard's tailoring guidance: confirm the purpose, choose the content sections that apply, and record the tailoring decisions. Tailoring is documented, not assumed.
3. **Define the information item management controls.** For each item, define its identifier, version scheme, approval authority, distribution list, change-control procedure, and retention rule. These controls are part of the template, not an afterthought.
4. **Produce items at the lifecycle points where their inputs exist.** A requirements specification needs agreed requirements; a verification plan needs an agreed verification strategy. Producing an item before its inputs are stable guarantees rework.
5. **Maintain traceability across items.** Establish and maintain traceability from stakeholder requirements through system and software requirements, architecture, design, implementation, verification, and validation, into completion evidence. Traceability is the property that makes the documentation set auditable.
6. **Control changes.** Approved items change only through the defined change-control procedure, with impact assessment across dependent items. A change to a requirements specification is a change to the design, verification, and traceability baseline as well.
7. **Retire deliberately.** At project close, transfer items to the retention regime defined for them, archive them with their approval evidence, and dispose of them only under the governing retention schedule.

## Controls and evidence

Evidence that lifecycle documentation governance operates correctly includes:

- the documented set of selected information items, with the rationale for inclusion and exclusion;
- the tailored content outline for each item, recording the tailoring decisions made;
- the information item management plan, defining identifiers, versioning, approval, distribution, change control, and retention for each item;
- approval records showing who approved each version of each item and when;
- change-control records linking each change to its impact assessment and approval;
- the traceability matrix linking requirements through design, implementation, verification, and validation evidence; and
- review and audit records demonstrating that items were reviewed at defined milestones.

## Validation

A governed documentation set is validated by:

- completeness checks confirming every selected information item exists at the required lifecycle point;
- content checks confirming each item contains the content sections selected during tailoring;
- traceability checks confirming every requirement traces forward to design and verification evidence and backward to a stakeholder need;
- consistency checks confirming dependent items agree (for example, the interface specification matches the architecture description);
- approval checks confirming each item version carries the required approval; and
- audit or peer review of the documentation set against the standard's content requirements for the item kinds selected.

## Failure correction

Common failure modes in lifecycle documentation governance include:

- **Producing every item regardless of need.** The corrective action is to re-tailor the item set against actual stakeholder and regulatory needs and to record the rationale for the reduced set.
- **Templates without tailoring records.** The corrective action is to document the tailoring decision for each item and to review the record at each milestone.
- **Traceability maintained only at the end.** The corrective action is to update traceability as part of each change, under change control, rather than reconstructing it before an audit.
- **Items approved by the author.** The corrective action is to enforce the defined approval authority and to re-approve affected items.
- **Documents retired without records disposition.** The corrective action is to route retired items through the retention schedule and to retain certificates of disposition.

## Limitations

ISO/IEC/IEEE 15289 specifies the content of information items, not the quality of the engineering they record: a complete document can still describe a poor design. The standard's content requirements are deliberately generic, so each organisation must tailor them; untailored adoption produces documents that satisfy an outline without serving their audience. The standard does not define document format, tooling, or repository design, and it does not replace domain-specific documentation obligations from regulators, acquirers, or sector standards. Finally, the relationship between this standard and the process standards (ISO/IEC/IEEE 12207 and 15288) means that a change in the process model can invalidate the item set; tailoring must be revisited when the lifecycle model changes.

## Canonical sources

- ISO — ISO/IEC/IEEE 15289:2019, Systems and software engineering — Content of life-cycle information items (documentation): https://www.iso.org/standard/79874.html
- ISO — ISO/IEC/IEEE 12207:2017, Systems and software engineering — Software life cycle processes: https://www.iso.org/standard/63712.html

## Scope note

This article describes project-neutral governance of lifecycle documentation templates. It does not claim conformance, certification, or assessment outcomes for any specific project, system, or organisation.
