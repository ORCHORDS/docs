# Identomat KYC Mobile WebView Integration

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Mobile users reach the age-verification step. The Identomat
iframe renders but the camera never activates. On iOS the flow
works in Safari but silently fails inside the Instagram,
Facebook, or TikTok in-app browser. The `window.postMessage`
callback from the Identomat SDK never arrives at the parent page.

## Context

example project is a 21+ anonymous social platform. Every user must
clear Identomat biometric KYC (liveness detection + government-
ID OCR) before accessing any content. Failure violates US state
age-verification laws (LA R.S. 14:91.14, UT HB 311, VA HB
2485). The gate must work on all realistic mobile entry paths,
including social-media link clicks that open inside IABs.

## 1. getUserMedia Support: Mobile Browsers vs WebViews

`navigator.mediaDevices.getUserMedia()` is the modern camera
API. The legacy `navigator.getUserMedia()` is deprecated.

| Surface                     | Camera access          |
|-----------------------------|------------------------|
| Safari on iOS 14.3+         | Yes — HTTPS required   |
| Chrome / Firefox — Android  | Yes — HTTPS required   |
| WKWebView (native-owned)    | Partial — iOS 15+ only |
| Chrome / Firefox on iOS     | No — WKWebView wrapper |
| Instagram / TikTok / FB IAB | No                     |

Apple requires all third-party iOS browsers to use WKWebView.
WKWebView disables `getUserMedia` unless the host native app
implements `WKUIDelegate.requestMediaCapturePermission`. Social
IABs do not expose that delegate to arbitrary web pages. Guard
before mounting: `if (!navigator.mediaDevices?.getUserMedia) {
  showOpenInSafariBanner(); return; }`

## 2. iOS In-App Browser: Escape to Safari

When a user taps a example project link inside Instagram or TikTok,
the page loads in a WKWebView IAB. The Identomat iframe cannot
obtain camera access there. Detect the IAB and surface a clear
message before mounting — silent failure causes abandonment.

```ts
const isInAppBrowser = (): boolean =>
  /FBAN|FBAV|Instagram|TikTok|Snapchat|Twitter/i
    .test(navigator.userAgent);
const isIOS = (): boolean =>
  /iPad|iPhone|iPod/.test(navigator.userAgent);

if (isIOS() && isInAppBrowser()) {
  showBanner(
    'Camera access is unavailable here. ' +
    'Open this link in Safari to verify your age.',
    { copyUrl: window.location.href }
  );
  return; // Do not mount the Identomat iframe
}
```

`SFSafariViewController` has camera access but blocks
`window.opener`, which breaks postMessage-based callbacks.
Real Safari is the only fully compatible iOS target.

## 3. HTTPS and Permissions-Policy Camera Header

`navigator.mediaDevices` is `undefined` on plain HTTP — the
Identomat SDK throws a `TypeError` with no camera-specific
message. All KYC pages must be served over HTTPS.

`Permissions-Policy` controls which iframe origins may request
camera. A common misconfiguration blocks all sub-frames:

```
# WRONG — disables camera in the Identomat iframe
Permissions-Policy: camera=()

# CORRECT
Permissions-Policy: camera=(self "https://go.identomat.com")
```

The iframe element also needs `allow="camera"` — the header
alone is not sufficient. Omitting `allow-modals` from
`sandbox` silently suppresses the camera permission dialog.

```html
<iframe src="https://go.identomat.com/..."
  allow="camera; microphone"
  sandbox="allow-scripts allow-forms allow-same-origin
           allow-popups allow-modals"></iframe>
```

## 4. Content-Security-Policy frame-src

A strict `default-src 'self'` CSP blocks the Identomat iframe
before camera access is attempted. Required additions:

```
Content-Security-Policy:
  default-src 'self';
  frame-src   'self' https://go.identomat.com
                     https://cdn.identomat.com;
  connect-src 'self' https://*.identomat.com;
  media-src   'self' blob:;
  img-src     'self' data: blob:;
```

`connect-src` is routinely omitted. The parent page's CSP
governs outbound fetch from inside the iframe; missing it
blocks liveness uploads even when the iframe itself renders.

