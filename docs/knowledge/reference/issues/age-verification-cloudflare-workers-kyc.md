# age-verification-cloudflare-workers-kyc

**Issue:** 21+ age gate via Identomat KYC breaks on mobile WebView;
  session handoff drops verification state after KYC redirect
**Date:** 2026-08-22
**Author:** example.com
**Status:** open

## Symptom

Mobile users (iOS/Android in-app WebView) complete the Identomat KYC
flow, are redirected back to example project, but land in an unverified
state. The D1 `verification_status` row is not updated. Desktop
Chrome/Safari complete the same flow without issue. Approximately
40% of mobile verifications fail to persist.

## Context

example project requires every account to pass an age gate (21+) before
accessing content. Verification is delegated to Identomat, a real-ID
KYC vendor. The flow uses an OAuth-style redirect handshake:
1. Worker issues a short-lived `kyc_session` token, stores it in D1.
2. User is redirected to Identomat's hosted verification page.
3. Identomat fires a server-side webhook AND redirects the user
   back to `/auth/kyc/callback?session=<token>&status=verified`.
4. Callback Worker reads the session token, validates the webhook
   HMAC signature, updates D1, sets a `verified` cookie, 302s home.

The webhook fires reliably; the callback redirect is where mobile
breaks.

## Mobile WebView vs Desktop Browser Differences

In-app WebViews (WKWebView on iOS, WebView2 on Android) differ from
real browsers in cookie and redirect handling:

```
┌────────────────────────┬───────────────────┬──────────────────┐
│ Behaviour              │ Desktop Browser   │ Mobile WebView   │
├────────────────────────┼───────────────────┼──────────────────┤
│ SameSite=Strict cookie │ Sent on same-     │ Dropped on any   │
│ after cross-origin     │ origin redirect   │ cross-origin hop │
│ redirect chain         │ chain             │                  │
├────────────────────────┼───────────────────┼──────────────────┤
│ 302 → 302 chain        │ Follows up to     │ Some WebViews    │
│ (multi-hop redirects)  │ 20 hops fine      │ abort at hop 2   │
├────────────────────────┼───────────────────┼──────────────────┤
│ sessionStorage         │ Persists across   │ Cleared on any   │
│                        │ 302 in same tab   │ cross-origin hop │
├────────────────────────┼───────────────────┼──────────────────┤
│ Identomat redirect URL │ Returns to app    │ May open system  │
│ scheme handling        │ URL directly      │ browser instead  │
└────────────────────────┴───────────────────┴──────────────────┘
```

Root cause: Identomat's return redirect passes through a cross-
origin hub (`verify.identomat.com → example project.app/auth/kyc/callback`).
The WebView drops the `kyc_session` cookie on that hop, so the
callback Worker cannot find the session to update.

## Session Handoff Pattern (Recommended)

Do not rely on a cookie to carry the session token through the
redirect. Encode the token in the redirect URL and validate it
server-side against the D1 row:

```ts
// workers/kyc-callback.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url          = new URL(req.url);
    const sessionToken = url.searchParams.get('session');
    const status       = url.searchParams.get('status');

    if (!sessionToken || status !== 'verified') {
      return new Response('Bad request', { status: 400 });
    }

    // Only accept sessions where webhook already set
    // webhook_confirmed = 1 (server-side validation)
    const row = await env.DB.prepare(
      `SELECT id, user_id
         FROM kyc_sessions
        WHERE token = ?1
          AND expires_at > unixepoch()
          AND webhook_confirmed = 1`
    ).bind(sessionToken).first();

    if (!row) {
      return new Response('Session invalid or expired', { status: 403 });
    }

    await env.DB.prepare(
      `UPDATE users
          SET verification_status = 'verified',
              verified_at = unixepoch()
        WHERE id = ?1`
    ).bind(row.user_id).run();

    // SameSite=None for cross-origin WebView compat; requires Secure
    return new Response(null, {
      status: 302,
      headers: {
        Location: '/',
        'Set-Cookie': [
          `verified=1; Path=/; HttpOnly; Secure; SameSite=None`,
          `kyc_session=; Path=/; Max-Age=0`,
        ].join(', '),
      },
    });
  },
};
```

## D1 Verification Status Schema

