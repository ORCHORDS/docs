# IEEE 12207-2017 Lifecycle Process Tailoring Governance

## Purpose

IEEE 12207-2017, "International Standard — Systems and Software Engineering — Software Life Cycle Processes," defines a comprehensive set of software life-cycle processes grouped into agreement, organizational project-enabling, and technical management processes, and offers a tailoring model so a project can adapt the processes to its context. This article governs how engineering teams apply tailoring, what the tailoring decision must address, and how the resulting tailored process is documented so it remains aligned with the standard's intent.

## Scope

The standard applies to software life-cycle processes in any context where the project benefits from a defined process model. Within this knowledge base, the article covers the tailoring conditions (environment, size, criticality, regulatory regime), the obligations that must be preserved when tailoring, the documentation of tailoring decisions, and the relationship between the tailored process and the project's quality plan. It does not cover tailoring of related standards (ISO/IEC 15288 for systems; project readers should consult that standard separately).

## Workflow

1. Identify the project's context for tailoring: project size, complexity, criticality, applicable regulations, organizational maturity, and stakeholder obligations.
2. Decide which processes are required, which are not applicable, and which can be combined or performed by the same party. The standard permits combining processes where the combination does not undermine the purpose of either.
3. For each tailored process, document:
   - the base process from IEEE 12207 being tailored;
   - the tailoring decision (omit, combine, re-sequence, re-assign, scale);
   - the rationale tied to a context factor;
   - the residual obligation preserved (for example, even if acceptance review is merged with validation, both purposes must be addressed).
4. Review the tailoring decision against any external obligation that the project carries (regulations, contracts, sector overlays). External obligations may be non-negotiable even when internal context supports tailoring.
5. Publish the tailored process in the project's life-cycle model documentation and reference it from the project's quality plan.
6. Reassess tailoring on scope change, context change, or external-obligation change.

## Controls and evidence

Tailoring produces a documented decision record (the tailoring rationale and the residual obligations), an updated process model for the project, and references from the project's plans (quality plan, project plan, measurement plan) to the tailored model. Where the standard names specific required artifacts (audit records, review records, verification records), the tailoring decision must state how each artifact is still produced. Evidence of proper tailoring is the alignment of the project's process to the standard's purposes despite the simplifications chosen.

## Validation

Validation should confirm the tailoring decision is documented, the rationale is tied to context factors rather than convenience, the residual obligations from the unmodified clauses are still met, and external obligations are not silently dropped. Auditors should be able to read the tailoring decision and trace any standard requirement to either (a) a tailored process that still satisfies it or (b) an external-obligation waiver. Tailoring decisions should be reviewed on each major scope change.

## Failure correction

Common failure modes: tailoring is invoked to remove a process the team finds inconvenient (corrective: require rationale tied to context, not preference); tailoring is undocumented (corrective: maintain the decision record alongside the quality plan); tailoring is applied without checking external obligations (corrective: include a sector-obligation review in the tailoring decision); tailoring decisions are not revisited on scope change (corrective: schedule a tailoring reassessment on scope change and on context change).

## Limitations

IEEE 12207 provides the process framework and the tailoring model; it does not prescribe the tools or techniques used to perform each process. The standard does not guarantee product quality; it ensures the processes are defined and applied. Tailoring is permitted but bounded: a project that removes an entire process without compensating controls must justify that removal against the standard's purposes.

## Scope note

This article summarizes project-neutral engineering use of IEEE 12207-2017. It does not assert any specific project's tailoring decisions or claim any conformance outcome.

## Canonical sources

- IEEE 12207-2017 — Systems and Software Engineering — Software Life Cycle Processes: https://standards.ieee.org/ieee/12207/6701/
- ISO/IEC/IEEE 12207:2017 — Systems and Software Engineering — Software Life Cycle Processes (joint ISO/IEC/IEEE edition): https://www.iso.org/standard/63712.html