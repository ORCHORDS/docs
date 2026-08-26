# iOS WKWebView Cookie Handling with Cloudflare Cookies

**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

The example project app embeds a WKWebView for certain in-app
flows. After a native login, the WebView session is not
authenticated — the Cloudflare-issued `__cf_bm` and
`cf_clearance` cookies are absent, forcing users to solve
a Cloudflare challenge inside the WebView. Cookie changes
made in the WebView (logout, session refresh) are not
visible to the native layer. On iOS 17+ with ITP enabled,
cookies written by the native layer to the WebView are
silently discarded within minutes.

## Context

Cloudflare sets several cookies during Bot Management and
Page Shield evaluation. The most relevant are:

- `__cf_bm` — Bot Management fingerprint (30 min, Secure,
  SameSite=None in some configs; SameSite=Lax otherwise)
- `cf_clearance` — issued after a challenge is solved
  (session-length, Secure, SameSite=Lax)

WKWebView uses a WKWebsiteDataStore that is isolated from
`URLSession`/`HTTPCookieStorage` by default. Cookies set
during native API calls are not shared with the WebView,
and vice versa, unless explicitly bridged.

---

## 1. WKWebView Cookie Architecture

```
┌─────────────────────────────────────────────────────┐
│                    iOS Process                       │
│                                                      │
│  Native Layer                WebView Layer           │
│  ┌────────────────┐          ┌─────────────────────┐ │
│  │ URLSession     │          │ WKWebView           │ │
│  │ HTTPCookie     │  ✗ (not  │ WKWebsiteDataStore  │ │
│  │ Storage        │  shared  │ WKHTTPCookieStore   │ │
│  └────────────────┘  by def) └─────────────────────┘ │
│                                                      │
│  Shared only via explicit WKHTTPCookieStore bridge   │
└─────────────────────────────────────────────────────┘
```

Each WKWebView instance can use either the default
`nonPersistent()` data store (ephemeral) or a persistent
store. Persistent stores can be shared across WebView
instances but not with URLSession.

---

## 2. Bridging Native Session Cookies into WKWebView

After a native login (the token exchange sets cookies in
HTTPCookieStorage), copy auth cookies to the WebView's
WKHTTPCookieStore before the first navigation:

```swift
// WASPWebViewController.swift

import WebKit

final class WASPWebViewController: UIViewController {

  private lazy var webView: WKWebView = {
    let config = WKWebViewConfiguration()
    // Use a non-default store so we can pre-seed it
    config.websiteDataStore = .default()
    return WKWebView(frame: .zero, configuration: config)
  }()

  func loadURL(_ url: URL) {
    copyAuthCookies { [weak self] in
      guard let self else { return }
      self.webView.load(URLRequest(url: url))
    }
  }

  private func copyAuthCookies(completion: @escaping () -> Void) {
    let jar  = HTTPCookieStorage.shared
    let store = webView.configuration.websiteDataStore
                       .httpCookieStore
    let group = DispatchGroup()

    for cookie in jar.cookies ?? [] {
      // Only bridge cookies for our domains
      guard cookie.domain.hasSuffix(".example.com") ||
            cookie.domain.hasSuffix(".cloudflare.com")
      else { continue }

      group.enter()
      store.setCookie(cookie) { group.leave() }
    }

    group.notify(queue: .main, execute: completion)
  }
}
```

---

## 3. SameSite=Lax Behaviour in WKWebView

Cloudflare sets `cf_clearance` with `SameSite=Lax`.
Inside a WKWebView initiated from native code, the
navigational context is treated as a "top-level
cross-site navigation" only when the WebView performs an
actual page load. Cookie rules:

```
┌───────────────────────────────────────────────────────────┐
│ Request type          │ SameSite=Lax sent? │ Note         │
│───────────────────────│────────────────────│──────────────│
│ Top-level navigation  │ Yes                │ Normal nav   │
│ Subresource (XHR/img) │ No                 │ Blocked      │
│ Iframe src            │ No                 │ Blocked      │
│ Redirect chain        │ Yes (first hop)    │ Varies       │
└───────────────────────────────────────────────────────────┘
```

If your in-app flow involves XHR from within the WebView
to the same Cloudflare-proxied origin, `cf_clearance` will
NOT be sent. The Worker will issue a new Bot Management
challenge, potentially looping.

**Fix:** ensure the WebView makes navigational requests
(full page loads) rather than SPA XHR calls when
Cloudflare Bot Management is active on the endpoint.

---

## 4. httpOnly Access Limitations

`cf_clearance` is set `httpOnly`. This means:

- JavaScript in the WebView cannot read it via
  `document.cookie`.
- `WKHTTPCookieStore` can enumerate it natively; it is
  accessible to Swift/ObjC code.
- You cannot bridge it back to the native layer via JS
  message passing — use `WKHTTPCookieStore` callbacks.

