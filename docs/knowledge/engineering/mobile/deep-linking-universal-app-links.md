# Deep Linking — Universal Links and App Links

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Links shared on social media, in emails, or in messages open your
website in a browser instead of your installed app. Users who click a
product link must navigate from the home screen instead of landing
directly on the product page. Your marketing team cannot track which
campaigns drive app opens versus web visits. Users who do not have the
app installed see a broken experience or a generic app store page
instead of the content they expected.

## Context

Deep linking routes users directly to specific content inside a mobile
app using a URL. In 2026, three mechanisms coexist: Custom URI Schemes
(legacy, e.g., `myapp://product/123`), Universal Links (iOS, Apple),
and App Links (Android, Google). Universal Links and App Links are the
modern standard — they use HTTPS URLs that work both as web links and
app entry points, with the OS verifying domain ownership to prevent
hijacking. Apps with proper deep linking report 3-5x higher conversion
from external clicks compared to generic home screen opens.

## Deep linking types

| Type | Mechanism | App required | Fallback |
|---|---|---|---|
| **Custom URI Scheme** | `myapp://path` | Yes | Error or nothing |
| **Universal Links** (iOS) | Standard HTTPS URL | If installed | Opens in browser |
| **App Links** (Android) | Standard HTTPS URL | If installed | Opens in browser |
| **Deferred deep linking** | Third-party SDK | No (installs first) | App Store → content after install |

## Universal Links (iOS)

### apple-app-site-association (AASA)

Host a JSON file at `https://example.com/.well-known/apple-app-site-association`:

```json
{
  "applinks": {
    "details": [
      {
        "appIDs": ["TEAMID.com.example.app"],
        "components": [
          { "/": "/products/*", "comment": "Product pages" },
          { "/": "/orders/*", "comment": "Order pages" },
          { "/": "/account/*", "exclude": true, "comment": "Keep in browser" }
        ]
      }
    ]
  }
}
```

### Requirements

| Requirement | Detail |
|---|---|
| HTTPS | Domain must serve over HTTPS |
| Content-Type | `application/json` (no redirects) |
| Signing | File is verified by Apple's CDN |
| Associated Domains | App must declare `applinks:example.com` in entitlements |
| No redirects | AASA file must be served directly (no 301/302) |

### iOS handling

```swift
// SceneDelegate or AppDelegate
func scene(_ scene: UIScene, continue userActivity: NSUserActivity) {
    guard userActivity.activityType == NSUserActivityTypeBrowsingWeb,
          let url = userActivity.webpageURL else { return }

    // Route to the correct screen based on URL path
    let path = url.pathComponents
    if path.contains("products"), let id = path.last {
        navigator.navigate(to: .product(id: id))
    }
}
```

## App Links (Android)

### Digital Asset Links

Host a JSON file at `https://example.com/.well-known/assetlinks.json`:

```json
[{
  "relation": ["delegate_permission/common.handle_all_urls"],
  "target": {
    "namespace": "android_app",
    "package_name": "com.example.app",
    "sha256_cert_fingerprints": [
      "AB:CD:EF:12:34:56:78:90:..."
    ]
  }
}]
```

### AndroidManifest.xml

```xml
<activity android:name=".DeepLinkActivity"
    android:exported="true">
    <intent-filter android:autoVerify="true">
        <action android:name="android.intent.action.VIEW" />
        <category android:name="android.intent.category.DEFAULT" />
        <category android:name="android.intent.category.BROWSABLE" />
        <data android:scheme="https"
              android:host="example.com"
              android:pathPrefix="/products" />
    </intent-filter>
</activity>
```

### Android handling

```kotlin
override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    val uri = intent.data ?: return
    when {
        uri.pathSegments.contains("products") -> {
            val productId = uri.lastPathSegment
            navigateToProduct(productId)
        }
    }
}
```

## Deferred deep linking

Handles the case where the user does not have the app installed:

```
1. User clicks link → App not installed
2. Redirect to App Store / Play Store
3. User installs and opens app
4. App retrieves the original deep link
5. User lands on the intended content
```

Deferred deep linking requires a third-party service (Branch, AppsFlyer,
Adjust, Firebase Dynamic Links) or custom implementation using clipboard,
IP fingerprinting, or server-side matching.

## Testing deep links

```bash
# iOS Simulator
xcrun simctl openurl booted "https://example.com/products/123"

# Android Emulator / Device
adb shell am start -a android.intent.action.VIEW \
  -d "https://example.com/products/123"

# Validate AASA file
curl -s https://example.com/.well-known/apple-app-site-association | jq .

# Validate assetlinks.json
curl -s https://example.com/.well-known/assetlinks.json | jq .

# Google Digital Asset Links API
# https://digitalassetlinks.googleapis.com/v1/statements:list?source.web.site=https://example.com
```

## Anti-patterns

- **Custom URI schemes as primary mechanism** — `myapp://` schemes have
  no fallback when the app is not installed (shows an error), cannot be
  verified by the OS (any app can claim the scheme), and do not work in
  all contexts (some apps strip custom schemes).
- **No web fallback** — deep links that only work when the app is
  installed leave users with no content when the app is absent.
  Universal Links and App Links fall back to the browser automatically.
- **Redirects in the AASA/assetlinks path** — Apple and Android verify
  the association file without following redirects. A CDN or server
  redirect (301/302) causes verification to fail silently.
- **Not testing across OS versions** — deep linking behavior differs
  between OS versions. iOS 14 changed AASA delivery to use Apple's CDN
  cache. Android 12 changed App Links verification timing.

## Gotchas

- **Apple CDN caching** — iOS downloads AASA files through Apple's CDN,
  which caches aggressively. Updates to the AASA file may take 24-48
  hours to propagate. During development, use the developer mode
  alternate AASA endpoint.
- **App Links domain verification** — Android verifies App Links domains
  at install time. If verification fails (server down, certificate
  mismatch), the app silently falls back to a disambiguation dialog
  instead of opening directly.
- **Social media in-app browsers** — Facebook, Instagram, Twitter, and
  LinkedIn open links in their in-app browsers, which may not trigger
  Universal Links. Users must tap "Open in Safari" or the system
  browser for deep linking to work.
- **Multiple apps on the same domain** — if two apps claim the same
  domain paths, the OS may show a disambiguation dialog or prefer one
  app. Use distinct path prefixes per app.

## Verification

- AASA file is accessible at `/.well-known/apple-app-site-association`
  with no redirects.
- assetlinks.json is accessible at `/.well-known/assetlinks.json`.
- Deep links open the correct screen in both iOS and Android apps.
- Web fallback works when the app is not installed.
- Deep linking is tested from email, SMS, social media, and QR codes.
- Deferred deep linking preserves context through install flow.

## Related

- `documentation/docs/policies/mobile/ios-android-security.md`
- `documentation/docs/policies/mobile/react-native-expo-patterns.md`
- `documentation/docs/policies/frontend/spa-routing-patterns.md`

## Source URLs (verified 2026-08-16)

- Deep linking 2026 guide — https://adapty.io/blog/app-deep-linking/
- Universal Links & deep links 2026 — https://blog.prototyp.digital/universal-links-deep-linking-2026/
- App Links vs Universal Links comparison — https://app.smler.io/blogs/deep-linking/app-links-vs-universal-links-technical-comparison-guide-2026
- iOS deep linking production guide — https://blog.stackademic.com/mastering-deep-linking-in-ios-swift-2026-the-complete-production-guide-to-universal-links-url-8b9a88f0d569
