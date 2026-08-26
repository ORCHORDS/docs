# Single-instance locks do not authenticate deep links

**Issue**

A desktop single-instance facility can route a second launch to the primary process, but forwarded command lines, URLs, and file paths remain untrusted external input.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Acquire the single-instance lock before creating windows or mutating shared state.
- Register associations through supported OS APIs and allowlist schemes, hosts, actions, and parameter sizes.
- Parse forwarded arguments structurally; canonicalize paths and require approval for privileged actions.
- Queue requests until initialization completes, then process them serially and idempotently.
- Never expose secrets in command lines, URLs, or logs.

## Verification

1. Launch simultaneous instances with malformed URLs, files, oversized values, and conflicting profiles.
2. Test cold-start and warm routing on every packaging target.
3. Attempt traversal, network paths, shell metacharacters, duplicates, and crash replay.
4. Verify upgrades and uninstall do not leave unsafe stale registrations.

## Gotchas

- Lock scope follows the application data scope and can change with profiles.
- Registration behavior differs between packaged builds and development.
- Second-instance payloads are attacker-controlled.
- Window focus does not prove request completion.

## Official sources

- [Electron requestSingleInstanceLock](https://www.electronjs.org/docs/latest/api/app#apprequestsingleinstancelockadditionaldata)
- [Electron protocol handling](https://www.electronjs.org/docs/latest/tutorial/launch-app-from-url-in-another-app)
