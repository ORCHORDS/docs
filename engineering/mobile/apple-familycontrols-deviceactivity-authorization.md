# Apple FamilyControls and DeviceActivity authorization lifecycle

**Issue:** A Screen Time feature treats entitlement approval, user authorization, and monitoring registration as one permanent permission. Monitoring silently stops, an extension cannot access expected selections, or a UI claims restrictions are active when the system rejected authorization.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Three separate gates

Model these states independently:

1. **Entitlement/distribution eligibility:** the app and relevant extensions are signed with approved Family Controls capabilities and provisioning.
2. **Runtime authorization:** the system's FamilyControls authorization flow has granted the mode the app requests.
3. **DeviceActivity configuration:** monitoring intervals/events were successfully registered and remain observable.

Possessing an entitlement does not grant user authorization. A successful authorization request does not prove a monitor started. The DeviceActivity API exposes an unauthorized monitoring error that must become an explicit product state.

## State machine

1. Read current authorization status when the feature screen becomes active and after the app returns to foreground.
2. Request authorization only from a clear user action with pre-prompt explanation. Handle cancellation, denial, restriction, and thrown errors without repeated prompting.
3. Store opaque system selection tokens only in appropriately protected app/group storage required by the app and extensions. Do not log or analytics-encode the selected applications/categories/domains.
4. Before starting monitoring, validate interval/event configuration and call the system API. Persist the desired configuration separately from confirmed active state.
5. Treat `unauthorized` and other monitoring errors as recoverable transitions. Stop claiming enforcement, explain the next valid action, and reconcile desired versus registered schedules.
6. App and report/monitor extensions must share the necessary entitlement and group configuration deliberately. Never assume the containing app's authorization object is an extension IPC channel.
7. On sign-out, feature disable, or policy removal, stop owned monitoring and clear application-owned sensitive selection state.
8. Keep server-side subscriptions or parental-account roles separate from the device's Screen Time authorization.

## Scheduling and UX

Device activity intervals are system scheduling requests, not hard real-time timers. Make the UI tolerant of delayed callbacks and device conditions. Use unique, versioned monitoring names so an updated schedule can replace the intended registration without deleting another feature's work.

Provide an “actual status” screen showing entitlement build state (for diagnostics), authorization, desired schedule, last successful registration, last callback, and bounded error code. Do not present monitoring as tamper-proof enforcement beyond Apple's documented guarantees.

## Verification

Test first request, cancel, deny, grant, changed/revoked authorization, unauthorized start, overlapping/invalid schedules, device reboot, app update, timezone/daylight changes, extension launch without the app, account switch, and deletion/recreation of monitoring. Validate on signed devices and distribution-like provisioning, not only simulator builds.

## Gotchas

- A permission prompt is not an appropriate background retry mechanism.
- Monitoring names and selected tokens can be sensitive metadata.
- Extension callbacks have constrained runtime; make work idempotent and bounded.
- Availability and authorization modes vary by platform/OS version; gate them explicitly.

## Sources

- [Apple — Requesting the Family Controls entitlement](https://developer.apple.com/documentation/FamilyControls/requesting-the-family-controls-entitlement)
- [Apple — DeviceActivityCenter.MonitoringError.unauthorized](https://developer.apple.com/documentation/deviceactivity/deviceactivitycenter/monitoringerror/unauthorized)
- [Apple — FamilyControls errors](https://developer.apple.com/documentation/familycontrols/familycontrolserror)
