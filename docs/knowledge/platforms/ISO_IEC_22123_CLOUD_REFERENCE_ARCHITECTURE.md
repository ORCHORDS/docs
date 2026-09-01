# ISO/IEC 22123 Cloud Reference Architecture

## Purpose

ISO/IEC 22123 (multipart, formerly ISO/IEC 17789) defines a cloud computing reference architecture (CCRA). It provides a vendor-neutral, role-based vocabulary and a structural decomposition that engineering and architecture teams can use to describe where their components sit, which role plays which role, and which cross-cutting concerns apply across the cloud ecosystem.

## Scope

The CCRA is an architecture document, not a control set, risk framework, or compliance program. It pairs naturally with ISO/IEC 27017 (cloud-sector information security controls), ISO/IEC 27018 (PII protection in public cloud), and ISO/IEC 22123-2:vocabulary. It is also useful as a common reference when reconciling documentation from multiple cloud providers that use different internal taxonomies.

## Roles

The CCRA defines roles, not products. A single organization can play multiple roles, and a single product can be viewed through multiple roles.

- **Cloud service customer (CSC)**: the party that uses cloud services.
- **Cloud service provider (CSP)**: the party that makes cloud services available.
- **Cloud service partner**: a party that provides supporting capabilities such as integration, audit, or managed services.
- **Cloud auditor**: a party that can conduct independent assessment of cloud services.
- **Cloud service broker**: an intermediary that arranges contracts between CSCs and CSPs.

## Cross-cutting aspects

The CCRA identifies cross-cutting aspects that apply to any cloud service regardless of the role being played. They are useful as headings in an architecture decision record or in a target operating model.

- **Auditability**: evidence must be available to internal and external auditors.
- **Availability**: the service must meet its stated availability targets.
- **Data governance**: data lifecycle, residency, lineage, and disposal are explicitly governed.
- **Identity and access management**: identities, authentication, and authorization are centrally governed across roles.
- **Interoperability**: services expose standards-based interfaces where practical.
- **Performance**: the service meets its stated performance characteristics under documented load.
- **Privacy**: PII is handled according to applicable regulation and consent.
- **Resilience**: the service continues to operate under partial failure.
- **Security**: confidentiality, integrity, and non-repudiation are preserved.
- **Service-level agreements**: SLAs make the above measurable and enforceable.

## Architectural view

The CCRA separates functional concerns from implementation concerns. The functional view identifies what each role does; the implementation view identifies how those functions are realized in a specific deployment (private, public, community, hybrid). Both views must be documented for a complete architecture description; collapsing them invites confusion between "what we promise" and "what we built."

## Engineering workflow

1. Identify which CCRA roles the organization plays for each in-scope service.
2. For each role, list the cross-cutting aspects that apply and the controls that implement them.
3. Map internal teams and tools to CCRA roles so that ownership is unambiguous.
4. Use the role vocabulary consistently in architecture documents, contracts, and SLAs.
5. Use the cross-cutting aspects as a checklist when reviewing a new cloud service for fit.
6. Reconcile internal terminology with CCRA roles when integrating an external partner or broker.

## Controls and evidence

- A role-to-team matrix that names the responsible owner for each CCRA role.
- A cross-cutting aspects register with one row per aspect and evidence link per row.
- Architecture diagrams that separate the functional view from the implementation view.
- SLAs that map to the cross-cutting aspects and that name the CCRA roles involved.

## Validation

- Independent reviewer confirms each in-scope service is documented under exactly the CCRA roles that apply.
- The cross-cutting aspects register is reviewed after any service change.
- A partner or broker integration is reviewed by both sides against the role vocabulary before contract signature.

## Failure modes and corrections

- Treating CSP as a synonym for "vendor" — correct by using CCRA roles even when the relationship is informal.
- Collapsing customer and provider responsibilities into one diagram — correct by separating the functional view from the implementation view.
- Describing cross-cutting concerns as implementation details rather than as governance objectives — correct by anchoring each aspect in a control objective and an SLA term.
- Mapping internal teams to CCRA roles only once at program start — correct by re-running the mapping when teams or services change.

## Limitations

- The CCRA is a vocabulary and architecture, not a control implementation guide.
- It does not specify how to assess conformance; the assessor must define the assessment methodology.
- It does not prescribe a particular cloud-native pattern (microservices, serverless, containers) as canonical.
- Some cross-cutting aspects overlap with control families in ISO/IEC 27001 and ISO/IEC 27002; the CCRA is intentionally not duplicative of those.

## Canonical sources

- ISO/IEC 22123-1:2023 (ISO, primary authority) — Cloud computing — Concepts and terminology: https://www.iso.org/standard/82635.html
- ISO/IEC 22123-2:2023 (ISO, primary authority) — Cloud computing — Reference architecture: https://www.iso.org/standard/83845.html

## Scope note

This article restates project-neutral architecture guidance from ISO/IEC 22123. It does not assert conformance to the standard or compliance with any regulation.