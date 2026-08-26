# Android 17 Local Network Permission Migration

**Issue:** An app discovers or connects to LAN devices without an explicit permission strategy, so targeting Android 17 breaks casting, pairing, printer, or smart-device flows—or prompts users before they understand why.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Control pattern

For apps targeting Android 17/API 37 or higher, inventory every local-network path and choose between a system-mediated privacy-preserving device picker and the `ACCESS_LOCAL_NETWORK` runtime permission. Prefer a picker when the user selects one device; request broad LAN access only at a user-initiated feature boundary with a clear rationale.

Model denied, not-yet-asked, granted, and policy-restricted states. Do not infer LAN permission from Internet access. Minimize discovery duration and retained device identifiers, and stop scans when the owning screen/process is no longer active. Keep compatibility behavior explicit for older targets and versions.

## Verification

Test first request, denial, don't-ask-again/policy restriction, existing NEARBY_DEVICES grants, picker path, upgrade from Android 16 opt-in behavior, target-SDK change, IPv4/IPv6, mDNS/SSDP/direct sockets, VPNs, guest Wi-Fi isolation, work profiles, and lost permission during a session. Verify unrelated Internet traffic remains functional.

## Gotchas

The requirement is tied to target SDK and Android version. A nearby-device group grant can change whether a prompt appears, so UI must not assume it. A system picker grants a narrower workflow than unrestricted background discovery. Never instruct users to disable network protections as a workaround.

## Sources

- [Android 17 behavior changes — local network permission](https://developer.android.com/about/versions/17/behavior-changes-17)
- [Android local network permission guidance](https://developer.android.com/privacy-and-security/local-network-permission)
