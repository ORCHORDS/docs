# mobile-payment-redirect-back-navigation

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

After a user taps "Pay" on mobile, the browser opens a
NOWPayments hosted invoice page or a Solana wallet app. On
return — via back gesture, app-switch, or wallet deep-link —
the merchant page shows stale or "pending" state even though
the provider confirmed the payment. JavaScript may never
execute on the return page because it was a frozen bfcache
snapshot; any polling, fetch, or callback that arrived during
the freeze is silently lost.

## Context

Mobile payment flows hand the user off to an external context
(provider-hosted page, wallet app) then must recover state on
return. Two platform behaviors break the naive approach:

**bfcache (back/forward cache).** iOS Safari and Android
Chrome store a complete memory snapshot of the departure page
and restore it instantly on back navigation. JS is paused
during storage and resumes on restore, but any network
response received while frozen is discarded. iOS Safari
caches essentially all HTTPS pages including those served
with `Cache-Control: no-store`.

**App-switch and deep links.** Crypto wallet apps (Phantom,
Solflare) sign transactions and return the user via a custom
URL scheme or universal link. The OS may not restore the
original browser tab — it may open a fresh navigation
context, bypassing any in-page event entirely.

example project uses NOWPayments for crypto checkout and supports
Solana wallet deep-link signing. Both paths land on a page
that may be bfcached, backgrounded, or freshly navigated.

## Redirect Flow and bfcache Eligibility

When the user completes payment on the NOWPayments hosted
page and the provider redirects to `success_url`, iOS Safari
restores the merchant page from bfcache rather than reloading
it. Chrome on Android does the same for eligible pages.

Factors that **block** bfcache in payment flows:

- `beforeunload` listener — blocks on all major browsers
- `unload` listener — blocks on Firefox and older Safari;
  Chrome and Safari desktop ignore it since 2024, but iOS
  Safari still blocks
- Unclosed IndexedDB transactions at `pagehide` time

Do not register `unload` or `beforeunload` to detect the
user leaving the checkout page. These destroy bfcache
eligibility and force a full reload on return that is still
slower and does not recover lost events.

## Page Lifecycle Events for bfcache Detection

Three events cover every mobile return path. Wire them all on
the merchant return page:

```js
// Restored from bfcache (iOS Safari, Android Chrome).
// In-flight fetches and WS messages received while frozen
// are discarded — re-query server-side status.
window.addEventListener('pageshow', (event) => {
  if (event.persisted) refreshPaymentStatus();
});

// App-switch return: user switches to wallet app, signs,
// then switches back without a navigation (no pageshow).
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible')
    refreshPaymentStatus();
});

// Page entering bfcache — stop polling; Worker picks up.
window.addEventListener('pagehide', (event) => {
  if (event.persisted) stopPolling();
});
```

On some iOS Safari builds `visibilitychange(hidden)` fires
just before the freeze and `pageshow(persisted)` on restore,
so both handlers fire on a single back-navigation. Guard with
a 100 ms debounce or a boolean flag to prevent
double-execution.

`DOMContentLoaded` and `load` do NOT fire on bfcache
restores. Write all re-hydration logic in `pageshow` only.

## Crypto Wallet Deep-Link Return Schemes

Phantom and Solflare expose Universal Links for browser-dApp
transaction signing. The dApp builds a URL to
`https://phantom.app/ul/v1/signAndSendTransaction` (or the
Solflare equivalent) with a `redirect_link` parameter that
points back to the merchant return page, plus a base58-encoded
`payload` and session `nonce`. The wallet signs, broadcasts,
then opens `redirect_link`, appending `signature`,
`errorCode`, and `errorMessage` as query parameters.

On iOS only one app handles a custom scheme — the first
installed wallet wins with no chooser. Use `https://`
universal links as `redirect_link` so the merchant web app
opens in the browser, not a competing wallet. On Android the
Intent chooser appears; but the tab that opened the wallet
may be a different history entry than the one restored on
return. Always query status server-side on the return page —
never treat the `signature` URL parameter as payment proof
without on-chain or provider verification.

## Android Back vs iOS Swipe-Back

