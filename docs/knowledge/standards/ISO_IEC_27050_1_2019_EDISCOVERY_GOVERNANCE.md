# ISO/IEC 27050-1:2019 — Electronic Discovery (e-Discovery) Governance

## 1. Scope

This card governs OrchordsAI adoption of ISO/IEC 27050-1:2019 (Information technology — Electronic discovery — Part 1: Overview and concepts) as the conceptual baseline for identifying, preserving, collecting, processing, reviewing, and producing electronically stored information (ESI) in legal, regulatory, and internal investigations. The card applies to all information systems, repositories, and endpoints that may contain ESI subject to a discovery obligation, and is supplemented by ISO/IEC 27050-2:2018 (guidance for governance and management of electronic discovery) and ISO/IEC 27050-3:2020 (code of practice for electronic discovery).

## 2. Normative references

- ISO/IEC 27050-1:2019 — Electronic discovery — Part 1: Overview and concepts.
- ISO/IEC 27050-2:2018 — Electronic discovery — Part 2: Guidance for governance and management of electronic discovery.
- ISO/IEC 27050-3:2020 — Electronic discovery — Part 3: Code of practice for electronic discovery.
- ISO/IEC 27001:2022 and ISO/IEC 27002:2022 (cross-reference for information security controls supporting e-Discovery).
- ISO/IEC 15489-1:2016 (records management) and ISO 14641:2018 (electronic archiving) where e-Discovery overlaps with archival retention.

## 3. Terms and definitions

- Electronically stored information (ESI): any data subject to discovery, including email, documents, databases, logs, chat, and cloud-native artefacts.
- Legal hold: a directive that suspends normal retention and deletion for ESI relevant to a matter.
- Custodian: a person or system in possession or control of potentially relevant ESI.
- Chain of custody: the documented sequence of handling, transfer, and access events for collected ESI.
- Defensibility: the property that the e-Discovery process can withstand scrutiny by a court, regulator, or auditor.

## 4. e-Discovery process overview

ISO/IEC 27050-1:2019 frames e-Discovery as a six-stage reference model: identification, preservation, collection, processing, review, and production. Each stage is a control point with defined inputs, outputs, accountable roles, and verifiable evidence. The model is technology-neutral and applies equally to on-premises repositories, cloud SaaS, and ephemeral workloads. Defensibility depends on process repeatability rather than on a specific tool, so each stage must be documented, time-stamped, and reproducible.

The reference model also recognises iterative and concurrent execution. Identification may continue as new custodians or sources are discovered during preservation or collection; preservation may extend as scope evolves; and review may identify additional sources requiring preservation. The standard accepts this fluidity but requires that every change be captured in the matter record with timestamp, author, and justification, so that the overall process remains auditable end-to-end.

## 5. Identification, preservation, collection, processing, review, production

Identification maps systems, custodians, and data sources that may hold relevant ESI and records scope decisions in a matter register. Preservation issues legal holds that freeze relevant ESI, suspends routine deletion for in-scope sources, and tracks acknowledgement by custodians. Collection acquires ESI using forensically sound methods that preserve metadata, hash values, and chain of custody. Processing converts collected data into a reviewable form through deduplication, de-NISTing, email threading, and metadata normalisation. Review applies relevance, privilege, and redaction decisions with reviewer attestation. Production delivers responsive, non-privileged ESI in an agreed format with a privilege log and confidentiality protections.

Each stage records its accountable role: identification is owned by legal counsel with IT support; preservation by legal operations and IT records management; collection by forensic or e-Discovery professionals; processing by technical operators with quality assurance review; review by qualified attorneys or subject-matter reviewers; and production by legal counsel with technical production support. Documented handoffs and sign-offs at each transition are essential to defensibility.

## 6. Cross-border discovery controls

Cross-border discovery introduces data-protection, sovereignty, and transfer-mechanism obligations. Before collection or production, each cross-border flow is assessed for lawful basis, applicable regulations (including EU GDPR transfers, national data-localisation rules, and sector-specific regimes), and the contractual mechanism supporting the transfer (standard contractual clauses, adequacy decisions, or equivalent). Technical controls enforce residency in transit and at rest, and redaction or pseudonymisation is applied where minimisation is required by the destination regime. Transfer decisions and legal advice are retained as part of the matter record.

Where local law prohibits or restricts cross-border transfer of certain ESI, the matter record documents the legal conflict, the in-jurisdiction alternative (local collection, local processing, or local review), and the basis for proceeding. Coordination with data-protection officers and external counsel is recorded in the matter timeline. The output of cross-border assessment is a per-matter data-transfer register retained alongside the chain-of-custody log.

## 7. Governance and evidence integrity

Governance under ISO/IEC 27050-1:2019 is anchored in defensibility. Each matter has a named custodian, a documented hold scope, an evidence inventory, and a chain-of-custody log. Access to collected ESI is restricted to authorised reviewers with audit logging. Hash values are recorded at collection and verified at each handoff. Periodic internal audits verify that the e-Discovery programme conforms to ISO/IEC 27050-2 governance expectations and ISO/IEC 27050-3 operational practice, and that exceptions are documented, justified, and time-bound. Lessons learned feed back into identification and preservation playbooks for future matters.

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
