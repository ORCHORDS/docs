# ISO 14721 OAIS Reference Model Governance

## Purpose

The ISO 14721 Open Archival Information System (OAIS) reference model defines a framework for the long-term preservation of digital information. OAIS is the de facto standard for digital preservation repositories. Governance ensures that an organization maintaining a digital preservation repository implements the OAIS functional model, manages the designated community, and addresses preservation planning.

## Current context and source status

ISO 14721 was first published in 2003 and updated as ISO 14721:2012. A second edition was published as ISO 14721:2023 (CCSDS 650.0-M-3 equivalent). The 2023 edition updates the model with clarifications on authentication, preservation planning, and software preservation. Verify the current ISO 14721 publication before treating any specific clause as a current requirement.

## Governance workflow and controls

### 1. Establish the OAIS framework

Adopt the OAIS framework: SIP (Submission Information Package), AIP (Archival Information Package), DIP (Dissemination Information Package). Document the package formats.

### 2. Define the designated community

Define the designated community: the set of consumers who should be able to understand the preserved information. Document the knowledge base required by the community.

### 3. Apply the six functional entities

Implement the six OAIS functional entities:

- ingest (receiving SIPs);
- archival storage (storing AIPs);
- data management (administrative metadata);
- preservation planning (strategic preservation activities);
- access (creating DIPs);
- administration (managing the repository).

### 4. Manage representation information

Manage representation information:

- reference information (taxonomy, ontology);
- context information (relationship to other information);
- provenance information (history);
- fixity information (integrity);
- access rights information.

Document the representation information for each AIP.

### 5. Apply preservation planning

Apply preservation planning: monitor the designated community, the technology base, and the threats to preservation. Implement preservation strategies (migration, emulation, replication).

### 6. Manage authenticity

Manage authenticity through fixity, provenance, and contextual information. Apply audit logging.

### 7. Apply the OAIS audit checklist

Apply the OAIS audit checklist (ISO 14721) or comparable (TRAC, CoreTrustSeal). Conduct regular audits.

## Validation and evidence

- OAIS implementation documentation.
- Designated community definition.
- Package format documentation.
- Preservation planning records.
- Audit reports.

## Failure correction

Common defects include missing preservation planning, weak fixity verification, and inadequate designated community definition. Corrective actions include a preservation planning program, a fixity check cadence, and a designated community review.

## Limitations

- OAIS is a reference model, not a certifiable standard.
- Implementing all six functional entities requires investment.
- Designated community knowledge evolves; re-evaluate.
- Some preservation strategies (emulation, migration) are complex.

## Canonical sources

- ISO 14721:2023, Space data and information transfer systems — Open archival information system (OAIS) — Reference model, current edition.
- CCSDS 650.0-M-3, Reference Model for an OAIS, current edition.
- CoreTrustSeal Trustworthy Digital Repositories requirements, current edition.

## Scope note

This article belongs to the engineering leaf and cross-references the operations leaf for archival storage, the standards leaf for preservation standards, and the reference leaf for metadata standards.
