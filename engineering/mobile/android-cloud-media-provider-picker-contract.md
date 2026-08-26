# Android Cloud Media Provider and Photo Picker Contract

**Issue:** A cloud media integration can expose more data than the user selected, return stale collections, or disappear from the system picker when its provider contract, permissions, pagination, or latency behavior is wrong.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Expose cloud media through Android's `CloudMediaProvider` contract, protected by the system-only `MANAGE_CLOUD_MEDIA_PROVIDERS` permission. Do not create a parallel exported content API for application access.
- Require applications to enter through `MediaStore.ACTION_PICK_IMAGES`; rely on the system UI and narrow URI grants created by explicit user selection.
- Keep media and album identifiers stable and unique across collection identifiers. Return the current media collection identifier in cursor extras so the picker can invalidate stale results.
- Implement pagination with opaque page tokens and honor requested page size, MIME type, and sort filters. Report honored arguments in `ContentResolver.EXTRA_HONORED_ARGS`.
- Make every selected media item an openable stream with an accurate MIME type. Authorize each stream request independently and avoid leaking account identifiers in content URIs.
- Observe cancellation signals and bound backend work. Cache only metadata that is safe to retain and invalidate it after account removal or collection changes.
- Design zero-state suggestions for a response within roughly 300 ms; keep paged search responses within the documented three-second display window.

## Verification

1. Confirm the provider fails registration when the system-only permission is absent.
2. Test collection changes, deleted media, duplicate identifiers, pagination completion, ignored filters, cancellation, offline mode, and expired authentication.
3. Verify an app cannot query the provider directly and can read only user-selected picker URIs.
4. Trace latency percentiles separately for zero-state, search, paging, thumbnails, and original streams.

## Gotchas

- Apps consume the system picker, not `CloudMediaProvider` directly.
- A missing media collection ID invalidates a returned cursor.
- Slow responses may simply not appear, creating a silent product failure.

## Sources

- [Android CloudMediaProvider API reference](https://developer.android.com/reference/android/provider/CloudMediaProvider)
- [Android MediaStore API reference](https://developer.android.com/reference/android/provider/MediaStore)
