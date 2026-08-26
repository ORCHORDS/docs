# Android Embedded Photo Picker Session and URI Permissions

**Issue:** An embedded media picker improves continuity but its system-owned surface, lifecycle, and temporary URI grants can be mishandled during resize, configuration change, deselection, or process recreation.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Check device/API-extension availability before opening an embedded session and retain the standard Photo Picker fallback. Treat the embedded surface as a dedicated system-rendered region: do not overlay it, obscure disclosures, or imitate its controls.

Forward configuration, resize, expansion, and visibility changes through the session APIs. Keep selected URI state in the host model, validate MIME/count constraints again, and request revocation for deselected URIs. Copy only media the feature truly needs into app-managed storage under its retention policy; temporary read access is not permanent ownership.

Handle session closure and process death without assuming stale URI access survives. Strip location/metadata only under explicit product policy and never upload before informed user action.

## Verification

Test Android 14+ with required extension and unsupported devices; rotation, fold/unfold, multi-window resize, theme change, expand/collapse, hide/show, multi-select limits, deselection/revocation, cloud media, provider failure, process death, and accessibility. Confirm no host view draws over the picker and rejected MIME types never reach upload.

## Gotchas

The system prevents overlaying the embedded picker, so allocate layout space deliberately. URI access and content availability can change. A returned URI must still be treated as untrusted input for decoding and metadata.

## Sources

- [Android embedded Photo Picker](https://developer.android.com/blog/posts/the-embedded-photo-picker)
- [EmbeddedPhotoPickerFeatureInfo](https://developer.android.com/reference/android/widget/photopicker/EmbeddedPhotoPickerFeatureInfo)
- [Android Photo Picker](https://developer.android.com/training/data-storage/shared/photopicker)
