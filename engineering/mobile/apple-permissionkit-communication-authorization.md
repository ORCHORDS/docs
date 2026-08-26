# Apple PermissionKit communication authorization

**Issue:** PermissionKit mediates child/guardian approval for communication and other protected actions. Treating a pending request as approval or bypassing denial undermines family safety controls.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** restricted capability

## Controls and implementation

Feature-detect eligibility, request in direct user context, bind the request to the exact contact/action, and model pending, approved, denied, expired, cancelled, and unavailable states. Minimize disclosed contact metadata and provide a safe non-communication fallback.

## Verification

Test guardian denial/delay, duplicate requests, changed contact, account/family changes, offline, expiration, process death, unsupported devices, and revocation.

## Gotchas

Platform approval is scoped and time-sensitive; it is not identity proof or permanent consent.

## Sources

- Apple Developer, [PermissionKit](https://developer.apple.com/documentation/permissionkit)
