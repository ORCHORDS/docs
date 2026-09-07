# AI Content Provenance Governance

## 1. Scope
This standard defines how teams declare, embed, and verify
provenance information for AI-generated content so that downstream
consumers can identify the origin, model, and process used to
produce a given artefact.

It applies to all AI-generated content produced by or on behalf of
the platform, including text, image, audio, video, code, and
structured data outputs. It does not replace content moderation
or licensing obligations documented in service runbooks.

## 2. Normative references
The following documents are referenced and inform the requirements
of this standard:

- C2PA (Coalition for Content Provenance and Authenticity)
  Technical Specification.
- W3C Verifiable Credentials Data Model 2.0.
- EU AI Act (Regulation (EU) 2024/1689) — transparency obligations
  for generative AI.
- NIST AI Risk Management Framework — Govern and Map functions.
- Platform AI Risk Tiering Practice Governance.

## 3. Terms and definitions
For the purposes of this standard, the following terms apply:

- **Provenance manifest**: a structured assertion describing the
  origin, model, and process used to generate a content artefact.
- **Cryptographic assertion**: a manifest signed using a verifiable
  credential or C2PA-compliant signing mechanism.
- **Provenance disclosure**: a human-readable statement of AI
  generation that accompanies the artefact.
- **Provenance verification**: the act of validating a manifest's
  signature and inspecting its content.

## 4. Provenance requirements
All AI-generated content MUST carry a provenance manifest at
production time. Manifests MUST identify the producing model
(identifier and version), the prompt hash, the generation
timestamp, and the platform's signing identity.

## 5. Disclosure requirements
AI-generated content delivered to end users MUST be accompanied by
a disclosure statement identifying the content as AI-generated.
Disclosures MUST be presented in the same language and at the same
prominence as the content itself.

## 6. Signing
Manifests MUST be signed using a platform-approved key bound to a
verifiable identity. Signing keys MUST be rotated per the platform
key management policy and protected by hardware-backed key
storage where available.

## 7. Verification
Downstream services MUST verify provenance manifests before
relying on AI-generated content for consequential actions.
Verification failures MUST be logged and surfaced to the AI
governance reviewer.

## 8. Retention
Provenance manifests MUST be retained for at least 24 months and
MUST be available for audit and incident response.

## 9. Roles and responsibilities
The AI service owner is accountable for manifest generation and
signing. The platform security team owns signing key management.
The legal team owns alignment with applicable transparency
regulation.

## 10. Exception handling
Any exception to provenance requirements MUST be approved by the AI
governance body and recorded in the AI exception register.

## 11. Audit and evidence
Manifests, signing logs, and verification logs MUST be retained
according to the platform audit retention schedule.

## 12. Change management
Material changes to the provenance schema or signing identity MUST
follow the platform change management procedure and be communicated
to downstream consumers.

## 13. Review cycle
This standard is reviewed at least annually or when material changes
occur in upstream C2PA guidance, applicable transparency regulation,
or platform practice.

---

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
