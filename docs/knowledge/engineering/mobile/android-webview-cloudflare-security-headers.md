# Android WebView and Cloudflare Security Headers

**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

The example project Android app embeds a WebView for in-app
content. Pages proxied through Cloudflare load fine in
Chrome but fail in the embedded WebView with blank screens,
mixed-content errors, or JavaScript console errors about
CSP violations. On older devices (Android 7–8), the
WebView silently ignores HSTS headers and allows downgrade
attacks. The app crashes when pinning to Cloudflare's TLS
certificate because Cloudflare rotates leaf certificates
frequently. On Android 14+ the WebView enforces X-Frame-
Options more strictly, breaking legacy iframe flows.

## Context

Android WebView is a separate APK shipped by Google Play
Services (Android System WebView). Its version is
decoupled from the OS version, meaning a device running
Android 10 may have a WebView at Chromium version 90 or
at 124 depending on when Play Services last updated.
Cloudflare's security headers — CSP, HSTS, X-Frame-Options,
Permissions-Policy — are evaluated by the WebView's
Chromium renderer. Behaviours differ across WebView
versions, making fragmentation the central challenge.

---

## 1. WebView Version Fragmentation

```
┌────────────────────────────────────────────────────────────┐
│ Android OS  │ Min WebView Chromium │ Key security changes   │
│─────────────│──────────────────────│────────────────────────│
│ 7.0 (N)     │ ~55                  │ SameSite=None ignored  │
│ 8.0 (O)     │ ~62                  │ HSTS partial support   │
│ 9.0 (P)     │ ~69                  │ Cleartext blocked      │
│ 10 (Q)      │ ~78                  │ SameSite enforced      │
│ 11 (R)      │ ~87                  │ CSP level 3 partial    │
│ 12 (S)      │ ~97                  │ CSP level 3 full       │
│ 13 (T)      │ ~108                 │ Permissions-Policy     │
│ 14 (U)      │ ~119                 │ X-Frame-Options strict │
│ 15+ (V)     │ ~128+                │ Third-party cookie blk │
└────────────────────────────────────────────────────────────┘
```

Always test on a physical Android 9 device (lowest
supported by example project) and the latest Android emulator.

---

## 2. Content Security Policy in Embedded WebViews

Cloudflare's Page Shield and Zaraz inject inline scripts.
If your Cloudflare zone has a strict `script-src` CSP,
Page Shield's runtime will be blocked in the WebView.

Configure CSP to allow Cloudflare's script hashes rather
than `unsafe-inline`. In the Cloudflare dashboard under
Page Shield → Settings, copy the nonce or hash values:

```
Content-Security-Policy:
  default-src 'self';
  script-src 'self'
    'sha256-<page-shield-hash>'
    https://challenges.cloudflare.com
    https://static.cloudflareinsights.com;
  frame-src 'self'
    https://challenges.cloudflare.com;
  connect-src 'self'
    https://cloudflareinsights.com;
```

In the WebView, you can intercept requests and strip or
modify headers for debugging:

```kotlin
// WASPWebViewClient.kt

class WASPWebViewClient : WebViewClient() {

  override fun shouldInterceptRequest(
    view: WebView,
    request: WebResourceRequest
  ): WebResourceResponse? {
    // Log CSP violations in debug builds
    if (BuildConfig.DEBUG) {
      Log.d("WebView", "→ ${request.url}")
    }
    return super.shouldInterceptRequest(view, request)
  }

  override fun onReceivedHttpError(
    view: WebView,
    request: WebResourceRequest,
    errorResponse: WebResourceResponse
  ) {
    Log.e("WebView",
      "HTTP error ${errorResponse.statusCode} " +
      "for ${request.url}")
    super.onReceivedHttpError(view, request, errorResponse)
  }
}
```

---

## 3. HSTS Handling Differences

Cloudflare sets `Strict-Transport-Security` with a long
`max-age`. WebView behaviour by version:

```
┌──────────────────────────────────────────────────────────┐
│ Chromium / WebView │ HSTS preload │ HSTS memory persistence│
│────────────────────│──────────────│────────────────────────│
│ < 62               │ Not honoured │ Session only           │
│ 62–86              │ Partial list │ Persisted per app      │
│ 87+                │ Full list    │ Persisted per app      │
└──────────────────────────────────────────────────────────┘
```

