# NIST SP 800-88 Rev. 1 — Guidelines for Media Sanitization Governance

## 1. Scope

This card governs the application of NIST Special Publication 800-88 Revision 1, "Guidelines for Media Sanitization" (December 2014), to media-bearing assets used by the OrchordsAI knowledge base and analytics estate. It applies to all digital media that store regulated, confidential, internal, or sensitive information at end of lease, end of life, redeployment, or release from custody. The card addresses sanitization decision-making, sanitization methods, cryptographic erase considerations, and verification or attestation posture. It complements NIST SP 800-53 Rev. 5 controls MP-6 (Media Sanitization) and MP-8 (Media Downgrading) and cross-references NIST SP 800-57 Part 1 Revision 5 for cryptographic key management.

## 2. Normative references

- NIST SP 800-88 Rev. 1 — Guidelines for Media Sanitization (December 2014).
- NIST SP 800-53 Rev. 5 — Media Protection control family, specifically MP-6 Media Sanitization and MP-8 Media Downgrading.
- NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management: General.
- NIST SP 800-171 Rev. 3 — 3.8 Media Protection (for CUI-bearing media).
- FIPS 199 / NIST SP 800-60 Vol. 1 / Vol. 2 — categorization input for sanitization decisions.

## 3. Terms and definitions

- Media sanitization: the process of rendering access to target data on the media infeasible for a given level of effort.
- Clear: logical technique to sanitize data on user-addressable storage using standard read and write commands so that the data is not readily accessible through standard interfaces.
- Purge: physical or logical technique that renders target data recovery infeasible using state-of-the-art laboratory techniques; for example, cryptographic erase, block erase, or vendor-specific secure erase commands.
- Destroy: physical technique that renders the media unusable and the data recovery infeasible using state-of-the-art laboratory techniques, such as shredding, incineration, or disintegration.
- Cryptographic erase (CE): sanitization technique that renders encrypted data unreadable by deleting or destroying the keying material used to encrypt the media.
- Media downgrading: reducing the sensitivity classification of media through sanitization to permit reuse at a lower sensitivity.
- Verification: confirmation that a sanitization technique was applied successfully to the intended target media and scope.
- Attestation: signed record produced by the sanitizer, the tool, or the operator providing evidence of sanitization completion.

## 4. Sanitization decision matrix

NIST SP 800-88 Rev. 1 organizes sanitization decisions by information sensitivity and media type. Three inputs drive the decision: the security categorization of the data (FIPS 199 low, moderate, or high); the media type (magnetic, flash-based solid-state, optical, or hybrid); and the intended disposition (reuse within the same confidentiality context, reuse at a lower sensitivity, or release outside organizational control). A reusable decision matrix maps each combination to clear, purge, or destroy, with the matrix revalidated on each new storage technology adoption.

For controlled unclassified information (CUI) and moderate-confidentiality data, the baseline expectation is purge for reuse and destroy for release outside organizational control. For high-impact data (FIPS 199 high), purge is the minimum acceptable treatment for reuse and destroy is required for release. When a media type lacks an effective purge technique, destroy is the only defensible choice. The matrix is documented, version-controlled, and referenced by media-disposition tickets, contracts, and disposal-vendor statements of work.

## 5. Sanitization methods (clear / purge / destroy)

Clear is applied through standard read and write commands applied to logical block addresses, typically by overwriting user-addressable space with fixed or random patterns. It is appropriate only for magnetic media and only when the data sensitivity does not exceed moderate impact. Clear does not address hidden areas such as host-protected areas, device configuration overlays, or reallocated sectors; sanitization procedures must explicitly enumerate these areas or fall back to purge.

Purge techniques include cryptographic erase, block erase, and vendor-specific device-managed commands such as ATA Secure Erase, NVMe Format with secure erase setting, or SCSI SANITIZE command. Purge is appropriate for solid-state drives when supported by the controller and firmware, and for self-encrypting drives when paired with cryptographic erase of the media encryption key. Destroy techniques include shredding, degaussing for magnetic media, pulverization, incineration, and chemical disintegration. Destroy is mandatory when no reliable purge mechanism is available and is preferred for media leaving the organization's custody.

Selection of a method is documented per asset class. Media-rotation runbooks capture the approved clear, purge, or destroy technique for each platform, with explicit identification of firmware prerequisites, vendor utility versions, and tool-configuration baselines. When a media type is introduced, a new sanitization procedure is drafted, validated against vendor guidance, and added to the matrix before the first instance enters production.

## 6. Cryptographic erase and media key management

Cryptographic erase (CE) renders data infeasible to recover by sanitizing the keying material used to encrypt the media. CE is only as strong as the surrounding key management lifecycle. Cryptographic keys must be generated, distributed, stored, rotated, and destroyed in accordance with NIST SP 800-57 Part 1 Revision 5; keys must never be reused across devices unless the data classification supports it. Self-encrypting drives (SEDs) must be configured so that the data encryption key is generated by the device, never exported in plaintext, and tightly bound to the device authentication credential.

CE-specific governance requires several controls. Key escrow records must exist for as long as data recovery is a possible legal or operational requirement, with explicit destruction evidence once the retention period ends. Cryptographic modules must be FIPS 140-3 validated when required by the data classification. Re-key events must trigger a CE event log entry even when the media is not leaving custody, so that key rotation policy and sanitization policy remain consistent. When a vendor key management service is used, contractual terms must give the organization sole control of key destruction commands for media it owns.

## 7. Verification, attestation, and audit posture

Verification confirms that the sanitization technique was applied to the intended scope, not merely to the device as a whole. For clear and purge operations, verification includes a post-sanitization read-back or hash comparison, a tool-generated log captured from the sanitizer, and reconciliation against the media inventory record. For destroy operations, verification includes photographic evidence, witness signatures or video, and disposal-vendor certificates of destruction cross-referenced to serial numbers or asset tags.

Attestation is the signed, time-stamped evidence that a specific sanitization action was completed against a specific asset. Attestation records include asset identifier, media type, sanitization technique, tool version, operator, verifier, completion timestamp, and any residual caveats. Attestation records are stored with the asset management system and retained according to the records retention schedule for the underlying data classification. Cryptographic hashes of attestation records are written to an append-only audit store so that later tampering can be detected.

Internal audits sample sanitization records against the decision matrix and the asset disposition log. Findings trigger root-cause analysis, vendor escalation, or runbook revision. External audits review the sanitization program against NIST SP 800-88 Rev. 1 and NIST SP 800-53 MP-6 / MP-8 expectations. Changes to media technology, sanitization tools, or service providers trigger a re-baselining of the matrix before the new option enters routine use.

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
