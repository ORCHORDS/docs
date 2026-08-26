# Apple AccessorySetupKit pairing lifecycle

**Issue:** An app scans broadly for nearby accessories and builds custom pairing UI, increasing permission friction, privacy exposure, and stale device state.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** newer Apple platform API; gate by OS and accessory support

AccessorySetupKit provides a system-mediated accessory discovery and setup flow. Keep application ownership and authorization separate from successful system pairing, and reconcile accessories through framework state rather than retaining scan data indefinitely.

**Source:** [Apple AccessorySetupKit documentation](https://developer.apple.com/documentation/accessorysetupkit)

## Controls

- declare only supported accessory descriptors and protocols;
- present the system picker from a clear user action;
- persist opaque accessory identifiers and minimal metadata;
- make add/remove/reconnect operations idempotent;
- reauthorize sensitive app operations after pairing;
- gate by OS availability with a documented fallback.

## Verification

Test no accessories, multiple similar devices, cancellation, denial, Bluetooth disabled, out-of-range loss, duplicate setup, app reinstall, device removal, and unsupported OS versions. Confirm one account cannot adopt another account's accessory through stale local state.

## Gotchas

Discovery, pairing, network membership, and application authorization are different states. Do not fingerprint nearby devices. Availability and supported accessory classes can change across OS releases.
