# NIST SP 800-88 Media Sanitization Operations

## Media and confidentiality boundary

NIST Special Publication 800-88 Rev. 1, "Guidelines for Media Sanitization," defines the sanitization methods that an organization should apply to digital media containing sensitive information at end of life. The publication is the U.S. National Institute of Standards and Technology's authoritative guidance and is referenced in federal acquisition regulations (e.g., FAR clause 52.204-23) and in NIST SP 800-171. This article covers the operational workflow that an organization follows when retiring, repurposing, or otherwise disposing of digital media. It does not cover physical destruction of non-digital records (paper, microfilm), which is governed by separate federal and state retention schedules.

## Clear, purge, or destroy decision sequence

1. **Inventory the media and the data class.** The organization catalogs the media type (hard disk, solid-state drive, removable media, mobile device, multifunction printer storage) and the highest data class stored on each item. The data class determination uses the organization's information classification policy and any contract-driven data classes (e.g., CUI, cardholder data, personal health information).
2. **Select the sanitization method.** The selected method follows the publication's three categories: Clear (logical techniques to overwrite user-addressable storage), Purge (physical or logical techniques that render recovery infeasible by state-of-the-art laboratory techniques), and Destroy (physical destruction of the media). NIST SP 800-88R1 also adds an "unrecoverable" assurance for the most sensitive data classes through cryptographic erase of self-encrypting drives with verified key destruction.
3. **Document the sanitization decision.** The sanitization decision records the media identifier, the data class, the chosen method, the operator, the date, and the tool version. The decision is reviewed by the asset owner and the information security team.
4. **Execute the sanitization.** The operator executes the chosen method using an approved tool. For Clear, the tool must support the specific storage technology (for example, ATA Secure Erase on SSDs versus overwrite on rotating disks). For Purge, cryptographic erase is acceptable on self-encrypting drives when the cryptographic key is destroyed.
5. **Verify the result.** Verification confirms that the chosen method ran to completion and that the post-sanitization state meets the "unrecoverable" assurance criterion. Verification methods include vendor-provided erasure logs, post-erasure boot-time failure, and laboratory spot tests on a sample basis.
6. **Retire the media or reissue.** When verification confirms sanitization, the media is either decommissioned (recycled, donated, or destroyed) or reissued for a less-sensitive use. A reissued asset retains a sanitization record with the prior data class and the new data class.

## Asset, method, tool, and disposition data

The sanitization record carries the asset tag, the media type, the manufacturer and model, the serial number, the data class stored prior to sanitization, the chosen sanitization method (Clear, Purge, or Destroy), the specific tool and tool version, the operator identification, the verification evidence (erasure log, boot failure), the verification reviewer, and the disposition decision (decommission or reissue).

## Sanitization verification evidence

Validation evidence includes the tool-generated sanitization log, the verification record (post-erasure state, sample laboratory test when required), the disposition record (recycling receipt, destruction witness attestation), and the asset register entry showing the new status. Periodic audits sample media from each sanitization method to confirm that the verification was performed; recurring verification failures trigger a tool refresh and retraining.

## Failed sanitization and custody handling

- **Wrong method selected.** A solid-state drive was sanitized with an overwrite tool appropriate for rotating disks; overwrite on SSDs does not reach all storage locations. The asset is re-sanitized using the manufacturer's Secure Erase command or cryptographic erase, the verification is re-run, and the SOP is updated to require SSD-specific methods.
- **Cryptographic erase without key destruction.** A self-encrypting drive was cryptographically erased but the original encryption key was retained in a key vault. The key is destroyed in the vault, the drive is re-verified, and the SOP is updated to require key destruction as part of the cryptographic erase procedure.
- **Verification skipped.** The operator executed the sanitization but did not record verification evidence. The asset is re-verified or re-sanitized, and the SOP is updated to require verification as a mandatory step before disposition.
- **Media incorrectly inventoried.** A high-class asset was sanitized as low-class. The asset is re-sanitized with a method appropriate to the higher class, the inventory is updated to reflect the actual data class, and the discrepancy is logged for further investigation.
- **Reissued to a higher class.** A sanitized drive was reissued for a use that stores a higher class than the sanitization method supports. The drive is re-sanitized using a method that meets the higher class, and the SOP is updated to require a class check before reissue.

## Technology-specific limits

The publication supplies risk-based guidance rather than a universal destruction mandate. Contract clauses, records holds, environmental rules, device architecture, and data classification can require a different disposition. A tool completion message is not by itself proof that inaccessible storage areas were sanitized.

## Canonical sources

- **Primary authority 1:** National Institute of Standards and Technology, *NIST SP 800-88 Rev. 1 — Guidelines for Media Sanitization* — https://csrc.nist.gov/publications/detail/sp/800-88/rev-1/final
- **Primary authority 2:** National Institute of Standards and Technology, *NIST Media Sanitization Self-Reference Guide* — https://csrc.nist.gov/projects/media-sanitization-reference-guide
