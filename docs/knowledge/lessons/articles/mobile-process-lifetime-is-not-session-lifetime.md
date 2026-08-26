# Mobile Process Lifetime Is Not Session Lifetime

**Issue:** Desktop-oriented code often assumes an active process, one window, and uninterrupted timers. Mobile operating systems can background, suspend, terminate, and later relaunch an app, while modern devices may host multiple independent UI scenes.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Lesson

Model user intent and durable work independently from process memory. Lifecycle callbacks are opportunities to checkpoint and quiet work, not promises that every shutdown path will run.

## Controls

- Persist minimal recoverable state at safe transaction boundaries instead of waiting for termination.
- Make network writes idempotent and record enough state to reconcile an uncertain completion after relaunch.
- Cancel or pause nonessential timers, sensors, sockets, and tasks when a scene backgrounds.
- Schedule eligible deferred work through operating-system APIs and implement expiration or cancellation handlers.
- Distinguish app-wide state from scene/window state; do not let one scene backgrounding invalidate another active scene.
- Revalidate credentials, permissions, connectivity, server state, and stale caches on resume.
- Route deep links, notifications, and background launch events through restart-safe handlers.

## Verification

- Terminate the process after every persistence boundary and verify correct recovery.
- Background and foreground multiple scenes independently.
- Kill the app during a write whose server response is lost, then confirm idempotent reconciliation.
- Test timer delay, network change, revoked permission, expired credential, and low-memory relaunch paths.
- Assert no correctness property depends on a termination callback.

## Gotchas

Backgrounding is not the same as termination, and an inactive scene is not necessarily an inactive process. In-memory locks and “run once” flags disappear on termination. Wall-clock time can advance substantially while monotonic callbacks are suspended.

## Official sources

- [Apple UIKit scenes](https://developer.apple.com/documentation/uikit/scenes)
- [Apple: Responding to app launch](https://developer.apple.com/documentation/uikit/responding-to-the-launch-of-your-app)
- [Android activity lifecycle](https://developer.android.com/guide/components/activities/activity-lifecycle)
