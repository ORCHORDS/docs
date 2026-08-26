# Apple AlarmKit scheduling lifecycle

**Issue:** An iOS alarm feature is implemented as an ordinary local notification, without modeling alarm authorization, presentation, cancellation, and app-state lifecycle.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** newer Apple platform API; gate by OS availability

AlarmKit provides system alarm experiences for eligible app use cases. Keep a durable application schedule and reconcile it with system alarm identifiers; a successful schedule call is not permission, user acknowledgement, or business-action completion.

**Source:** [Apple AlarmKit documentation](https://developer.apple.com/documentation/alarmkit)

## Controls

- check OS/framework availability and request only documented authorization;
- use stable opaque identifiers and persist schedule intent separately;
- make create, update, cancel, and reschedule operations idempotent;
- provide localized titles/actions and accessible fallbacks;
- restrict use to genuine alarm experiences and review App Store guidance.

## Verification

Test first authorization, denial, revocation, time-zone/clock change, reboot, app update, duplicate scheduling, cancellation, action handling, and unsupported OS versions. Reconcile system state after launch without duplicating alarms.

## Gotchas

AlarmKit is distinct from UserNotifications. Delivery UI does not prove the user completed an app task. API availability and entitlement/policy requirements can change by OS release.
