# turnstile-best-practices

**Issue:** Cloudflare Turnstile — CAPTCHA alternative
**Date:** 2026-08-09
**Status:** documented

## Symptom
Bots are spamming your forms. You use Google
reCAPTCHA. Users complain about solving puzzles.
You wish there were a better way.

## Root cause
**CAPTCHAs hurt UX.** Use Turnstile.

**Source:** Turnstile:
https://developers.cloudflare.com/turnstile/

## The "Turnstile" concept

Turnstile is CF's CAPTCHA alternative:
- **No puzzle:** Most users don't see a challenge
- **Adaptive:** Smart difficulty per request
- **Managed:** Auto checkbox
- **Non-interactive:** No user input
- **Invisible:** Hidden
- **WCAG 2.2 AA:** Compliant

The CAPTCHA is invisible.

## The "client widget" pattern

For the client:
```html
<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
<form action="/api/signup" method="POST">
  <input name="email" type="email" />
  <div class="cf-turnstile" data-sitekey="YOUR_SITE_KEY"></div>
  <button type="submit">Sign up</button>
</form>
```

The widget is rendered.

## The "execute-on-submit" pattern (recommended)

For execute on submit:
```ts
const widgetId = window.turnstile.render('#cf-widget', {
  sitekey: 'YOUR_SITE_KEY',
  execution: 'execute',
  appearance: 'interaction-only',
  callback: (token) => pendingResolve(token),
});

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const token = await new Promise((resolve) => {
    pendingResolve = resolve;
    window.turnstile.reset(widgetId);
    window.turnstile.execute(widgetId);
  });
  // POST with token
});
```

The token is fresh on submit.

**Why:** Tokens expire after 300s. Auto-solving on page
load + slow submission = expired token = "verification
failed."

## The "server validation" pattern

For server validation:
```ts
async function verifyTurnstile(token: string, env: Env): Promise<boolean> {
  const response = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      secret: env.TURNSTILE_SECRET_KEY,
      response: token,
    }),
  });

  const result = await response.json() as { success: boolean };
  return result.success;
}
```

The token is verified.

## The "widget types" pattern

For widget types:
- **Managed:** Auto checkbox
- **Non-interactive:** No user input
- **Invisible:** Hidden

```html
<!-- Managed -->
<div class="cf-turnstile" data-sitekey="..." data-action="login"></div>

<!-- Non-interactive -->
<div class="cf-turnstile" data-sitekey="..." data-cdata="..."></div>

<!-- Invisible -->
<div class="cf-turnstile" data-sitekey="..." data-size="invisible"></div>
```

The type is per use case.

## The "Pre-Clearance cookie" pattern

For SPA / Pre-Clearance:
```html
<div class="cf-turnstile" data-sitekey="..." data-pre-clearance="true"></div>
```

CF issues a cookie; subsequent navigations skip the
challenge.

## The "domain restriction" pattern

For domain restriction, configure per widget:
- **Production:** `example.com`
- **Staging:** `staging.example.com`
- **Local:** `localhost`

Each env gets its own widget + key.

**Note:** Don't add `localhost` to production.

## The "key management" pattern

For key management:
- **Site key:** Public, in HTML
- **Secret key:** Private, in env
- **Rotate:** Regularly
- **Different per env:** Production vs dev

The secret is in the backend.

## The "token validation rules" pattern

For rules:
- **Token expires:** 300s
- **One-time use:** Each token = one validation
- **Server-side mandatory:** Always verify

The validation is server-side.

## The "Turnstile metrics" pattern

For metrics:
- **Solve rate:** % solved
- **Challenge type:** What was shown
- **Per-widget:** Per widget

The metrics are in the Turnstile dashboard.

## The "Turnstile limits" pattern

For limits:
- **Token size:** 2,048 chars
- **Token expiry:** 300s
- **One-time use:** Per token

The limits are checked.

## The "Turnstile + WAF" pattern

For defense in depth:
- **Turnstile:** Per-form bot detection
- **WAF:** Network-level protection
- **Rate limit:** Per IP

The defense is layered.

## The "Turnstile vs alternatives" choice

| Use case | Use |
|---|---|
| **CF-protected site** | Turnstile |
| **Non-CF site** | Turnstile (works on any) |
| **Critical** | Turnstile + rate limit |
| **Simple** | hCaptcha |

For most apps, **Turnstile** is the right answer.

## The "Turnstile anti-pattern" anti-patterns

### 1. Token at page load
- **Issue:** Expired on slow submit
- **Fix:** Execute on submit

### 2. No server validation
- **Issue:** Bypassable
- **Fix:** Always verify server-side

### 3. Same key for prod + dev
- **Issue:** Localhost in prod
- **Fix:** Separate keys

### 4. Secret key in HTML
- **Issue:** Secret leak
- **Fix:** Backend only

### 5. No retry on failure
- **Issue:** User can't proceed
- **Fix:** Re-execute on failure

## Verification
- **Test:** Widget renders
- **Test:** Token is valid
- **Test:** Server validation works
- **Live:** Solve rate monitored
- **Audit:** Quarterly review

## Gotchas
- **The "token at page load" anti-pattern.** Execute
  on submit.
- **The "no server validation" anti-pattern.** Always
  verify.
- **The "secret in HTML" anti-pattern.** Backend only.

## Related
- `cloudflare/waf-best-practices.md`
- `feature-cookbook-rate-limiting.md`
- `feature-cookbook-rate-limiting-detail.md`
- `feature-cookbook-auth.md`
- Turnstile: https://developers.cloudflare.com/turnstile/
