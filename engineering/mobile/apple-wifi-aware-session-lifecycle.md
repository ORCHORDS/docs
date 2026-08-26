# Apple Wi-Fi Aware session lifecycle

**Issue:** Wi-Fi Aware enables nearby discovery and data paths without an infrastructure network, but peers appear and disappear, permissions and capabilities vary, and identifiers must not become durable tracking keys.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** experimental

## Controls and implementation
Feature-detect platform/device support, request access in user context, and degrade to another transport. Model discovery, authentication, connection, suspension, and teardown explicitly. Authenticate the application peer above proximity discovery, encrypt sensitive payloads, rotate ephemeral identifiers, minimize advertised metadata, and bind resources to a cancellable session.

## Verification
Test denial, unsupported devices, peer churn, simultaneous peers, background/foreground, radio changes, locked device, duplicate discovery, timeout, cancellation, reconnect, and malicious advertisements. Confirm teardown closes sockets and erases ephemeral state.

## Gotchas
Physical proximity is not identity. Framework availability and entitlement requirements evolve; mark rollout experimental until verified on supported OS/device pairs.

## Sources
- Apple Developer, [Wi-Fi Aware](https://developer.apple.com/documentation/wifiaware)
- Apple Developer, [Network framework](https://developer.apple.com/documentation/network)