```sql
CREATE TABLE kyc_sessions (
  id                TEXT PRIMARY KEY,
  token             TEXT NOT NULL UNIQUE,
  user_id           TEXT NOT NULL,
  created_at        INTEGER NOT NULL DEFAULT (unixepoch()),
  expires_at        INTEGER NOT NULL,  -- created_at + 900 (15 min)
  webhook_confirmed INTEGER NOT NULL DEFAULT 0,
  result            TEXT               -- 'verified'|'rejected'|NULL
);

CREATE TABLE users (
  id                  TEXT PRIMARY KEY,
  verification_status TEXT NOT NULL DEFAULT 'unverified',
                        -- 'unverified'|'pending'|'verified'|'rejected'
  verified_at         INTEGER,
  reverify_after      INTEGER   -- NULL or future unixepoch
);

CREATE INDEX idx_kyc_sessions_token ON kyc_sessions(token);
CREATE INDEX idx_users_status
    ON users(verification_status);
```

## Re-verification Triggers

```
┌──────────────────────────────┬────────────────────────────────┐
│ Trigger                      │ Action                         │
├──────────────────────────────┼────────────────────────────────┤
│ Identomat webhook:           │ Set reverify_after = now+86400 │
│ re-check required signal     │ Notify user; block content     │
├──────────────────────────────┼────────────────────────────────┤
│ Account email/phone changed  │ Reset status to 'pending';     │
│                              │ immediate re-gate on next req  │
├──────────────────────────────┼────────────────────────────────┤
│ Trust score drops below 20   │ Flag for reverify within 7 d   │
├──────────────────────────────┼────────────────────────────────┤
│ Annual re-verification       │ Cron sets reverify_after       │
│ policy (365 days)            │ = verified_at + 31536000       │
└──────────────────────────────┴────────────────────────────────┘
```

A Cloudflare Cron Trigger checks `reverify_after < unixepoch()`
each hour and sets `verification_status = 'pending'` for due rows.

## Anti-patterns

- **Relying on SameSite=Strict cookies through cross-origin KYC
  redirects.** They are dropped silently in WebViews. Use the URL
  token pattern above.
- **Trusting the redirect callback alone without the webhook.**
  The redirect can be replayed or spoofed. Always require
  `webhook_confirmed = 1` before upgrading status in D1.
- **Storing KYC PII in D1.** Identomat holds the document scan.
  example project D1 rows must store only session token, result, and
  timestamp — no name, DOB, or document number.

## Gotchas

- iOS WKWebView with `App-Bound Domains` configured will refuse to
  navigate to `identomat.com` unless it is listed in
  `Info.plist > WKAppBoundDomains` in the native shell app.
- Identomat webhook POST includes `X-Identomat-Signature` HMAC.
  Verify it with `crypto.subtle.verify` — do not skip in staging.
- `SameSite=None` requires `Secure`. In local `wrangler dev` (HTTP)
  the cookie is silently dropped by the browser.
- D1 `unixepoch()` returns an integer (seconds). JavaScript
  `Date.now()` is milliseconds. Always divide JS timestamps by
  1000 before binding to D1 epoch columns.

## Verification

```
# 1. Confirm webhook sets webhook_confirmed=1 before redirect fires
curl -X POST https://example project.app/webhooks/kyc \
  -H 'X-Identomat-Signature: <valid-hmac>' \
  -d '{"session":"tok_test","status":"verified"}'
# → 200 OK

# 2. Hit callback with valid token, expect 302 to /
curl -I 'https://example project.app/auth/kyc/callback\
?session=tok_test&status=verified'
# → HTTP/2 302  Location: /  Set-Cookie: verified=1

# 3. Confirm D1 row updated
wrangler d1 execute example project-db --command \
  "SELECT verification_status FROM users WHERE id='<uid>'"
# → verified
```

## Related

- `documentation/docs/policies/issues/platform-trust-score-cloudflare-signals.md`
- `documentation/docs/policies/issues/cookie-samesite-lax-oauth-redirect.md`
- `documentation/docs/policies/issues/d1-column-affinity-gotcha.md`
- `documentation/docs/policies/issues/content-moderation-appeals-workflow.md`

## Source URLs

- https://docs.identomat.com/integration/redirect-flow
- https://developers.cloudflare.com/d1/
- https://webkit.org/blog/10218/full-third-party-cookie-blocking-and-more/
- https://developer.apple.com/documentation/webkit/wkwebview
