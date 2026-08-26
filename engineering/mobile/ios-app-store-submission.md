# ios-app-store-submission

**Issue:** Preparing and submitting an iOS app to the App Store
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
App Store submission involves provisioning profiles, code signing, binary validation, and App Store Connect metadata. One misconfigured entitlement causes rejection after an hours-long upload.

## Pattern / Solution
**Pre-submission checklist:**
1. Bump version + build number in `app.json` / Xcode
2. Confirm all required privacy usage strings in `Info.plist` (`NSCameraUsageDescription`, etc.)
3. Archive in Xcode → Product → Archive (or via EAS Build)
4. Validate archive in Xcode Organizer before upload

**EAS Submit (automated):**
```bash
eas build --platform ios --profile production
eas submit --platform ios --latest
# or non-interactively
eas submit -p ios --latest \
  --apple-id your@email.com \
  --asc-app-id 1234567890
```

**Fastlane deliver (alternative):**
```ruby
# Fastfile
lane :release do
  build_app(scheme: "MyApp", configuration: "Release")
  upload_to_app_store(
    skip_metadata: false,
    screenshots_path: "./screenshots",
    submit_for_review: true,
    automatic_release: false,
    submission_information: { add_id_info_uses_idfa: false }
  )
end
```

**Required metadata:**
- App icon: 1024×1024 PNG (no alpha channel)
- Screenshots for all required device sizes (6.7", 6.5", 5.5" minimum)
- Privacy policy URL
- App category and age rating
- Export compliance (encryption) answers

## Gotchas
- Build numbers must be monotonically increasing; you cannot reuse a build number even after rejection
- Bitcode is deprecated as of Xcode 14; remove `ENABLE_BITCODE = YES` from build settings
- TestFlight builds expire after 90 days; always archive fresh for App Store submission
- App Review can take 1–3 days; appeals take longer — submit with buffer before launch
- IDFA/ATT prompt requires `NSUserTrackingUsageDescription` and `AppTrackingTransparency` framework
- Entitlements in the provisioning profile must exactly match app entitlements; extra entitlements cause validation failure

## Related
- `react-native-expo-setup.md`
- `ios-push-notifications-apns.md`
- `react-native-over-the-air-updates.md`
