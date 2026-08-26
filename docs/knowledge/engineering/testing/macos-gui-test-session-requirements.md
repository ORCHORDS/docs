# macOS GUI test session requirements

**Issue**

A headless service runner can execute command-line tests but UI automation may require an active graphical login session, Accessibility permissions, Screen Recording permission, or unlocked keychain state.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Route GUI tests to a dedicated runner class with an explicitly managed console session.
- Grant only required privacy permissions through managed configuration and document the exact test binary identity.
- Keep unit and headless integration checks separate so GUI capacity does not become a reason to skip them.
- Serialize UI tests that share the desktop and restore display, locale, input, and application state.

## Verification

1. Reboot with and without console login and assert the GUI lane fails closed when prerequisites are absent.
2. Test permission revocation, screen lock, resolution changes, dialogs, and crash recovery.
3. Preserve screenshots and logs while redacting user data.

## Gotchas

- SSH access does not create an Aqua session.
- Privacy permissions are tied to code identity and can change after rebuilding tools.
- A permanently logged-in runner increases physical and remote exposure.

## Official sources

- [Apple UI testing with XCTest](https://developer.apple.com/documentation/xctest/user_interface_tests)
- [GitHub self-hosted runners](https://docs.github.com/en/actions/reference/runners/self-hosted-runners)
