# npm registry-signature and provenance verification

**Issue:** Lockfile integrity alone does not prove that downloaded package metadata was signed by the expected registry or that available provenance validates.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

For registries that support it, `npm audit signatures` verifies registry ECDSA signatures and available provenance attestations for installed dependencies. Run it after a deterministic install with a pinned, current npm CLI that supports the registry's signing conventions.

## Controls and verification

- Treat missing or invalid signatures as a reviewed failure, not an automatic bypass.
- Pin registry identity and TLS trust.
- Keep dependency vulnerability audit separate from signature verification.
- Do not claim provenance exists for packages that do not publish it.
- Record npm version and registry in evidence.
- Test key rotation and restricted-network behavior.

## Sources

- [npm: Verifying registry signatures](https://docs.npmjs.com/verifying-registry-signatures/)
- [npm: Generating provenance statements](https://docs.npmjs.com/generating-provenance-statements/)
