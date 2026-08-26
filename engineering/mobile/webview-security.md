# webview-security-mobile

**Issue:** Capacitor WebView security — JS bridge hardening, allowNavigation, XSS via deep links
**Date:** 2026-08-11
**Status:** documented

## Symptom
A user sends a crafted deep link (`example project://open?redirect=javascript:...`)
to another user. When opened, it executes arbitrary JavaScript in the
Capacitor WebView, which has access to the Capacitor JS bridge and
all native plugin APIs. The attacker can call `Filesystem.readFile()`,
exfiltrate stored session tokens, or trigger in-app purchases.

Or: your `allowNavigation` list includes a wildcard, and a phishing
page loads inside your app's WebView with full bridge access.

## Root cause
**The Capacitor JS bridge exposes native APIs to all JavaScript
running in the WebView.** If untrusted content (from a deep link
redirect, an injected ad, or a third-party iframe) can run in the
WebView, it inherits all bridge permissions. Capacitor does not
sandbox individual frames.

**Source:** Capacitor Security — allowNavigation:
https://capacitorjs.com/docs/config#allownavigation

**Source:** OWASP MASVS-PLATFORM:
https://mas.owasp.org/MASVS/controls/MASVS-PLATFORM-1/

## Capacitor config — minimum allowNavigation

```ts
// capacitor.config.ts
import { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'app.example project',
  appName: 'example project',
  webDir: 'dist',
  server: {
    androidScheme: 'https',
    // allowNavigation: []  — empty array or omit entirely
    // Never: allowNavigation: ['*'] or ['*.example.com']
    // Only add specific URLs if you need external content in the WebView
  },
  plugins: {
    CapacitorHttp: {
      enabled: true,  // Use native HTTP stack (avoids CORS, respects ATS)
    },
  },
};

export default config;
```

When `allowNavigation` is empty or not set, the WebView only loads
content from your app's bundle (`capacitor://localhost`). Any
navigation to an external URL opens the system browser, not the
WebView — keeping the Capacitor bridge out of reach.

## Deep link validation — sanitise before navigation

```ts
// src/deeplinks/handler.ts
import { App, URLOpenListenerEvent } from '@capacitor/app';

const ALLOWED_PATHS = new Set([
  '/profile',
  '/content',
  '/creator',
  '/settings',
]);

function sanitiseDeepLink(url: string): string | null {
  try {
    const parsed = new URL(url);
    // Only accept example project:// scheme — reject http/https/javascript
    if (parsed.protocol !== 'example project:') return null;

    const path = '/' + parsed.hostname + parsed.pathname;

    // Whitelist-only navigation
    if (!ALLOWED_PATHS.has(path) && !path.startsWith('/content/')) {
      console.warn('[DeepLink] Rejected unknown path:', path);
      return null;
    }

    // Strip query parameters that could carry XSS payloads
    // Only allow known safe params
    const safeParams = new URLSearchParams();
    const allowed = ['id', 'tab', 'ref'];
    for (const key of allowed) {
      const val = parsed.searchParams.get(key);
      if (val && /^[a-zA-Z0-9_-]{1,64}$/.test(val)) {
        safeParams.set(key, val);
      }
    }

    return `${path}?${safeParams.toString()}`;
  } catch {
    return null;
  }
}

export function registerDeepLinkHandler(navigate: (path: string) => void) {
  App.addListener('appUrlOpen', (event: URLOpenListenerEvent) => {
    const safePath = sanitiseDeepLink(event.url);
    if (safePath) {
      navigate(safePath);
    } else {
      console.warn('[DeepLink] Blocked potentially malicious URL:', event.url);
    }
  });
}
```

## Content Security Policy (CSP) in the WebView

Set a strict CSP in your web app's `index.html`. Even though the
WebView isn't a browser, Capacitor respects CSP headers for
`script-src`, `object-src`, etc.

```html
<!-- dist/index.html (your Vite/React build output) -->
<meta http-equiv="Content-Security-Policy" content="
  default-src 'self' capacitor://localhost ionic://localhost;
  script-src 'self' 'nonce-{NONCE}';
  style-src 'self' 'unsafe-inline';
  img-src 'self' data: https://cdn.example.com https://imagedelivery.net;
  media-src 'self' https://stream.example.com;
  connect-src 'self' https://api.example.com wss://ws.example.com;
  frame-src 'none';
  object-src 'none';
  base-uri 'self';
">
```

Key points:
- `frame-src 'none'` — no iframes (prevents clickjacking and third-party
  frame content from accessing the bridge)
- `object-src 'none'` — no Flash/plugins
- `connect-src` whitelist — only your own API and WebSocket
- No `unsafe-eval` — Capacitor does not require it

