# NIST SP 800-88 r2 Media Sanitization Template Governance

## Purpose

NIST SP 800-88 r2, "Guidelines for Media Sanitization," provides guidance on sanitization methods (clearing, purging, destroying) for digital media so that the sanitization is matched to the sensitivity of the information and the intended reuse or disposal of the media. The publication addresses a wide range of media types (magnetic, optical, solid-state, electronic, mobile devices), the verification of sanitization, and the documentation of sanitization decisions. This article governs the application of SP 800-88 r2 as a template for the media sanitization decision process.

## Scope

The publication applies to any organization that handles digital media containing sensitive information. Within this knowledge base, the article covers the sanitization decision matrix (information sensitivity, sanitization method, media type), the three sanitization methods (clearing, purging, destroying), the verification of sanitization, and the documentation requirements. It does not cover sector-specific sanitization regulations; readers should overlay their sector requirements.

## Workflow

1. Identify the media to be sanitized and the information it contains. Apply the organization's information classification scheme.
2. Select the sanitization method based on the information sensitivity and the intended reuse or disposal:
   - Clearing: rendering the data unreadable through standard interfaces; appropriate for media that will be reused within the organization.
   - Purging: rendering the data unrecoverable even with forensic tools; appropriate for media that will leave the organization's control.
   - Destroying: physical destruction; appropriate for media at end of life, for highly sensitive data, or where purging is not feasible.
3. Apply the method appropriate to the media type. SP 800-88 r2 provides media-specific guidance for HDDs, SSDs, optical media, magnetic tape, mobile devices, and others.
4. Verify the sanitization. Verification may include reading back the media, using the manufacturer's verification tools, or destroying verification.
5. Document the sanitization decision, the method applied, the verification, and the media's disposition.

## Controls and evidence

Sanitization evidence includes the sanitization decision record, the method applied, the verification record, and the disposition. For media with high-sensitivity data, additional evidence may include witness signatures, photographs of destruction, or third-party certification.

## Validation

Validation should confirm the decision matrix was applied, the method matches the sensitivity and the media type, the verification was performed, and the documentation is complete. Periodic audits of media sanitization records provide additional assurance.

## Failure correction

Common failure modes: sanitization method is selected based on convenience rather than the decision matrix (corrective: require the decision matrix to be applied and documented); verification is skipped (corrective: enforce verification for every sanitization event); documentation is incomplete (corrective: require complete records); media is reused with residual data from a prior sensitivity level (corrective: re-sanitize to the current sensitivity level); sanitization of SSDs is treated like HDDs (corrective: apply SSD-specific methods such as cryptographic erase or Secure Cryptographic Erase where supported).

## Limitations

SP 800-88 r2 provides guidelines; it does not certify sanitization products or services. The publication does not address every media type or every emerging technology; the organization's media inventory may require additional research for specific media. The publication does not address legal obligations for retention or for forensic preservation; these are governed by separate policies.

## Scope note

This article summarizes project-neutral use of NIST SP 800-88 r2 as a template. It does not assert any specific sanitization outcome or claim any certification.

## Canonical sources

- NIST SP 800-88 r2 — Guidelines for Media Sanitization: https://csrc.nist.gov/publications/detail/sp/800-88/rev-2/final