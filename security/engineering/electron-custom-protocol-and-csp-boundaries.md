# Electron custom protocol and CSP boundaries

**Category:** Security
**Author:** ORCHORDS
**Source:** [example project architecture rules](https://github.com/example-org/example-repo)

## Problem

An Electron renderer must display local media and reach approved services without becoming a general file or network capability. Development often hides CSP mistakes because its production policy is absent.

## Practice

- Serve application-managed media through a custom protocol implemented in the main process.
- Resolve every requested path and enforce an allowlist of approved roots before reading it; never turn a renderer-supplied path into unrestricted filesystem access.
- Keep context isolation, disabled Node integration, and web security enabled. Expose only narrow IPC operations.
- Permit external navigation only through validated schemes and spawn child processes with an argument vector and no shell.
- Treat production CSP as executable access control: add each new image, media, API, WebSocket, or fetch origin to the relevant directive in the same change.
- Verify a packaged build, not only development mode, because a missing allowlist entry can fail silently after release.

## Verification

1. Attempt protocol access to an allowed media file and to a sibling path outside the allowed root; the second request must fail.
2. Attempt an IPC call or URL scheme outside the declared contract; it must be rejected.
3. Run a packaged build and exercise every newly introduced network host.
4. Review CSP changes alongside the feature that requires them.

## Failure modes

- A broad file URL or path traversal bypasses renderer isolation.
- A CSP wildcard conceals a new third-party dependency.
- A development-only check ships a feature that cannot reach its service in production.