Android WebView stores its HSTS policy per-app (in the
app's data directory), not system-wide. Clearing app data
in Settings → Apps wipes the HSTS cache. On fresh installs
the first request to each host is plain HTTP-redirected by
Cloudflare; subsequent requests skip the redirect.

Enable `geolocation` and `javascript` only after user
consent; keep `allowFileAccessFromFileURLs` false:

```kotlin
webView.settings.apply {
  javaScriptEnabled       = true
  domStorageEnabled       = true
  allowFileAccess         = false   // default true on old API
  allowContentAccess      = false
  allowFileAccessFromFileURLs = false
  mixedContentMode        =
    WebSettings.MIXED_CONTENT_NEVER_ALLOW
}
```

---

## 4. X-Frame-Options in Embedded Contexts

Cloudflare can inject `X-Frame-Options: SAMEORIGIN` on
responses. When your WebView loads a page that then iframes
another Cloudflare-proxied page:

- Android WebView ≥ Chromium 119 enforces `SAMEORIGIN`
  strictly: the embedded iframe origin must match the
  top-level frame origin.
- If the WebView is rendering `file://` or `app://` or
  an `about:blank` page as the top-level frame, then
  `SAMEORIGIN` blocks ALL iframes because the top-level
  "origin" is opaque.

Fix: load the top-level page from `https://app.example.com`
rather than a local `file://` asset, or use
`loadDataWithBaseURL`:

```kotlin
// Correct: set a real base URL so SAMEORIGIN resolves
webView.loadDataWithBaseURL(
  "https://app.example.com/",   // baseUrl
  htmlContent,
  "text/html",
  "UTF-8",
  null
)
```

---

## 5. Certificate Pinning with Cloudflare TLS

Cloudflare rotates leaf certificates frequently (often
every 3 months). Pinning the leaf certificate will break
the app when rotation occurs. Pin the intermediate CA
instead — Cloudflare uses DigiCert and Google Trust
Services intermediates, which rotate on a ~1-year cadence.

In `network_security_config.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
  <domain-config>
    <domain includeSubdomains="true">example.com</domain>
    <!-- Pin Cloudflare's DigiCert G2 intermediate -->
    <pin-set expiration="2027-08-22">
      <pin digest="SHA-256">
        r/mIkG3eEpVdm+u/ko/cwxzOMo1bk4TyHIlByibiA5E=
      </pin>
      <!-- Backup pin: Let's Encrypt ISRG Root X1 -->
      <pin digest="SHA-256">
        C5+lpZ7tcVwmwQIMcRtPbsQtWLABXhQzejna0wHFr8M=
      </pin>
    </pin-set>
  </domain-config>
</network-security-config>
```

```xml
<!-- AndroidManifest.xml -->
<application
  android:networkSecurityConfig=
    "@xml/network_security_config"
  ...>
```

Always include a backup pin. Without it, a CA rotation
will make every HTTPS request fail until the app is
updated.

---

## 6. Permissions-Policy and Camera/Mic in WebView

Cloudflare may pass through `Permissions-Policy` from your
origin response. WebView blocks camera/mic access unless
explicitly permitted via `onPermissionRequest`:

```kotlin
webView.webChromeClient = object : WebChromeClient() {
  override fun onPermissionRequest(request: PermissionRequest) {
    val allowed = arrayOf(
      PermissionRequest.RESOURCE_AUDIO_CAPTURE,
      PermissionRequest.RESOURCE_VIDEO_CAPTURE,
    )
    request.grant(
      request.resources.filter { it in allowed }.toTypedArray()
    )
  }
}
```

If the Cloudflare `Permissions-Policy` header disallows
`camera=()` or `microphone=()`, the WebView will block
permission grants regardless of the above callback. Adjust
the header via a Cloudflare Transform Rule or Workers
response rewrite.

---

## Anti-patterns

- Pinning the Cloudflare leaf certificate. Rotations
  happen without notice; the app breaks silently until
  updated.
- Setting `mixedContentMode = MIXED_CONTENT_ALWAYS_ALLOW`
  to fix CSP issues. This allows HTTP subresource loading
  and defeats HTTPS entirely.
- Disabling WebView safe browsing (`setSafeBrowsingEnabled
  (false)`) to avoid Cloudflare URL warnings. Safe browsing
  runs separately from Cloudflare; disabling it removes a
  real protection layer.
- Calling `clearCache(true)` on every resume. This wipes
  the HSTS cache, forcing a redirect on every cold load.

## Gotchas

- Android System WebView updates are independent of OS
  updates. After installing a Play Services update, the
  running WebView version changes without an app restart.
  Call `WebView.getCurrentWebViewPackage()` to log the
  version in crash reports.
- On Android 8.0 (Oreo), multiple processes can use a
  WebView simultaneously only after enabling multiprocess
  mode. Without it, only one WebView renders at a time,
  causing the second to show a blank screen.
- Cloudflare's `__cf_bm` cookie is set with `SameSite=None`
  on some zone configurations. Android WebView < Chromium
  80 ignores `SameSite=None` and treats the cookie as
  `SameSite=Strict`, blocking it on cross-origin fetches.

## Verification

```bash
# Check which CSP violations the WebView reports
# Use remote debugging via chrome://inspect
# Connect Android device via USB, enable USB debugging
# Open chrome://inspect#devices in desktop Chrome
# Select the WebView process → Console tab
# Navigate to the page; CSP violations appear as errors

# Verify security headers from a Worker
curl -si https://app.example.com/ | grep -i \
  'strict-transport\|content-security\|x-frame\|permissions'
```

## Related

- `android-network-security-config.md`
- `webview-security.md`
- `certificate-pinning.md`
- `mobile-device-fragmentation-test-matrix.md`
- `android-17-encrypted-client-hello-policy.md`

## Source URLs (verified 2026-08-22)

- https://developer.android.com/privacy-and-security/security-ssl
- https://developer.android.com/develop/ui/views/layout/webapps/webview
- https://chromium.googlesource.com/chromium/src/+/main/android_webview/docs/
- https://developers.cloudflare.com/page-shield/
- https://developer.android.com/guide/topics/manifest/network-security-config
