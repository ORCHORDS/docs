# ISO/IEC 20000-1 Service Management Requirements

## Purpose

ISO/IEC 20000-1 specifies requirements for establishing, implementing, maintaining, and continually improving a service management system (SMS). The standard is published by ISO/IEC JTC 1/SC 40, the same joint technical committee responsible for ISO/IEC 27001. This article summarizes the requirements as a reference for service-management programs that want to align with a stable, certifiable standard rather than treating service management as an ad hoc collection of procedures.

## Standard structure

ISO/IEC 20000-1:2018 follows the ISO/IEC Annex SL high-level structure:

- Clause 4 — Context of the organization
- Clause 5 — Leadership
- Clause 6 — Planning
- Clause 7 — Support of the SMS
- Clause 8 — Operation of the SMS
- Clause 9 — Performance evaluation
- Clause 10 — Improvement

Additional guidance for applying the requirements is provided by ISO/IEC 20000-2 and ISO/IEC 20000-3. Vocabulary is defined in ISO/IEC 20000-10. ISO/IEC 20000-6 specifies requirements for bodies providing audit and certification of SMSs.

## SMS operation requirements

Clause 8 covers the operational core of the standard. It requires the organization to plan, deliver, and control services and the SMS, including:

- defining and managing the services in the service catalogue;
- planning and implementing change control for services and the SMS;
- managing suppliers and the relationships on which services depend;
- resolving incidents and service requests;
- managing problems to prevent recurrence and reduce impact;
- ensuring continuity of services across adverse events;
- satisfying availability and capacity requirements for each service;
- controlling the configuration of services and supporting assets;
- operating release and deployment activities so that production changes can be reproduced and validated;
- tracking and acting on risks and opportunities related to services.

These clauses are not optional. They are the operational conditions certification audits will sample against, so implementing them as a coherent system rather than as separate procedures is required.

## Adoption workflow

1. Establish the SMS scope, including which services, business units, locations, and supporting technologies are in scope.
2. Identify interested parties and the requirements those parties impose on services (regulatory, contractual, business).
3. Determine the operational requirements for each in-scope service, including availability, capacity, continuity, security, and support requirements.
4. Define policies, processes, and roles for each requirement; allocate ownership and evidence responsibilities.
5. Implement the SMS and operate it through normal and abnormal conditions.
6. Monitor, measure, and evaluate the SMS, including customer satisfaction indicators.
7. Conduct internal audits and management reviews on a documented schedule.
8. Address nonconformities, corrective actions, and continual improvement through a documented improvement register.

The standard assumes that the SMS exists to deliver value to customers and that the operation of services is the primary lens for performance evaluation rather than the maturity of internal documentation.

## Validation evidence

Useful evidence includes the SMS scope statement, the service catalogue, change records, incident and problem reports, service request records, supplier registers and performance reviews, continuity test results, availability and capacity reports, configuration baseline documents, release records, satisfaction survey results, internal audit reports, management review minutes, and the improvement register with status.

Where services are inherited from external providers, the SMS must still define its own monitoring and assurance responsibilities. A service that is provided by a partner cannot be excluded from the SMS simply because another party operates the platform; the requirements apply to the organization that is responsible for the customer relationship.

## Failure modes

Common adoption failures include:

- documenting the SMS scope and policy without operating the supporting processes to the same depth;
- confusing certification objectives with operational improvements and treating the audit as a one-time project;
- leaving the improvement register open indefinitely instead of closing completed items;
- excluding third-party services by definition instead of governing them through the SMS;
- failing to integrate incident, problem, change, and release processes, producing inconsistent records across those areas;
- aligning only the documentation with ISO/IEC 20000-1 while service operations continue to follow uncontrolled local practice.

## Relationship with ISO/IEC 27001

Where information security is also in scope, ISO/IEC 20000-1 and ISO/IEC 27001 can be operated together. The two standards share the Annex SL high-level structure, which simplifies their joint operation: a single leadership commitment, a single planning cycle, and a single management review can satisfy both standards provided evidence is organized against each standard's clauses. ISO/IEC 27001 focuses on confidentiality, integrity, and availability of information assets, while ISO/IEC 20000-1 focuses on the service management system that delivers services. Where the two overlap (such as availability targets, incident management, supplier management, and change control), the same activity can satisfy both standards as long as the evidence and ownership are recorded against each.

## Maintenance and continual improvement

The standard requires continual improvement but does not prescribe a single improvement methodology. ITIL 4 continual improvement practice, DMAIC-based quality methodologies, and internally defined improvement cycles have all been used to satisfy the clause. The methodological choice should not delay the underlying principle: monitor the SMS, evaluate outcomes, identify gaps, treat gaps with named actions, verify the actions closed the gap, and feed the result back into the next planning cycle.

## Certification evidence

Certification audits are organized around the standard's clauses. Each clause requires evidence of operation, not just documentation, and the evidence must be retrievable across the audit window. Useful patterns include maintaining a clause-to-evidence map, retaining records for the entire certificate validity, providing internal audit reports that cover each clause within the prior audit cycle, and tracking management review action items through closure. Organizations preparing for certification benefit from rehearsing the evidence collection with a mock audit; the rehearsal often surfaces records that are technically stored but not retrievable in audit format.

## Canonical sources

- ISO/IEC 20000-1:2018, Information technology — Service management — Part 1: Service management system requirements: https://www.iso.org/iso/iso_catalogue/catalogue_ics/catalogue_detail_ics.htm?csnumber=70636
- ISO/IEC 20000 family overview: https://www.iso.org/standards/popular/iso-iec-20000-family
- ISO/IEC 20000-2:2019, Information technology — Service management — Part 2: Guidance on the application of service management systems: https://www.iso.org/standard/74493.html

## Scope note

This article summarizes requirements of ISO/IEC 20000-1:2018; it is not a conformity guide and does not authorize certification decisions. The current edition should be confirmed with the official ISO catalog before adoption is finalized.
