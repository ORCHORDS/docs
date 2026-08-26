# Mobile restoration rebuilds from durable intent

**Issue:** An app assumes its process, navigation stack, and view models survive interruption, then restores stale or privileged screens after process death.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Lesson

Treat every mobile process as disposable. Save the minimum user intent needed to reconstruct a safe experience, then revalidate account, authorization, server state, and resource availability during restoration.

**Sources:** [Android save UI states](https://developer.android.com/topic/libraries/architecture/saving-states) · [Apple preserving app state across launches](https://developer.apple.com/documentation/swiftui/restoring-your-app-s-state-with-swiftui)

## Apply

- separate transient view state from durable domain data;
- persist opaque object IDs and drafts, never live handles or credentials;
- version restoration payloads and discard unknown schemas;
- restore navigation only after authentication and tenant checks;
- checkpoint edits atomically and surface recovery when a draft cannot reopen;
- make deep links and restoration converge on the same validated routing path.

## Verify

Exercise OS process kill, memory pressure, reboot, app upgrade, logout on another device, deleted records, expired sessions, corrupted state, and multiple windows/scenes. Confirm restoration cannot reopen another account's data or repeat a completed mutation.

## Gotchas

Serialization is not authorization. UI restoration may occur long after the original context. Large state bundles increase failure risk and belong in durable storage, not platform snapshot payloads.
