# Cloudflare Turnstile: Invisible Widget and Server Validation

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Bot-created accounts slip through example project signup flow.
The visible Turnstile checkbox breaks the "frictionless
21+ onboarding" design principle. Mobile WebView embeds
fail to load the challenge, or the token is never returned
to native code. Server-side validation is either missing
or the same token is accepted twice when a user double-taps
the submit button.

## Context

WAM (example.com) uses Cloudflare Turnstile on every
unauthenticated surface: account creation, login, age
verification submission, and password reset. The
platform targets a 21+ audience; bot account creation
is a regulatory risk, not just a nuisance. Invisible
mode is used to preserve the brand UX; mobile clients
inject JavaScript into a WebView to surface the widget.
Server-side validation runs in a Cloudflare Worker before
any D1 write or SMS code is dispatched.

## 1. Widget Mode Comparison

| Mode            | Visible element         | User interaction | Privacy addendum |
|-----------------|-------------------------|------------------|-----------------|
| Managed         | Checkbox (sometimes)    | Click if prompted| Not required    |
| Non-interactive | Spinner during check    | None             | Not required    |
| Invisible       | Nothing                 | None             | **Required**    |

**Managed** (recommended default): Cloudflare's risk engine
decides whether to show a checkbox. Most users see nothing;
high-risk signals trigger the checkbox. Best balance of
security and UX for most forms.

**Non-interactive**: Always shows a loading spinner while
the challenge runs silently. Signals to users that something
is happening; useful when a visible security indicator is
desired without asking them to act.

**Invisible**: Completely hidden. Zero UI. The widget runs
in the background and calls `callback` when done. To enable
it, you must link Cloudflare's Turnstile Privacy Addendum
in your privacy policy. Use for sensitive flows where any
UI element breaks conversion.

WAM uses **invisible** mode on the signup and login screens
and **managed** mode on the age-verification submission
form (higher risk surface, acceptable friction).

## 2. Client-Side Integration: Invisible Widget

```html
<!-- Load the Turnstile script -->
<script src="https://challenges.cloudflare.com/turnstile/v0/api.js"
        async defer></script>

<!-- Invisible widget container (hidden by mode) -->
<div id="cf-turnstile"
     class="cf-turnstile"
     data-sitekey="0x4AAAAAAAxxxxxxxxxxxxxxxx"
     data-callback="onTurnstileSuccess"
     data-theme="auto"
     data-size="invisible"></div>
```

```javascript
function onTurnstileSuccess(token) {
  // Attach token to form or store for later submit
  document.getElementById("cf-token").value = token;
}

// Programmatic render (call after DOM ready)
turnstile.render("#cf-turnstile", {
  sitekey:  "0x4AAAAAAAxxxxxxxxxxxxxxxx",
  callback: onTurnstileSuccess,
  size:     "invisible",
  theme:    "auto",
});

// Reset after a failed submission to get a fresh token
function resetTurnstile() {
  turnstile.reset("#cf-turnstile");
}
```

The token (`cf-turnstile-response`) is valid for 300 seconds
(5 minutes) and has a maximum length of 2,048 characters.
Tokens are **single-use** — submit them exactly once.

## 3. Server-Side Validation in a Worker

The siteverify endpoint is:

```
POST https://challenges.cloudflare.com/turnstile/v0/siteverify
```

Validate every form submission before processing:

```typescript
interface TurnstileResult {
  success:      boolean;
  challenge_ts: string;
  hostname:     string;
  "error-codes": string[];
  action:       string;
  cdata:        string;
}

export async function verifyTurnstileToken(
  token:    string,
  remoteIp: string,
  env:      Env,
): Promise<TurnstileResult> {
  const resp = await fetch(
    "https://challenges.cloudflare.com/turnstile/v0/siteverify",
    {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        secret:   env.TURNSTILE_SECRET_KEY,
        response: token,
        remoteip: remoteIp,
      }),
    },
  );

  if (!resp.ok) {
    throw new Error(`siteverify HTTP ${resp.status}`);
  }

  return resp.json<TurnstileResult>();
}

// In your request handler:
export async function handleSignup(
  request: Request,
  env:     Env,
): Promise<Response> {
  const body  = await request.json<{ token: string; /* … */ }>();
  const ip    = request.headers.get("CF-Connecting-IP") ?? "";
  const check = await verifyTurnstileToken(body.token, ip, env);

  if (!check.success) {
    return Response.json(
      { error: "Bot check failed", codes: check["error-codes"] },
      { status: 403 },
    );
  }

  // Proceed with D1 write / SMS dispatch
}
```

**Idempotency:** Because tokens are single-use, a
double-submit from the client will return
`timeout-or-duplicate` on the second call. The client
must call `turnstile.reset()` and re-render a new token
before retrying. Do not retry the same token value.

For safe server-side retries (e.g. transient network
errors calling siteverify) pass an `idempotency_key`:

```typescript
body: JSON.stringify({
  secret:           env.TURNSTILE_SECRET_KEY,
  response:         token,
  remoteip:         remoteIp,
  idempotency_key:  crypto.randomUUID(), // stable per request
}),
```

The same `idempotency_key` can be resent to siteverify
multiple times without counting as a duplicate.

## 4. Mobile WebView Integration

Native iOS/Android apps embed WAM's signup flow in a
WebView. The Turnstile script requires a real browser
environment; limited WebViews (e.g. `WKWebView` with
JavaScript disabled) will silently fail.

