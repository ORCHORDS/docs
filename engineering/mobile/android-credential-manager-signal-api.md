# Android Credential Manager Signal API consistency

**Issue:** A relying party changes passkeys on its server but credential providers retain stale entries, causing sign-in suggestions for deleted accounts or missing newly linked credentials.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

Use Credential Manager's Signal API after authoritative server-side account or credential changes. Signals reconcile provider state; they do not create, authenticate, revoke, or prove ownership of a credential.

**Source:** [Android Credential Manager Signal API for relying parties](https://developer.android.com/identity/sign-in/credential-manager-signal-api)

## Controls

- emit unknown-credential signals only after server verification determines a presented credential ID is no longer valid;
- emit the complete accepted credential-ID set after authenticated account maintenance;
- emit current user details after a verified identifier or display-name change;
- gate calls by supported Android/Credential Manager versions and tolerate unsupported providers;
- minimize identifiers and never include private keys, challenges, session tokens, or secrets.

## Verification

- deleting a server credential eventually removes its stale suggestion without affecting valid siblings;
- an interrupted signal does not roll back the authoritative server change;
- retry behavior is bounded and idempotent;
- cross-account tests prove one user's accepted-ID set cannot update another user's provider state.

## Gotchas

- provider handling is asynchronous and may not be immediately visible.
- a successful signal call is not evidence of sign-in or account ownership.
- use the latest compatible AndroidX credentials library and recheck release notes before rollout.