```swift
// Reading httpOnly cookies from WKWebView
webView.configuration.websiteDataStore.httpCookieStore
  .getAllCookies { cookies in
    let clearance = cookies.first {
      $0.name == "cf_clearance"
    }
    // Use clearance.value in native URLSession if needed
  }
```

---

## 5. ITP (Intelligent Tracking Prevention) in WKWebView

ITP is enabled by default in WKWebView on iOS 14.5+.
Its effect on embedded WebViews:

```
┌────────────────────────────────────────────────────────────┐
│ ITP behaviour                │ Impact on Cloudflare cookies │
│──────────────────────────────│──────────────────────────────│
│ 3rd-party cookie block       │ Blocks __cf_bm on            │
│                              │ cross-origin subresources    │
│ Storage access API required  │ JS can request via           │
│ for cross-origin JS access   │ document.requestStorageAccess│
│ Purge after 7-day inactivity │ cf_clearance cleared if user │
│                              │ doesn't revisit in 7 days    │
│ Link decoration stripping    │ Query param tokens stripped  │
└────────────────────────────────────────────────────────────┘
```

To prevent ITP from purging the `cf_clearance` cookie,
re-seed it from `HTTPCookieStorage` on every WebView
re-activation (app foreground or WebView appearance):

```swift
// AppDelegate or SceneDelegate
func sceneWillEnterForeground(_ scene: UIScene) {
  webViewController?.loadURL(currentURL)
  // copyAuthCookies is called inside loadURL before nav
}
```

---

## 6. Cookie Sharing for Native + WebView Auth

The recommended pattern for example project:

1. Perform authentication natively via URLSession.
2. Store tokens in Keychain; let Cloudflare cookies land
   in HTTPCookieStorage.
3. Before any WebView navigation, call `copyAuthCookies`
   (see §2) to pre-populate WKHTTPCookieStore.
4. After the WebView session ends, read updated cookies
   back via `getAllCookies` and sync to HTTPCookieStorage.
5. Never use `WKWebsiteDataStore.nonPersistent()` when
   Cloudflare session cookies are required — ephemeral
   stores cannot be pre-seeded with cookies.

---

## Anti-patterns

- Loading a URL in WKWebView before bridging cookies. The
  first request will lack `cf_clearance` and trigger a
  Cloudflare challenge, creating a second cookie that then
  conflicts with the bridged one.
- Using `UIWebView`. It was removed in iOS 15 and shares
  the same cookie jar as URLSession (which was its one
  advantage), but it is unavailable and App Store rejects
  any binary using it.
- Injecting cookies via JavaScript (`document.cookie = …`)
  for httpOnly cookies. This silently fails for httpOnly
  values; use `WKHTTPCookieStore.setCookie`.
- Sharing a single `WKProcessPool` across WebViews for
  unrelated users/sessions. Cookie isolation breaks and
  sessions bleed between users on the same device.

## Gotchas

- `WKHTTPCookieStore.setCookie` completion callbacks are
  dispatched on an internal queue, not the main queue.
  Wrap UI updates in `DispatchQueue.main.async`.
- Cookie domain matching in WKWebView requires an exact
  dot-prefix match. A cookie for `.example.com` will NOT
  be sent for `api.example.com` unless the domain in
  `HTTPCookie` is set to `.example.com` (leading dot).
- `SameSite=None` cookies require `Secure=true`. On the
  Cloudflare dashboard, ensure the SSL mode is "Full
  (strict)" so the secure flag is preserved.
- iOS 17 introduced stricter ITP enforcement for cookies
  set by 3rd-party scripts embedded in a first-party page.
  Cloudflare's Bot Management script (`/cdn-cgi/challenge…`)
  may be classified as 3rd-party if served from a different
  subdomain.

## Verification

```swift
// In a debug build, dump all WebView cookies after load
webView.configuration.websiteDataStore.httpCookieStore
  .getAllCookies { cookies in
    for c in cookies {
      print("[\(c.domain)] \(c.name)=\(c.value)" +
            " httpOnly=\(c.isHTTPOnly)")
    }
  }
// Expected: cf_clearance and __cf_bm visible for .example.com
```

## Related

- `ios-app-transport-security.md`
- `ios-urlsession-patterns.md`
- `webview-security.md`
- `in-app-browser-detection-escape-patterns.md`
- `mobile-auth-oauth-pkce.md`

## Source URLs (verified 2026-08-22)

- https://developer.apple.com/documentation/webkit/wkhttpcookiestore
- https://webkit.org/blog/10218/full-third-party-cookie-blocking-and-more/
- https://developers.cloudflare.com/fundamentals/reference/policies-compliances/cloudflare-cookies/
- https://developer.apple.com/documentation/webkit/wkwebsitedatastore
- https://webkit.org/blog/8311/intelligent-tracking-prevention-2-0/
