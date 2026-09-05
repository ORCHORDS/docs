---
title: "ISO/IEC 27040:2015 Storage Security — Version Transition Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "ISO/IEC 27040:2015 (Information technology — Security techniques — Storage security); https://www.iso.org/standard/44404.html"
---

# ISO/IEC 27040:2015 Storage Security — Version Transition Governance

## Purpose

This card governs how ORCHORDS references ISO/IEC 27040:2015 — the dedicated ISO/IEC standard for the security of data storage systems and the protection of data at rest across block, file, object, and ephemeral storage tiers. It sits alongside ISO/IEC 27001/27002 and ISO/IEC 27018 in the ORCHORDS governance taxonomy.

## Canonical Reference

- ISO/IEC 27040:2015, *Information technology — Security techniques — Storage security* (first edition, January 2015). 116 pages.
- Companion standards: ISO/IEC 27001:2022 (ISMS), ISO/IEC 27002:2022 (controls), ISO/IEC 27017:2015 (cloud), ISO/IEC 27018:2019 (PII in cloud), ISO/IEC 27035 (incident management), ISO/IEC 20000-1 (service management), ISO/IEC 27037 (digital evidence).

## Scope

ISO/IEC 27040:2015 covers:

- Storage architecture (block, file, object, key-value, archival)
- Storage media (HDD, SSD, tape, optical, NVMe-oF)
- Storage interfaces (FC, iSCSI, NFS, SMB, S3-compatible, SCSI)
- Storage management (provisioning, monitoring, retirement)
- Storage-related applications and services
- Backup and archival
- Sanitization, retention, and end-of-life disposal
- Security-relevant metadata (audit logs, configuration state)

It does NOT cover in-transit encryption (covered by ISO/IEC 27033 / TLS governance) or application-layer cryptography (covered by FIPS 140-3 and the ORCHORDS cryptographic agility playbook).

## Core Clauses and Controls

- **Clause 5: Storage security overview** — Threat taxonomy, design principles (least privilege, defence in depth, separation of duties, auditability).
- **Clause 6: Design and planning** — Storage-class selection, classification mapping, capacity planning, RTO/RPO alignment.
- **Clause 7: Storage security implementation** — Authentication, authorisation, audit, encryption-at-rest, media sanitization, key management hooks.
- **Clause 8: Storage security integration** — Interface and protocol security, network zoning, replication security, key rotation across replication targets.
- **Clause 9: Storage monitoring and auditing** — Audit-event coverage, log integrity, log retention, correlation with incident management.
- **Annex A (informative)**: Storage-specific threat catalogue (media theft, snapshot leakage, residual data on retired media, key compromise, supply chain attacks on storage firmware).
- **Annex B**: Mapping to ISO/IEC 27002:2013 controls (now updated to 27002:2022 in the supplementary mapping).

## Migration and Version Drift

ISO/IEC 27040 has not yet had a major revision since 2015; the 2022 ISO/IEC 27002 update (Annex A control renumbering) is the most material change to track:

| Topic | 2015 alignment | 2026 alignment |
| --- | --- | --- |
| Control numbering | ISO/IEC 27002:2013 | ISO/IEC 27002:2022 (Annex A renumbered to 93 controls in 4 themes: organisational, people, physical, technological) |
| Storage encryption | Annex A.10 (cryptography) + 27002:2013 10.1.x | Annex A.8.24 (use of cryptography) + A.5.x organisational controls |
| Backup | ISO/IEC 27001:2013 A.12.3 | ISO/IEC 27002:2022 A.8.13 (information backup) |
| Media handling | ISO/IEC 27001:2013 A.10.7 | ISO/IEC 27002:2022 A.7.10–7.14 (physical/media) + A.8.10 (information deletion) |
| Audit logging | ISO/IEC 27001:2013 A.12.4 | ISO/IEC 27002:2022 A.8.15–8.16 (logging, monitoring) |
| Key management | Cross-reference to ISO/IEC 11770 | unchanged |

## Usage in ORCHORDS

- Treat ISO/IEC 27040 as a *binding control layer* above ISO/IEC 27002:2022. Where 27002 specifies "protect data at rest" at a control level, 27040 specifies the storage-engineering implementation.
- For cloud object stores (S3-compatible), apply 27040 §7.5 (object-store-specific threats) — versioning, lifecycle, cross-region replication with distinct KMS keys, immutable retention, lifecycle-based deletion.
- For block storage, apply 27040 §7.3 (LUN masking, zoning, LUN-level encryption with KMIP-managed keys).
- For backup media, apply 27040 §7.7 — cryptographic protection of backup tapes, offsite transit controls, cryptographic erasure before decommission.
- For retired storage media, apply 27040 Clause 7 cryptographic sanitization guidance (NIST SP 800-88 Rev. 1 Clear/Purge/Destroy mapping).

## Open Items

- Track ISO/IEC 27040 second-edition work; expected 2026–2027 publication window.
- Map internal ORCHORDS storage-engineering playbook to 27040 §7 in the next review cycle.
- Watch ISO/IEC JTC1/SC42 (AI) output for storage-of-training-data overlap.
