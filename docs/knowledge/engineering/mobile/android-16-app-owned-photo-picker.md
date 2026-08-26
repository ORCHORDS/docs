# Android 16 app-owned media in selected-photo access

**Date:** 2026-08-26
**Status:** documented
**Source:** https://developer.android.com/about/versions/16/behavior-changes-16

## Context

On Android 16 for apps targeting SDK 36 or higher, the selected-photo permission flow changes how media owned by the app is presented when a user limits photo/video access.

## Current behavior

Android documents that app-owned photos can appear pre-selected in the system photo picker. The user can deselect them, which revokes the app's access to those selected items.

## Engineering implications

- Do not equate app ownership of a media item with permanent read access.
- Treat user deselection and access revocation as ordinary states.
- Re-query permission/access state before opening previously available media.
- Keep UI resilient when an item becomes unavailable.
- Avoid caching a stale authorization decision as if it were durable consent.

## Verification

On an API 36 device/emulator:

1. Create/import media owned by the app.
2. Trigger limited photo/video access.
3. Confirm app-owned items appear as Android specifies.
4. Deselect an owned item.
5. Verify subsequent reads fail safely and the UI explains/recover from the missing access without exposing stale content.

## Related

- `android-photo-picker.md`
- `android-runtime-permissions.md`
