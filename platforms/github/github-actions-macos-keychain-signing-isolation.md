# macOS runner keychain signing isolation

**Issue**

Code-signing identities imported into a persistent login keychain can remain available to later jobs or interactive users on the same Mac.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use a per-job temporary keychain with a random non-logged secret, restricted permissions, and explicit search-list management.
- Import only the required certificate, configure key partition access narrowly, and delete the keychain in an administrator-owned completion hook.
- Restrict signing workflows to protected runner groups and trusted refs; never expose signing to fork jobs.
- Keep certificates and passwords in approved secret systems and mask diagnostic commands.

## Verification

1. Run a signing job followed by an untrusted probe and prove the identity is absent.
2. Exercise success, failure, cancellation, and runner crash cleanup.
3. Verify signatures, designated requirements, entitlements, and notarization on the produced artifact.

## Gotchas

- Deleting a certificate file does not remove an imported identity.
- The login keychain can unlock at GUI login.
- Cleanup cannot compensate for sharing a signing runner across trust boundaries.

## Official sources

- [Apple security command manual](https://keith.github.io/xcode-man-pages/security.1.html)
- [GitHub secure use](https://docs.github.com/en/actions/reference/security/secure-use)
