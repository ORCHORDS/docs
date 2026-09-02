# ISO 14721:2012 OAIS Reference Model Template Governance

## Purpose

ISO 14721:2012 (CCSDS 650.0-M-2), "Space data and information transfer systems — Open archival information system (OAIS) — Reference model," defines the OAIS reference model for long-term preservation of digital information. The model specifies six functional entities (Ingest, Archival Storage, Data Management, Preservation Planning, Access, Administration), the information packages ingested, stored, and disseminated (SIP, AIP, DIP), and the preservation description information (PDI) categories needed to maintain usability over time. This article governs the application of the OAIS model as a template for designing long-term digital preservation systems.

## Scope

The reference model applies to any organization that has a long-term responsibility for preserving digital information. Within this knowledge base, the article covers the OAIS functional model, the information package concept, the PDI categories (reference information, context information, provenance information, access rights information, fixity information, history), and the documentation of the preservation system's compliance with OAIS. It does not cover the substantive preservation tools or formats; those are governed by other standards and by community practice.

## Workflow

1. Establish the preservation purpose and the user community the preservation system must serve. OAIS defines designated community; the system's preservation choices must be made in that community's context.
2. Implement the six OAIS functional areas:
   - Ingest: receive SIPs from producers, validate them, generate AIPs.
   - Archival Storage: store AIPs and their PDI.
   - Data Management: maintain descriptive information and the system catalog.
   - Preservation Planning: monitor the preservation environment, develop preservation strategies, and apply migration plans.
   - Access: provide DIPs to consumers, mediated by the access rights.
   - Administration: negotiate agreements with producers and consumers, manage resources.
3. Maintain PDI for each AIP: reference information (identifier), context information (the relationship of the data to its environment), provenance information (history), access rights, fixity information, and history.
4. Establish preservation strategies and migration plans. Format obsolescence, hardware obsolescence, and software obsolescence are expected; the system must plan for them.
5. Negotiate submission agreements with producers and dissemination agreements with consumers.

## Controls and evidence

OAIS evidence includes the designation of the user community, the implementation of the functional areas, the PDI records, the preservation plans and migration records, and the submission and dissemination agreements. Audit-friendly implementations should be able to demonstrate the seven mandatory responsibilities of an OAIS (negotiate submission, receive data, derive dissemination, deliver data, preserve data, formulate policy, provide access).

## Validation

Validation should confirm the six functional areas operate, the PDI is captured for each AIP, preservation strategies are documented and applied, submission agreements exist for each producer relationship, and the system can produce DIPs for the designated community. Periodic preservation audits (e.g., against ISO 16363) provide additional assurance.

## Failure correction

Common failure modes: PDI is captured incompletely (corrective: ensure all six PDI categories are present for each AIP); preservation strategy is reactive rather than planned (corrective: develop a preservation plan with monitoring, decision points, and migration paths); submission agreements are not in place (corrective: require a submission agreement before ingest); access is provided without authorization (corrective: enforce access rights information at the Access functional area); migration plans are documented but not executed (corrective: trigger migration on format obsolescence or according to plan).

## Limitations

ISO 14721 is a reference model; it is not a certification scheme. The model does not prescribe specific storage technologies, formats, or preservation tools. The model assumes the organization has the resources and the commitment to maintain preservation over the long term. The standard does not address legal deposit or specific cultural heritage obligations; readers should overlay their sector requirements.

## Scope note

This article summarizes project-neutral use of ISO 14721:2012 as a template. It does not assert any specific preservation system's conformance or claim any certification outcome.

## Canonical sources

- ISO 14721:2012 — Space data and information transfer systems — Open archival information system (OAIS) — Reference model: https://www.iso.org/standard/57284.html
- CCSDS 650.0-M-2 — OAIS Reference Model (consultative committee): https://public.ccsds.org/pubs/650x0m2.pdf