Requirements:
- JavaScript must be enabled on the WebView instance.
- The WebView must load the page from the real WAM origin
  (`https://example.com`) — `localhost` or `file://` will
  fail sitekey domain validation.
- If using a custom scheme bridge (`wam://callback`),
  inject a JavaScript handler that relays the token to
  native code:

```javascript
// Injected via WKUserScript (iOS) or evaluateJavascript (Android)
window.onTurnstileSuccess = function(token) {
  // iOS WKWebView message handler
  window.webkit.messageHandlers.turnstileToken.postMessage(token);
  // Android JavascriptInterface
  // Android.onTurnstileToken(token);
};
```

Use `data-size="invisible"` and trigger `turnstile.render()`
programmatically after the WebView `DOMContentLoaded` event
to avoid layout shifts on mobile.

## 5. Error Codes Reference

| Error code                | Meaning                                   | Action                        |
|---------------------------|-------------------------------------------|-------------------------------|
| `missing-input-secret`    | `secret` param not sent                   | Fix server code               |
| `invalid-input-secret`    | Secret key is invalid or expired          | Rotate in dashboard           |
| `missing-input-response`  | `response` (token) not sent               | Fix client code               |
| `invalid-input-response`  | Token malformed, expired, or wrong key    | Client must reset widget      |
| `bad-request`             | Malformed request body                    | Fix request format            |
| `timeout-or-duplicate`    | Token already used or > 300 s old        | Client must reset widget      |
| `internal-error`          | Cloudflare-side error                     | Retry with backoff            |

## 6. Turnstile vs reCAPTCHA v3 Scoring Comparison

| Dimension              | Turnstile                         | reCAPTCHA v3                     |
|------------------------|-----------------------------------|----------------------------------|
| Challenge model        | Pass / Fail (binary)              | Score 0.0–1.0 (threshold tuning) |
| Puzzle / friction      | None (invisible/managed modes)    | None (invisible)                 |
| Data collection        | Minimal (Cloudflare Privacy Addendum)| Google ecosystem signals      |
| Token validity         | 300 s, single-use                 | 120 s (2 min), single-use        |
| Server-side endpoint   | `challenges.cloudflare.com`       | `www.google.com/recaptcha/api`   |
| Cost                   | Free (included in all CF plans)   | Free up to quota; paid above     |
| GDPR / privacy         | Easier — no Google data sharing   | Requires Google consent handling |
| False-positive control | Managed by CF; no threshold tuning| Developer tunes score threshold  |

For WAM's user base (adult, mobile-first), Turnstile's
binary pass/fail model eliminates the threshold-tuning
risk where reCAPTCHA v3 score decisions are arbitrary.
No Google data sharing also simplifies the privacy policy
for the 21+ platform context.

## Anti-patterns

- Accepting a token on the server without calling
  siteverify — the client-side widget alone provides
  no security guarantee.
- Reusing or caching a token across multiple form
  submissions — the second call will always return
  `timeout-or-duplicate`.
- Serving the Turnstile widget from `localhost` in
  staging — use the test sitekey
  (`1x00000000000000000000AA`) that always passes.
- Calling siteverify from client-side JavaScript and
  forwarding the result to the backend — the secret key
  would be exposed in the browser.
- Not calling `turnstile.reset()` before allowing a
  user to retry a failed submission.

## Gotchas

- Invisible mode requires the Cloudflare Turnstile
  Privacy Addendum to be linked in your privacy policy
  before you can enable it in the dashboard.
- Turnstile tokens are max 2,048 characters. Middleware
  or WAFs with small header limits may truncate them if
  the token is passed in a header rather than the body.
- The `challenge_ts` field in the siteverify response
  is the time the challenge was solved, not when the
  token was created — useful for detecting pre-solved
  tokens submitted hours later.
- Test sitekeys for automated testing:
  - Always passes: `1x00000000000000000000AA`
  - Always fails:  `2x00000000000000000000AB`
  - Always triggers interactive: `3x00000000000000000000FF`
- On mobile WebViews, if the WebView navigates away and
  back, the widget token is stale — call `reset()` on
  every page focus event.

## Verification

1. Submit the signup form with a valid token; confirm
   siteverify returns `{ "success": true }` in Worker
   logs.
2. Submit the same token a second time; confirm the
   Worker returns 403 with `timeout-or-duplicate`.
3. Submit with `response: ""` (empty string); confirm
   `missing-input-response` error and 403.
4. Use the test sitekey `2x00000000000000000000AB` to
   force a failure end-to-end and confirm the UI shows
   the retry prompt and calls `turnstile.reset()`.
5. Test from a mobile WebView and confirm the token
   is correctly relayed to native code via the message
   handler.

## Related

- `turnstile-best-practices.md` — general widget setup
- `turnstile-webview-in-app-browser-challenge-loops.md`
- `managed-challenge-mobile-browser-pass-rates.md`
- `waf-rate-limiting-deep-dive.md` — complementary
  bot-mitigation layer

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/turnstile/get-started/server-side-validation/
- https://developers.cloudflare.com/turnstile/concepts/widget/
- https://developers.cloudflare.com/turnstile/get-started/client-side-rendering/widget-configurations/
- https://developers.cloudflare.com/turnstile/troubleshooting/client-side-errors/error-codes/
- https://developers.cloudflare.com/turnstile/troubleshooting/testing/
