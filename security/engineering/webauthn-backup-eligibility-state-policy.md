# WebAuthn backup eligibility and state policy

**Issue:** WebAuthn authenticator data has two different backup signals. Backup Eligibility (BE) is a permanent credential property, while Backup State (BS) can change as a multi-device credential becomes backed up. Treating both as static, or treating either as proof of a particular cloud provider, breaks account policy and recovery decisions.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented — WebAuthn Level 3 Candidate Recommendation

## Controls

- Parse BE and BS from the signed authenticator data during registration and every assertion.
- Reject the invalid combination BE=0 and BS=1.
- Store the registered BE value and the most recent BS value with the credential record.
- Verify that BE never changes for an existing credential; investigate or reject an assertion that conflicts with the stored value.
- Allow BS to transition according to explicit relying-party policy and record the transition without assuming it proves compromise.
- For BE=0 single-device credentials, require another authenticator or a tested account-recovery path before removing other factors.
- Base privileged-action policy on verified user presence, user verification, risk, and account context; backup flags are additional signals, not authentication factors.
- Avoid exposing detailed authenticator backup metadata unnecessarily in logs or user analytics.

## Implementation and tests

Extract the flags only from authenticator data whose challenge, origin, RP ID hash, signature, and other ceremony checks pass. Persist BE at registration and compare it at authentication; update BS after policy evaluation.

Use WebAuthn virtual authenticators to test 00, invalid 01, 10, and 11; BS transitions 0→1 and 1→0; an attempted BE transition; multiple credentials with different states; recovery after loss of a single-device credential; and step-up policy. Verify replayed or invalidly signed authenticator data cannot alter stored flags.

## Gotchas

BE=1 means the credential is allowed to be backed up, not that it is currently backed up; BS supplies current state. Neither identifies the synchronization vendor, export mechanism, device count, or custody model. The flags are authenticator assertions protected by the ceremony signature, not independent attestation of backup-provider security.

WebAuthn Level 3 is a Candidate Recommendation as of 2026-08-18. Verify current specification status and browser/authenticator support.

## Official sources

- [W3C WebAuthn Level 3: Credential Backup State](https://www.w3.org/TR/webauthn-3/#sctn-credential-backup)
- [W3C WebAuthn Level 3: Verifying an authentication assertion](https://www.w3.org/TR/webauthn-3/#sctn-verifying-assertion)