Android's system back button and Android 14+ predictive-back
trigger a navigation pop, so `load` may fire on Android but
not on iOS. iOS swipe-back always restores from bfcache on
Safari — `load` and `DOMContentLoaded` do not fire. The
Android 14+ predictive-back preview renders the previous page
before the gesture commits; do not start status side-effects
during that preview. Code all re-hydration to `pageshow`
exclusively — it is the only event reliable on both platforms.

## Worker Polling as Safety Net

The browser page may freeze or be replaced before any
re-hydration code runs. Maintain authoritative payment state
server-side with a Cloudflare Worker that polls NOWPayments
and caches results in KV:

```js
// Cloudflare Worker — called from the merchant return page
export default {
  async fetch(request, env) {
    const id = new URL(request.url)
      .searchParams.get('payment_id');
    const hit = await env.PAYMENTS_KV.get(`st:${id}`, 'json');
    if (hit) return Response.json(hit);

    const res = await fetch(
      `https://api.nowpayments.io/v1/payment/${id}`,
      { headers: { 'x-api-key': env.NOWPAYMENTS_API_KEY } }
    );
    const data = await res.json();
    await env.PAYMENTS_KV.put(`st:${id}`,
      JSON.stringify(data), { expirationTtl: 60 });
    return Response.json(data);
  }
};
```

The return page calls `/api/payment-status?payment_id=<id>`
in both `pageshow` and `visibilitychange`. Only `finished`
or `confirmed` status triggers fulfillment. For Solana
flows, the Worker can subscribe to an RPC WebSocket for the
expected transaction signature and persist the confirmed
slot, independent of any client-side event.

## Anti-patterns

- `unload` / `beforeunload` listeners in the checkout path —
  blocks bfcache and forces full reload on return.
- Treating `success_url` redirect as payment proof —
  NOWPayments redirects before on-chain confirmation.
- Status refresh wired to `DOMContentLoaded` or `load` —
  silent on iOS Safari bfcache restores.
- Trusting wallet-returned `signature` URL params without
  on-chain or provider API verification.
- Not pausing polling intervals in `pagehide(persisted)` —
  duplicate timers accumulate on bfcache restore.

## Gotchas

- `event.persisted` is `false` on the first load and `true`
  only on bfcache restores; check it on every `pageshow`.
- `Cache-Control: no-store` does not prevent iOS Safari from
  storing the page in bfcache (confirmed Safari 17+).
- `visibilitychange` may fire before `pageshow` on restore
  in some iOS Safari versions — debounce or flag to prevent
  double-execution.
- Phantom deeplinks require the wallet app to be installed;
  offer a QR code or NOWPayments hosted page as fallback.
- NOWPayments `waiting` / `confirming` are transient; only
  `finished` or `confirmed` warrants fulfillment.

## Verification

- On iOS Safari, complete a NOWPayments checkout then
  swipe back; assert `pageshow` fires with `persisted=true`
  and the Worker endpoint is called.
- Background the browser during a Phantom signing flow and
  restore; assert `visibilitychange` triggers
  `refreshPaymentStatus`.
- Inspect Worker KV before and after a bfcache restore to
  confirm status is current without any client event.
- Use Chrome DevTools > Application > Back/forward cache to
  confirm no blocking reasons on the merchant return page.
- Assert no `unload` or `beforeunload` listeners are active
  during checkout.

## Related

- `payments/nowpayments-invoice-lifecycle-and-late-deposits.md`
- `payments/nowpayments-callback-payment-intent-integrity.md`
- `payments/nowpayments-webhook-hmac-sha512.md`
- `payments/crypto-payments-integration.md`
- `payments/payment-state-machine-design.md`

## Source URLs (verified 2026-08-17)

- https://web.dev/articles/bfcache
- https://developer.mozilla.org/en-US/docs/Web/Events/pageshow
- https://developer.chrome.com/docs/web-platform/bfcache-ccns
- https://docs.phantom.com/phantom-deeplinks/deeplinks-ios-and-android
- https://phantom.com/learn/blog/the-complete-guide-to-phantom-deeplinks
- https://docs.solflare.com/solflare/technical/deeplinks
- https://docs.solanamobile.com/blog/ios-wallet-signing
