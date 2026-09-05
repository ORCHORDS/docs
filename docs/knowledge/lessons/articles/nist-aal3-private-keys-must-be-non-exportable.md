# NIST AAL3 Private Keys Must Be Non-Exportable

**Issue:** A cryptographic authenticator is treated as AAL3-capable even though its private authentication key can be exported into general-purpose host storage.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

NIST SP 800-63B-4 requires the cryptographic authenticator used at AAL3 to have a non-exportable private key. NIST describes qualifying storage as a separate hardware authenticator or an embedded isolated processor or execution environment designed to prevent the host processor from extracting the authentication secret.

## Engineering rule

- Make key exportability an explicit property in authenticator inventory and assurance reviews.
- Require hardware-backed or equivalently isolated non-exportable key storage for NIST AAL3 alignment.
- Do not treat operating-system file permissions around an exportable key as equivalent to a non-exportable authenticator.
- Verify that host software cannot reprogram the authenticator to expose the protected key.

## Verification

- Inspect authenticator architecture and vendor documentation for key-export behavior.
- Attempt supported backup/export operations and confirm AAL3-designated credentials cannot expose private key material.
- Validate that the authenticator meets the framework's applicable cryptographic and hardware-protection requirements.

## Official source

- NIST SP 800-63B-4, AAL3 Authenticator and Key Requirements: https://pages.nist.gov/800-63-4/sp800-63b.html
