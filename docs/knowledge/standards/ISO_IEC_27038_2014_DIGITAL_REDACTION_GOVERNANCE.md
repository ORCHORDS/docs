# ISO/IEC 27038:2014 Digital Redaction of Digital Records Governance

## 1. Scope

This card governs ORCHORDS adoption of ISO/IEC 27038:2014 ("Information technology — Security techniques — Specification for digital redaction of digital records") as the baseline for redacting sensitive content from documents, images, and other digital records before disclosure.

## 2. Normative references

- ISO/IEC 27038:2014.
- ISO/IEC 27001:2022 (information security management system).
- NIST SP 800-88 Rev. 1 (Guidelines for Media Sanitization).
- ORCHORDS Records Management Policy (internal).

## 3. Redaction principles

1. **Permanent removal**: the original information MUST be unrecoverable from the disclosed file, not merely hidden.
2. **Verification**: every redacted file MUST be machine- and human-verified before release.
3. **Audit trail**: every redaction event MUST be logged with operator, timestamp, and justification.
4. **Tooling**: only approved redaction tools are permitted; ad-hoc image editing is forbidden.

## 4. Approved redaction methods

| Source medium | Approved method |
| --- | --- |
| PDF text | `pdftk` or `qpdf` with overlay redaction |
| Word/PowerPoint | native redaction (Review > Restrict Editing) |
| Images (PNG/JPEG) | dedicated redaction tool with burned-in black box |
| Plain text logs | tokenisation before storage; never store raw secrets |
| Audio/video | overwrite the underlying file with a redaction log marker |

## 5. Prohibited patterns

- Black rectangle drawn on a layer above the original text in a PDF (text remains selectable).
- Cropping that does not remove embedded metadata.
- Replacing text with asterisks in a field that still contains the original value in metadata.

## 6. Verification procedure

1. Open the redacted file in a viewer that exposes underlying content (`exiftool`, `pdftotext`).
2. Confirm the redacted area contains no recoverable text.
3. Strip metadata (`exiftool -all=`, `qpdf --linearize`) before the file is published.
4. Have a peer reviewer (not the original operator) sign the verification log.

## 7. Retention

- Original pre-redaction files MUST be retained for 90 days after release in a restricted access store.
- Redaction logs MUST be retained for 7 years per the ORCHORDS Records Management Policy.

## 8. Review cadence

This card is reviewed every 180 days. The next scheduled review is 2027-03-07. New ISO/IEC 27038 edition or a privacy regulation change (GDPR, HIPAA, FERPA) triggers out-of-cycle updates.
