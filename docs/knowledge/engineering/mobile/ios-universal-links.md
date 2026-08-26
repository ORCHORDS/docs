# ios-universal-links

**Issue:** Configuring iOS Universal Links to open your app from HTTPS URLs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Universal Links let HTTPS URLs open your app directly instead of Safari. They are more secure than custom URI schemes because they require server-side verification, preventing link hijacking.

## Pattern / Solution
**Step 1 — Apple App Site Association (AASA):**
Host at `https://example.com/.well-known/apple-app-site-association` (no redirect, no extension):
```json
{
  "applinks": {
    "details": [
      {
        "appIDs": ["TEAMID.com.example.myapp"],
        "components": [
          { "/": "/product/*", "comment": "Product pages" },
          { "/": "/user/*" },
          { "/": "/reset-password", "?": { "token": "?*" } }
        ]
      }
    ]
  }
}
```

**Step 2 — Xcode entitlement:**
In `MyApp.entitlements`:
```xml
<key>com.apple.developer.associated-domains</key>
<array>
    <string>applinks:example.com</string>
    <string>applinks:www.example.com</string>
</array>
```

**Step 3 — Handle in AppDelegate:**
```swift
func application(_ application: UIApplication, continue userActivity: NSUserActivity,
                 restorationHandler: @escaping ([UIUserActivityRestoring]?) -> Void) -> Bool {
    guard userActivity.activityType == NSUserActivityTypeBrowsingWeb,
          let url = userActivity.webpageURL else { return false }
    return DeepLinkRouter.handle(url)
}
```

**Expo config:**
```json
{
  "expo": {
    "ios": {
      "associatedDomains": ["applinks:example.com"]
    }
  }
}
```

## Gotchas
- AASA is fetched by Apple's CDN at install time (not at runtime); changes can take hours to propagate without a reinstall
- The file must be served with `Content-Type: application/json` and return HTTP 200 (no redirect)
- Universal Links only activate when tapping links in Safari, Mail, Messages — not from within apps using `openURL`
- If the app is not installed, the link falls through to Safari — handle this gracefully with a web fallback
- `applinks:` domain entitlement requires a paid Apple Developer membership
- Test with `xcrun simctl openurl booted 'https://example.com/product/42'`

## Related
- `react-native-deep-linking.md`
- `android-deep-linking-intents.md`
- `mobile-deep-link-hijacking.md`
