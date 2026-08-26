# Explicit local mode for cloud-dependent desktop apps

**Category:** Patterns
**Author:** ORCHORDS
**Source:** [example project architecture rules](https://github.com/example-org/example-repo)

## Problem

A desktop application may need to run when cloud configuration is absent or a cloud service is unavailable. Silent partial cloud behavior causes crashes, confusing data placement, and accidental requests to unconfigured endpoints.

## Pattern

Define a named local mode with a small, testable contract:

- Determine the mode once from validated configuration, before initializing cloud clients.
- In local mode, persist projects and user content locally and make no cloud calls.
- Guard every cloud helper, token accessor, sync task, and remote feature behind the mode boundary.
- Make each optional cloud capability fail back to a defined local behavior, or show an explicit unavailable state.
- Keep local and remote data identities distinguishable so later synchronization is deliberate rather than automatic.

## Verification

1. Launch with cloud configuration absent and verify the application remains functional.
2. Trace network activity in local mode; it must contain no cloud-service traffic.
3. Exercise every feature with an optional cloud dependency and confirm its documented fallback.
4. Re-enable configuration and verify that cloud initialization occurs only after validation.

## Failure modes

- One unguarded helper crashes startup or leaks a request to an unintended endpoint.
- Local data is misrepresented as synchronized data.
- A fallback changes user-visible behavior without communicating its limits.
