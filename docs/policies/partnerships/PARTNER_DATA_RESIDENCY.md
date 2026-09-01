---
title: "Partner Data Residency"
owner: "Partnerships Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Partner Data Residency

## Purpose

This policy defines how data-residency obligations are specified, validated, and maintained with each partner that processes, stores, or transmits data on the organization's behalf or jointly. It ensures that the legal jurisdiction in which partner-held data resides is known, that cross-border transfer mechanisms are documented, that regulator expectations are met, and that evidence of residency is current and verifiable.

## Scope

This policy applies to all partners that handle organization-controlled data, partner-sourced data, or jointly processed data, including processing environments, backup repositories, secondary copies, log archives, and disaster-recovery sites. It covers identification of the residency obligation, selection of the transfer mechanism, evidence collection, periodic validation, and the records that demonstrate compliance with the agreed jurisdiction. It does not prescribe the residency itself; that determination follows from applicable law, contractual commitments, customer commitments, and risk appetite.

## Requirements

- The Partnerships Lead MUST record the data-residency obligation for each partner engagement, including the jurisdictions in which partner-held data MUST and MUST NOT reside, and the data classes to which the obligation applies.
- Any cross-border transfer of partner-held data MUST rely on a lawful transfer mechanism recognized in the source jurisdiction (for example, adequacy decision, standard contractual clauses, binding corporate rules, or recognized certification).
- The partner MUST provide evidence of residency on request, including data-center locations, subprocessor locations, replication topology, and backup geography.
- The partner MUST notify the organization within ten business days of any change in residency that affects the recorded obligation, including new locations, replication changes, or processor changes.
- The Partnerships Lead MUST validate residency evidence at least annually and more frequently for high-risk or regulated engagements.
- The organization MUST incorporate residency obligations into the partner agreement, the security exhibit, and the data-processing addendum.
- The Partnerships Lead SHOULD maintain a partner-residency map showing the jurisdictions of primary storage, replication, and backup, and reconcile it against the contract at each validation.
- The organization MAY require independent attestation of residency by a qualified auditor where the engagement involves regulated data or significant volume.

## Workflow

1. **Obligation definition.** During onboarding, the Partnerships Lead defines the residency obligation using a data-classification matrix and the engagement's regulatory profile.
2. **Contract incorporation.** The obligation is incorporated into the data-processing addendum and the security exhibit.
3. **Evidence request.** The partner is asked to provide a residency attestation and supporting evidence for each obligation.
4. **Validation.** The Partnerships Lead validates the evidence, reconciling residency claims against the contractual obligation.
5. **Annual review.** Residency evidence is revalidated annually or whenever a change is reported.
6. **Change handling.** Any change in residency triggers an interim review, a risk assessment, and, where required, renegotiation of the contract or transfer mechanism.
7. **Records retention.** Attestations, evidence, and reconciliations are retained per the records-retention schedule.

## Controls

- A residency record exists for every partner that processes organization-controlled data, with obligation, evidence, and validation date.
- A residency change-notification commitment is in every data-processing addendum.
- Annual validation evidence is current and reconcilable against the contract.
- Independent attestation is required where the engagement involves regulated data or significant cross-border volume.

## Backup, replication, and disaster recovery

Residency obligations extend beyond primary storage to backup copies, replicas, snapshots, log archives, and disaster-recovery environments. The partner MUST disclose the geographic location of each tier, the replication topology, the retention of backup media, and the location to which backup media is returned for service. The Partnerships Lead reconciles the disclosed topology against the contract at each validation and requires remediation where any tier is inconsistent with the obligation. Disaster-recovery exercises that exercise cross-region failover are documented in the residency record.

## Records and retention

Residency evidence, attestations, reconciliations, and change-notification records are retained for the period required by the records-retention schedule and made available to authorized reviewers including Privacy, Legal, Security, and external auditors. Where regulatory access requests require evidence of residency, the Partnerships Lead coordinates with Privacy and Legal to produce the relevant records under the standard cooperation clause.

## Canonical sources

- European Data Protection Board, "Guidelines on the Territorial Scope of the GDPR," and adequacy decisions page: https://edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-32018-territorial-scope-gdpr_en
- European Commission, "Standard Contractual Clauses for the transfer of personal data to third countries": https://commission.europa.eu/document/fa09cbad-dd7d-4c60-9f29-1cd772d1f70d_en
- ISO/IEC 27018:2019, "Code of practice for protection of personally identifiable information in public clouds acting as PII processors," controls on data location: https://www.iso.org/standard/76559.html
- APEC Cross-Border Privacy Rules (CBPR) system: https://www.apec.org/Groups/Committee-on-Trade-and-Electronic-Business/Electronic-Commerce-Steering-Group/Cross-Border-Privacy-Rules-(CBPR)