# ios-app-clips

**Issue:** Building lightweight iOS App Clips that launch under 15 MB from QR codes, NFC, or Safari banners
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Users are reluctant to install full apps for one-time tasks; App Clips let them use core functionality instantly without installation.

## Pattern / Solution
Add an App Clip target in Xcode:
- File > New > Target > App Clip
- Set the bundle ID to `<main-app-bundle-id>.Clip`

`AASA` file (hosted at `https://example.com/.well-known/apple-app-site-association`):
```json
{
  "appclips": {
    "apps": ["TEAMID.com.example.myapp.Clip"]
  }
}
```

Register App Clip experience in App Store Connect with the invocation URL.

App Clip entitlement (`MyAppClip.entitlements`):
```xml
<key>com.apple.developer.parent-application-identifiers</key>
<array>
  <string>$(AppIdentifierPrefix)com.example.myapp</string>
</array>
```

```swift
// Check if running as App Clip
import AppClip
import CoreLocation

class SceneDelegate: UIResponder, UIWindowSceneDelegate {
  func scene(_ scene: UIScene, continue userActivity: NSUserActivity) {
    guard let url = userActivity.webpageURL else { return }
    // Parse URL to determine which experience to show
    handleClipURL(url)
  }
}
```

## Gotchas
- App Clip binary must be under 15 MB uncompressed — strip unused assets aggressively
- App Clips cannot use push notifications, access HealthKit, or read contacts
- Transient iCloud data is available for App Clips but regular iCloud Drive is not
- Clips are automatically deleted 30 days after last use unless the user installs the full app

## Related
- `ios-widget-extension.md`
- `ios-in-app-purchase.md`
- `ios-universal-links.md`