## 5. Cloudflare WAF and postMessage Callback

**WAF.** The Identomat SDK POSTs large JSON payloads with
Base64-encoded image frames during liveness capture. Cloudflare
managed rules (SQLI/XSS heuristics, OWASP paranoia level 2+)
can block or challenge these. Diagnose in Security Events;
fix with a skip rule scoped to the KYC API path only:

```
# WAF → Custom Rules → Skip
Expression: (http.request.uri.path wildcard "/api/kyc/*")
Action: Skip → All managed rules
```

Add `data-cfasync="false"` to the Identomat `<script>` tag
to prevent Rocket Loader from deferring it.

**postMessage callback.** Identomat signals completion via
`window.postMessage` from the iframe. IABs silently drop it.
Always pair the listener with a server-poll fallback:

```ts
window.addEventListener('message', (e: MessageEvent) => {
  if (e.origin !== 'https://go.identomat.com') return;
  const { type, sessionId, status } = e.data ?? {};
  if (type === 'IDENTOMAT_COMPLETE') {
    clearTimeout(poll);
    handleKycResult(sessionId, status);
  }
});
const poll = setTimeout(async () => {
  const { status } = await fetch(`/api/kyc/status/${id}`)
    .then(r => r.json());
  if (status !== 'pending') handleKycResult(id, status);
}, 30_000); // Never accept event.origin === '*'
```

## Anti-patterns

- Mounting the iframe without `allow="camera"` on the element.
- Serving `/verify` over HTTP — `navigator.mediaDevices` is
  `undefined`; the SDK throws a generic `TypeError`.
- `Permissions-Policy: camera=()` site-wide without carving
  out the Identomat origin.
- Trusting `postMessage` as the only callback signal — IABs
  drop it silently; always add a backend-poll fallback.
- Skipping all WAF managed rules globally instead of scoping
  the skip narrowly to `/api/kyc/*`.
- Not detecting IABs before mounting — silent abandonment.

## Gotchas

- **WKWebView delegate (iOS 15+)** helps native apps that own
  their WebView shell; Instagram/TikTok do not expose it to
  arbitrary pages, so the restriction still applies there.
- **Android is not symmetric.** Chrome Custom Tabs and Android
  WebView generally support camera; Android users will not
  reproduce the iOS failure, masking its severity in reports.
- **Bot Fight Mode** treats Identomat server-to-server webhook
  IPs as data-centre traffic. Add their egress CIDRs to an
  IP Access allow-list before enabling BFM.
- **Rocket Loader race:** the SDK is undefined at init time
  when Rocket Loader defers it. Fix: `data-cfasync="false"`.

## Verification

```bash
curl -sI https://your-domain.com/verify \
  | grep -iE 'permissions-policy|content-security-policy'
# frame-src must include https://go.identomat.com
# Permissions-Policy must include "https://go.identomat.com"
```

- **Real iOS device, Safari DevTools console:**
  `navigator.mediaDevices.getUserMedia({video:true})`
  must trigger the camera permission prompt, not throw.
- **Instagram link tap:** "Open in Safari" banner appears;
  the Identomat iframe must not be mounted in the IAB.
- **Cloudflare Security Events:** no block or challenge on
  `/api/kyc/*` after the skip rule is applied.

## Related

- `documentation/categories/compliance/age-gating.md`
- `documentation/categories/compliance/coppa-compliance.md`
- `documentation/categories/cloudflare/waf-custom-rules.md`
- `documentation/categories/security/content-security-policy.md`
- `documentation/categories/compliance/gdpr-consent-management.md`

## Source URLs (verified 2026-08-17)

- https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia
- https://caniuse.com/mdn-api_mediadevices_getusermedia
- https://bugs.webkit.org/show_bug.cgi?id=208667
- https://developer.apple.com/forums/thread/134216
- https://docs.identomat.com/sdks/ios-sdk
- https://blog.addpipe.com/getusermedia-getting-started/
- https://developers.cloudflare.com/waf/custom-rules/
- https://developer.mozilla.org/en-US/docs/Web/API/Window/postMessage
- https://content-security-policy.com/examples/cloudflare/
- https://showdns.net/guides/how-to-set-permissions-policy