## JavaScript bridge — plugin permission model

Capacitor plugins are available to all WebView JavaScript by default.
Audit which plugins are installed and remove unused ones:

```bash
# List installed Capacitor plugins
cat package.json | grep -E '"@capacitor'
```

For sensitive plugins (Filesystem, Camera, Contacts), add a runtime
permission check before exposing the feature in the UI:

```ts
// src/permissions/runtimeCheck.ts
import { Camera } from '@capacitor/camera';
import { Filesystem } from '@capacitor/filesystem';

export async function checkPermissionsBeforeUse(): Promise<void> {
  // Check camera permission only when the user initiates the camera
  const cameraStatus = await Camera.checkPermissions();
  if (cameraStatus.camera !== 'granted') {
    const request = await Camera.requestPermissions({ permissions: ['camera'] });
    if (request.camera !== 'granted') {
      throw new Error('Camera permission denied');
    }
  }
}
```

Do not pre-request all permissions at app launch — Apple and Google
both penalise blanket permission requests in their reviews.

## iOS WKWebView — disabling JS bridge for external content

If you must load external URLs (e.g., a payment page), open them in
`SFSafariViewController` instead of the WebView. This is completely
isolated from the Capacitor bridge.

```ts
// src/utils/openExternal.ts
import { Browser } from '@capacitor/browser';

export async function openExternalSecurely(url: string): Promise<void> {
  // Opens in SFSafariViewController (iOS) or Chrome Custom Tab (Android)
  // Neither has access to the Capacitor bridge
  await Browser.open({
    url,
    presentationStyle: 'popover',  // iOS: sheet instead of full-screen
    toolbarColor: '#1a1a2e',
  });
}
```

Never call `window.open()` with an external URL inside the WebView —
this creates a new WebView window that still has bridge access.

## Android `setJavaScriptEnabled` and `addJavascriptInterface`

Capacitor enables JavaScript in the WebView by default (required).
If you register any custom `addJavascriptInterface` objects, annotate
every exposed method with `@JavascriptInterface` — unannotated methods
are not called from JavaScript on Android 4.2+ but the bridge is
still there:

```kotlin
// Only do this if you have a custom native bridge beyond Capacitor's
class CustomBridge {
  @JavascriptInterface
  fun getAppVersion(): String = BuildConfig.VERSION_NAME

  // Without @JavascriptInterface: NOT callable from JS
  // (but the object is still registered — remove it if unused)
  fun internalMethod(): Unit = Unit
}
```

## Verification
- [ ] `allowNavigation` is empty or omitted in `capacitor.config.ts`
- [ ] Deep link handler rejects `javascript:`, `data:`, `http:` URLs
- [ ] CSP meta tag is present in built `index.html`
- [ ] `frame-src 'none'` is in CSP
- [ ] External URLs open in `Browser.open()`, not `window.open()`
- [ ] Penetration test: send crafted deep link with `javascript:alert(1)` — confirm it is blocked
- [ ] `npm ls | grep capacitor` — audit installed plugins, remove unused

## Gotchas
- **Capacitor 5 removed `allowMixedContent`** (previously could allow
  HTTP + HTTPS in the same WebView). If you relied on it, upgrade to
  HTTPS-only.
- **`postMessage` from iframes** (if you allow any): without a strict
  `frame-src 'none'`, a malicious iframe can `postMessage` to the
  parent and trigger bridge calls if your app listens to unvalidated
  `message` events.
- **`window.location.href` manipulation**: an XSS payload can redirect
  the WebView to an attacker-controlled page within the same origin.
  CSP `navigate-to` (not yet universally supported) can help; more
  reliable is to validate all route changes in your router.
- **`data:` URI scheme** can execute JavaScript in some WebView
  versions even with `script-src 'self'`. Add `navigate-to` to CSP
  and test with `data:text/html,<script>alert(1)</script>`.
- **Android WebView version**: Android uses the system WebView (Chrome).
  Old devices (Android 9) have older Chrome versions with different CSP
  support. Test on API 28 emulator.

## Related
- `ios-app-transport-security.md`
- `android-network-security-config.md`
- `mobile-data-storage.md`
- Capacitor allowNavigation: https://capacitorjs.com/docs/config#allownavigation
- Capacitor Browser plugin: https://capacitorjs.com/docs/apis/browser
- OWASP MASVS-PLATFORM-1: https://mas.owasp.org/MASVS/controls/MASVS-PLATFORM-1/
- OWASP MSTG WebView: https://mas.owasp.org/MASTG/tests/android/MASVS-PLATFORM/MASTG-TEST-0005/
