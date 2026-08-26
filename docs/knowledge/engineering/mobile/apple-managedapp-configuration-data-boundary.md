# Apple ManagedApp configuration and data boundary

**Issue:** A managed deployment treats MDM-delivered configuration as trusted authorization or mixes managed and unmanaged account data after policy changes.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** newer Apple platform API; gate by OS and managed deployment support

Apple's ManagedApp framework exposes managed configuration and related enterprise controls. Validate configuration shape and provenance, but enforce user/account authorization at the server and reconcile when management state changes.

**Source:** [Apple ManagedApp documentation](https://developer.apple.com/documentation/managedapp)

## Controls

- schema-validate allowlisted configuration keys;
- separate configuration, secrets, identity, and authorization;
- observe updates and apply them transactionally;
- partition managed/unmanaged accounts and storage;
- handle removal/wipe requirements without deleting unrelated personal data;
- provide safe defaults for missing or malformed values.

## Verification

Test unmanaged install, enrollment, configuration update/removal, account switch, offline launch, malformed values, app update, device reassignment, and wipe. Managed policy must not grant backend access alone.

## Gotchas

Device management state can change while the app is inactive. Configuration may be visible on-device and is not a secret store. Enterprise policy and platform API availability vary.
