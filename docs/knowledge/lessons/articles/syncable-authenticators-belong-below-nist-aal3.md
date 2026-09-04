# Syncable Authenticators Belong Below NIST AAL3

**Issue:** A syncable passkey is assumed to satisfy every higher assurance level simply because it uses public-key cryptography.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

NIST SP 800-63B-4 permits syncable authenticators for applications up to AAL2 when the sync fabric and key protections meet the specified requirements. AAL3 requires a non-exportable private key, while syncable authenticators necessarily use an exportable key so it can be copied through the sync fabric. NIST therefore states that syncable authenticators SHALL NOT be used at AAL3.

## Engineering rule

- Treat syncability/exportability as part of assurance-level classification.
- Do not infer AAL3 suitability from phishing resistance alone.
- For NIST AAL3 designs, choose a cryptographic authenticator whose private key is non-exportable and hardware-protected as required by the framework.
- For AAL2 syncable authenticator deployments, review sync-fabric access protection and recovery controls as part of the authenticator threat model.

## Verification

- Determine whether the authenticator private key can be exported, cloned, backed up, or synchronized.
- Confirm AAL3 deployments reject authenticators whose key material is exportable.
- For AAL2 syncable authenticators, verify the sync fabric applies the required access protections.

## Official source

- NIST SP 800-63B-4, Syncable Authenticators: https://pages.nist.gov/800-63-4/sp800-63b.html
