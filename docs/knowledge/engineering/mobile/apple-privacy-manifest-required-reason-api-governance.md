# Apple privacy manifest and required-reason API governance

**Issue:** iOS-family apps can be rejected when required-reason API use is undeclared. The duty applies to application code and included third-party SDKs, so a one-time manifest review is insufficient.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Policy boundary

Apple requires apps that use covered required-reason APIs to declare approved reasons in a privacy manifest. The stated reason must accurately reflect the app's use and any data derived from it; it cannot be used for tracking or fingerprinting.

## Delivery controls

- Maintain an inventory of required-reason API categories used by app code and every shipped SDK version.
- Require an owner and a product justification for each declaration before release; do not copy a reason from another app or SDK.
- Keep the privacy manifest versioned with the target and review it in code review when SDKs, analytics, device APIs, or storage behavior change.
- Compare the manifest to build artifacts and SDK dependency locks during release preparation.
- Treat App Store Connect feedback as a signal to re-audit usage, not merely as a metadata task.
- Do not collect, derive, or repurpose device signals for tracking under a nominally functional reason.
- Test release and production build configurations, because conditional compilation and optional SDKs can change what ships.

## Verification checklist

1. Enumerate covered API calls in first-party code and packaged dependencies.
2. Confirm every declared reason is on Apple's approved list for its API category.
3. Confirm the released product behavior matches the reason.
4. Review privacy declarations when updating a third-party SDK.
5. Retain the review evidence with the release record.

## Sources

- [Apple — Describing use of required reason API](https://developer.apple.com/documentation/bundleresources/describing-use-of-required-reason-api)
- [Apple — Privacy manifest files](https://developer.apple.com/documentation/bundleresources/privacy-manifest-files)

## Tags

`ios` `privacy` `app-store` `sdk` `mobile`
