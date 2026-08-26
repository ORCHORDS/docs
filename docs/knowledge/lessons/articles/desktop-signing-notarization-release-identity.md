# Desktop signing and notarization must bind release identity

**Issue**

A valid signature proves a package was signed by some accepted identity; release safety also depends on the intended product identifier, entitlement set, timestamp, hardened runtime, and notarization or reputation workflow.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Pin expected Team ID, bundle identifier, Windows publisher subject/thumbprint policy, and executable names in release verification.
- Sign nested code in the required order, apply the least entitlements, and archive the exact entitlement manifest.
- Timestamp Windows signatures and verify both signature and chain under the target trust policy.
- Submit macOS artifacts for notarization, staple tickets where supported, and assess the distributed artifact with Gatekeeper tooling.
- Keep signing keys in managed signing services or protected CI identities; never place private keys in the repository.

## Verification

1. Verify a release artifact on clean, supported OS installations with no developer certificates.
2. Modify a nested binary, entitlement, timestamp, package payload, and identifier; require verification failure.
3. Test offline macOS assessment of stapled artifacts and Windows verification after certificate expiry with a valid timestamp.
4. Confirm update packages and installed binaries resolve to the same approved identity.

## Gotchas

- Ad hoc signing is not distribution signing.
- Notarization is automated malware checking, not a source-code audit.
- Repacking after signing invalidates the signature.
- Certificate rotation must preserve updater identity rules.

## Official sources

- [Apple notarizing macOS software](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)
- [Microsoft SignTool](https://learn.microsoft.com/en-us/windows-hardware/drivers/devtest/signtool)
