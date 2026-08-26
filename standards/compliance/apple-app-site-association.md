# apple-app-site-association

**Issue:** iOS Universal Links + Saved Passwords autofill won't activate without correct AASA
**Date:** 2026-08-09
**Repo:** <your-org>/<your-repo> at main (PR #assetlinks + the platform issue #open-issue-aasa)
**Author:** the platform team
**Status:** fixed (a sibling repo); the platform awaiting operator secrets

## Symptom
On iOS Safari, tapping a link to `https://the domain/post/123`
opens Safari (not the native app). Universal Links should deep-link
directly to the app. Similarly, the iOS Password Manager doesn't
offer to save passwords for `the domain` logins.

## Root cause
Universal Links and Saved Passwords autofill both require the
**Apple App Site Association** (AASA) file at:
```
https://<domain>/.well-known/apple-app-site-association
```

The AASA is a JSON file (no `.json` extension) that:
1. Declares which paths the app handles (for Universal Links)
2. Declares the team ID + bundle ID (for app verification)
3. Optionally lists the `webcredentials` service (for Saved
   Passwords autofill)

**Source:** Apple developer docs:
https://developer.apple.com/documentation/xcode/supporting-universal-links-in-your-app

> "Your server must host an `apple-app-site-association` file at
> `https://<domain>/.well-known/apple-app-site-association`."

## Fix
Two parts:

### Part 1: The AASA file
```json
{
  "applinks": {
    "apps": [],
    "details": [
      {
        "appIDs": ["<TEAM_ID>.com.orchords.the platform"],
        "components": [
          { "/": "/post/*", "comment": "Post detail" },
          { "/": "/profile/*", "comment": "User profile" },
          { "/": "/settings/*", "comment": "Settings" }
        ]
      }
    ]
  },
  "webcredentials": {
    "apps": ["<TEAM_ID>.com.orchords.the platform"]
  }
}
```

- **`<TEAM_ID>`** is the 10-character Apple Team ID. Get it from
  App Store Connect → Membership.
- **`com.orchords.the platform`** is the iOS bundle ID. Must match the
  Xcode project's `PRODUCT_BUNDLE_IDENTIFIER`.
- **`webcredentials.apps`** enables Saved Passwords autofill in
  iOS 12+.

### Part 2: Serve it from Cloudflare Pages
Place the file at:
```
apps/web/public/.well-known/apple-app-site-association
```

The Next.js static export copies `public/` to `out/`, which CF
Pages serves at the root. **NO `_redirects` line can intercept
this path** — verify with:
```bash
curl -sI https://the domain/.well-known/apple-app-site-association
# Expect: HTTP/2 200, content-type: application/json
```

### Part 3: iOS app entitlement
In Xcode, add to `Entitlements.plist`:
```xml
<key>com.apple.developer.associated-domains</key>
<array>
  <string>applinks:the domain</string>
  <string>webcredentials:the domain</string>
</array>
```

Rebuild + redeploy the iOS app. Universal Links activate after
the user installs the updated build (no server-side action).

## Verification
- **Live:** `curl -sI https://the domain/.well-known/apple-app-site-association`
  → 200 + JSON content
- **iOS device:** Open Notes app, type `the domain`, tap suggestion
  → opens native app (not Safari)
- **Saved Passwords:** Open Settings → Passwords → tap +
  → suggests the domain credentials

## Gotchas
- **NO `.json` extension.** Apple requires the literal name
  `apple-app-site-association`. Browsers will 404 if you serve
  `apple-app-site-association.json`.
- **`Content-Type` must be `application/json`** (or
  `application/octet-stream` is also accepted by some Apple tools,
  but JSON is canonical). Don't serve as `text/plain`.
- **The AASA is cached aggressively by iOS.** After updating the
  file, users may need 24h for the new version to take effect.
  Apple CDN fetches the file on app install + on every few days
  for active apps.
- **TestFlight builds use a separate bundle ID.** If you have
  `com.orchords.the platform` (App Store) and `com.orchords.the platform.preview`
  (TestFlight), you need BOTH in the AASA's `appIDs` array.
- **Android side is separate.** Android uses
  `assetlinks.json` (different file, different content).
  See: Android assetlinks.json specification.
- **The `webcredentials` service is opt-in.** Without it, iOS
  Password Manager works as a generic site (no autofill magic).

## Related
- the platform issue #open-issue-aasa (awaiting operator's Apple Team ID + bundle ID)
- a sibling repo PR #assetlinks (assetlinks + AASA)
- AASA validator: https://branch.io/resources/aasa-validator/
- Apple docs: https://developer.apple.com/documentation/xcode/supporting-universal-links-in-your-app
