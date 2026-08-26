# PRECIS Internationalized Username and Password Profiles

**Issue:** A service applies lowercase/NFKC rules to every credential string, causing false username collisions or silently changing passwords; different clients then compare internationalized credentials differently.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Adopt the profile required by the application protocol. RFC 8265 defines `UsernameCaseMapped` for case-insensitive usernames, `UsernameCasePreserved` where case is preserved under the profile's comparison rule, and `OpaqueString` for passwords and other opaque secrets. Execute preparation, enforcement, and comparison in the specified order and reject nonconforming output.

Do not reuse username mappings for passwords. OpaqueString applies NFC, does not case-map, and compares the processed values exactly. Process a password at the endpoint that performs authentication, then pass the resulting bytes to the password-hashing/KDF flow; never log either input or prepared value. Pin the PRECIS/Unicode library version and design a migration path from SASLprep or legacy normalization.

## Verification

Use RFC examples plus case variants, width variants, non-ASCII spaces, combining sequences, bidi usernames, prohibited/private-use code points, zero-length output, and legacy records. Confirm client and server produce identical prepared username bytes. For password migration, test old and new verification paths without storing plaintext, and rehash only after successful authentication.

## Gotchas

PRECIS does not decide password strength, breached-password checks, hashing parameters, or visual-confusable policy. NFKC-based SASLprep and NFC-based OpaqueString are not interchangeable. Changing a stored username key can create collisions; changing password preparation without a compatibility verifier locks users out.

## Sources

- [IETF RFC 8265 — Internationalized Usernames and Passwords](https://datatracker.ietf.org/doc/html/rfc8265)
- [IETF RFC 8264 — PRECIS Framework](https://datatracker.ietf.org/doc/html/rfc8264)
