# ios-app-transport-security

**Issue:** ATS configuration, Info.plist requirements, Apple rejection reasons
**Date:** 2026-08-11
**Status:** documented

## Symptom
Your Capacitor app submits to the App Store. Apple rejects it with:
> "Your app uses NSAllowsArbitraryLoads, which disables App Transport
> Security. Please provide justification or fix the exception."
Or worse — it passes review but silently loads HTTP content, exposing
user tokens on unencrypted connections.

## Root cause
**App Transport Security (ATS) is enforced by default since iOS 9.**
All network connections must use TLS 1.2+ with forward secrecy.
Capacitor's default `Info.plist` from older templates sometimes
includes `NSAllowsArbitraryLoads = true` — a catch-all exception
that bypasses all ATS requirements.

**Source:** Apple — NSAppTransportSecurity:
https://developer.apple.com/documentation/bundleresources/information_property_list/nsapptransportsecurity

**Source:** Apple App Store Review Guideline 5.4 (Privacy):
https://developer.apple.com/app-store/review/guidelines/#privacy

## ATS defaults

When ATS is on (no exceptions), Apple requires:
- TLS 1.2 minimum (TLS 1.3 preferred)
- Forward secrecy cipher suites (ECDHE)
- Certificates with SHA-256 or better
- Minimum RSA key size 2048 bits / EC key size 256 bits

## Correct `Info.plist` — no exceptions

```xml
<!-- ios/App/App/Info.plist -->
<!-- ATS is ON by default when NSAppTransportSecurity is absent -->
<!-- Do NOT add NSAppTransportSecurity unless you need an exception -->

<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDisplayName</key>
  <string>example project</string>
  <key>CFBundleIdentifier</key>
  <string>app.example project</string>
  <!-- No NSAppTransportSecurity key = strict ATS on all connections -->
</dict>
</plist>
```

## Acceptable exception — specific domain for legacy service

```xml
<key>NSAppTransportSecurity</key>
<dict>
  <!-- Do NOT set NSAllowsArbitraryLoads to true -->

  <!-- Allow a specific legacy endpoint that cannot yet use TLS -->
  <key>NSExceptionDomains</key>
  <dict>
    <key>legacy.partner-api.example.com</key>
    <dict>
      <!-- Only allow HTTP for this domain, not the whole app -->
      <key>NSExceptionAllowsInsecureHTTPLoads</key>
      <true/>
      <!-- Still require TLS 1.2 for HTTPS on this domain -->
      <key>NSExceptionMinimumTLSVersion</key>
      <string>TLSv1.2</string>
      <!-- Do NOT include subdomains unless necessary -->
      <key>NSIncludesSubdomains</key>
      <false/>
    </dict>
  </dict>
</dict>
```

You must justify every `NSExceptionDomains` entry in your App Review
Notes when submitting.

## Capacitor WebView — content loaded in the WebView

Capacitor loads your web app via a local server (`capacitor://localhost`
or `ionic://localhost`). This is exempt from ATS. However, any
`fetch()` call from JavaScript to an HTTP URL is still subject to ATS.

```ts
// This will fail on iOS with ATS enabled:
const response = await fetch('http://api.example.com/data');
// Use HTTPS always:
const response = await fetch('https://api.example.com/data');
```

If you use a custom URL scheme handler, ensure it only handles HTTPS
URLs. Never register a scheme handler that downgrades to HTTP.

## Common Apple rejection reasons

| Rejection | Cause | Fix |
|---|---|---|
| "NSAllowsArbitraryLoads is true" | Catch-all ATS bypass | Remove it; use specific domain exceptions |
| "NSAllowsLocalNetworking is true without justification" | Local network access | Only include if app requires local device discovery; justify in review notes |
| "NSExceptionAllowsInsecureHTTPLoads for your own domain" | First-party HTTP | Fix your server to use HTTPS; no exception acceptable |
| "TLS 1.0 exception" | NSExceptionMinimumTLSVersion = TLSv1.0 | Upgrade to TLS 1.2; Apple rejects TLS 1.0/1.1 exceptions since 2022 |
| "No justification for media exception" | NSAllowsArbitraryLoadsForMedia | Required only for AVFoundation HTTP live streaming; cite RFC 8216 |

## ATS and Capacitor CDN resources

If your app loads fonts, images, or scripts from a CDN, those CDN
domains must also serve valid TLS. Common pitfall: a Capacitor app
bundles the web app but the web app still tries to load Google Fonts
over HTTP in a local dev build.

```ts
// capacitor.config.ts
import { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'app.example project',
  appName: 'example project',
  webDir: 'dist',
  server: {
    // Never set androidScheme: 'http' — this breaks ATS equivalent on Android too
    androidScheme: 'https',
  },
};

export default config;
```

## Auditing your Info.plist

```bash
# Check for ATS exceptions in your built app
find ios/App -name "Info.plist" -exec grep -A 20 "NSAppTransportSecurity" {} \;

# Check for HTTP URLs in your JS bundle
grep -r "http://" dist/ --include="*.js" | grep -v "localhost" | grep -v "127.0.0.1"
```

## Verification
- [ ] `Info.plist` has no `NSAllowsArbitraryLoads: true`
- [ ] Any `NSExceptionDomains` entries are documented with business justification
- [ ] JS bundle contains no non-localhost HTTP URLs
- [ ] `capacitor.config.ts` has `androidScheme: 'https'`
- [ ] App Review Notes include justification for any ATS exceptions
- [ ] Charles Proxy / Proxyman shows all app traffic as HTTPS

## Gotchas
- **Simulator does not enforce ATS** by default. Test on a physical
  device with a proxy to verify ATS is working.
- **`localhost` is always exempt** from ATS — Capacitor's local server
  is safe.
- **`NSAllowsArbitraryLoadsForMedia`** is only for `AVFoundation`
  HTTP Live Streaming (HLS). Apple rejected apps in 2023 that used it
  for general CDN access.
- **WKWebView and ATS:** WKWebView respects ATS for navigations but
  not for `loadHTMLString:` with embedded HTTP resource URLs. Always
  use HTTPS in embedded HTML.
- **Third-party SDKs** sometimes add their own ATS exceptions (old
  Firebase SDK versions, ad SDKs). Audit `Pods/*/Info.plist` after
  `pod install`.

## Related
- `certificate-pinning.md`
- `android-network-security-config.md`
- `webview-security.md`
- Apple ATS docs: https://developer.apple.com/documentation/bundleresources/information_property_list/nsapptransportsecurity
- Apple ATS technote: https://developer.apple.com/news/technotes/tn2277/
- App Store Review Guideline 5.4: https://developer.apple.com/app-store/review/guidelines/#privacy
