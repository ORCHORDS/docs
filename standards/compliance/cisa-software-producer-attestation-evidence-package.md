# CISA software-producer attestation evidence package

**Issue:** Signing a secure-development attestation without scoped, current evidence can create a false assurance statement and leave the organization unable to substantiate it.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Scope

CISA and OMB released a common Secure Software Development Attestation Form for software producers serving the US federal government. Applicability, submission timing, and authorized signatory are procurement/legal determinations; this entry is an evidence workflow, not legal advice.

## Evidence package

For each attested product/version, record:

- producer legal identity and authorized signatory;
- product, version, delivery model, covered code and excluded components;
- mapped SSDF practices and implementation owners;
- protected build environment and access evidence;
- provenance, SBOM, dependency and vulnerability handling records;
- secure-development policies, tests, findings, exceptions, and remediation;
- third-party component governance;
- evidence timestamps, retention, confidentiality, and reviewer approval.

## Controls

1. Freeze the attestation scope and form revision.
2. Map every statement to primary evidence; do not rely on a narrative alone.
3. Identify inherited controls and obtain supplier evidence.
4. Time-bound gaps and exceptions; escalate statements that cannot be supported.
5. Separate submission artifacts from sensitive engineering evidence and use least-privilege access.
6. Reassess after material product/build changes or new form guidance.
7. Preserve exactly what was submitted and the approval trail.

## Verification

An independent reviewer samples each claim back to source evidence and confirms it covers the attested release. Reproduce artifact provenance and vulnerability checks from a clean context. Counsel/procurement validates applicability and wording before signature.

## Gotchas

Repository activity is not evidence of a secure process by itself. Do not upload secrets, exploitable details, classified information, or unnecessary personal data. A past attestation does not automatically cover a new product version.

## Sources

- [CISA Secure Software Development Attestation Form](https://www.cisa.gov/resources-tools/resources/secure-software-development-attestation-form)
- [NIST SP 800-218 SSDF](https://csrc.nist.gov/pubs/sp/800/218/final)
