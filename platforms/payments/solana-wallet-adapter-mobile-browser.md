# solana-wallet-adapter-mobile-browser

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

`window.solana` is `undefined` on mobile Safari and mobile Chrome;
`useWallet().connect()` throws "No wallet selected" even though the
same flow works on desktop with Phantom or Solflare installed.
`WalletMultiButton` renders a list of adapters that all detect
nothing. On pages behind Cloudflare with Rocket Loader enabled the
race also surfaces on desktop during fast hard-refreshes.

## Context (example project: Solana/Helius payments, NOWPayments, mobile-first)

example project processes Solana payments via Helius RPC with NOWPayments
as the fiat-to-crypto rail. The checkout UI must work on iOS
Safari, Android Chrome, and social-app in-app browsers. Extension
wallets inject `window.solana` only on desktop; mobile devices run
wallet logic inside a separate native app unreachable through an
injected global, so every mobile path requires deep links or a
relay protocol.

## Why `window.solana` injection fails on mobile browsers

Extension wallets inject a provider via a content script at
`document_start`. That mechanism requires the browser to support
extensions — Chrome desktop and Firefox do; mobile Safari, mobile
Chrome, and every in-app WebView do not.

On iOS, Safari Web Extensions (iOS 15+) can inject `window.solana`
inside Safari only if the wallet is installed as a Safari Extension
AND the user has granted per-site permission. Phantom shipped a
Safari Extension in v23; per-site permission prompts have a low
acceptance rate. On Android Chrome the content-script path does not
exist at all.

```ts
// Anti-pattern — assumes extension, always fails on mobile
const provider = window.solana;
if (!provider?.isPhantom) throw new Error('Phantom not found');
```

## Wallet Standard vs legacy adapter detection

The Solana Wallet Standard (`@wallet-standard/app`) replaces
`window.solana` polling with an event-driven registry. Wallets
call `registerWallet()`; the DApp subscribes with `getWallets()`.

```ts
import { getWallets } from '@wallet-standard/app';

const { get, on } = getWallets();
const current = get();          // already-registered wallets
on('register', (w) => console.log('registered', w.name));
```

On a plain mobile browser `get()` returns `[]` and `register`
never fires — the standard defines no deep-link transport. The
legacy `@solana/wallet-adapter-wallets` bundle bundles a Mobile
Wallet Adapter (MWA) plugin (Android Chrome only) and a
`WalletConnectWalletAdapter`. Never invoke MWA on iOS — the
adapter silently no-ops.

## Deep-link URI schemes for Phantom and Solflare mobile apps

Deep links open the native wallet app, let the user approve, then
redirect back. Encryption uses a per-session x25519 DH key pair;
generate a fresh pair on every `connect`. Both wallets support
universal links (preferred — falls back to App Store) and a custom
scheme as a secondary option:

```
# Phantom universal link
https://phantom.app/ul/v1/connect
  ?app_url=<url-encoded-origin>
  &dapp_encryption_public_key=<base58-x25519-pubkey>
  &redirect_link=<url-encoded-callback-url>
  &cluster=mainnet-beta
phantom://v1/connect?...same params...   # Android fallback

# Solflare
https://solflare.com/ul/v1/connect?...same params...
```

```ts
import nacl from 'tweetnacl';
import bs58  from 'bs58';

const kp  = nacl.box.keyPair();          // fresh per session
const url = new URL('https://phantom.app/ul/v1/connect');
url.searchParams.set('app_url',
  encodeURIComponent('https://yourapp.com'));
url.searchParams.set('dapp_encryption_public_key',
  bs58.encode(kp.publicKey));
url.searchParams.set('redirect_link',
  encodeURIComponent('https://yourapp.com/callback'));
url.searchParams.set('cluster', 'mainnet-beta');
window.location.href = url.toString();
// Callback arrives with phantom_encryption_public_key + nonce
// + data (DH-encrypted session + user pubkey). Persist session;
// it expires after ~15 min of inactivity.
```

## WalletConnect v2 (Reown) as the mobile bridge

Reown (WalletConnect v2) is a relay-based bridge between the DApp
and any WC-compatible mobile wallet, avoiding deeplink redirect
handling. Register a free `projectId` at cloud.reown.com. Phantom
and Solflare both support WC v2; `@reown/appkit-adapter-solana`
(2025+) is the current single-component drop-in.

```ts
import { WalletConnectWalletAdapter }
  from '@walletconnect/solana-adapter';

const wcAdapter = new WalletConnectWalletAdapter({
  network: WalletAdapterNetwork.Mainnet,
  options: {
    projectId: process.env.NEXT_PUBLIC_WC_PROJECT_ID!,
    metadata: {
      name: 'example project Checkout',
      url: 'https://yourapp.com',
      icons: ['https://yourapp.com/icon-192.png'],
    },
  },
});
// Desktop: shows QR code. Mobile: deep-links into wallet app.
```

WalletConnect v1 is fully sunset — packages still pulling
`@walletconnect/web3provider` v1 fail at runtime.

## Injection race condition and Rocket Loader

Extension wallets inject `window.solana` at `document_start` via a
Manifest V3 content script. DApp bundles evaluated at module load
can run before that injection completes. Check `readyState` first
rather than assuming `DOMContentLoaded` has not yet fired
(anza-xyz/wallet-adapter PR #<number>):

```ts
function waitForInjection(ms = 2000): Promise<boolean> {
  return new Promise((resolve) => {
    if (typeof window.solana !== 'undefined') return resolve(true);
    const tid = setTimeout(() => resolve(false), ms);
    const done = () => {
      clearTimeout(tid);
      resolve(typeof window.solana !== 'undefined');
    };
    if (document.readyState === 'loading')
      document.addEventListener('DOMContentLoaded', done,
        { once: true });
    else
      window.addEventListener('load', done, { once: true });
  });
}
```

**Rocket Loader** defers all `<script>` tags asynchronously,
causing wallet injection to arrive after bundles have evaluated.
Exempt the wallet-init script or disable it on the checkout route:

```html
<script data-cfasync="false" ></script>
```

Alternatively send the `cf-rocket-loader: off` response header or
create a Cloudflare Page Rule for the checkout path.

## iOS WKWebView restrictions on wallet in-app browsers

Phantom's and Solflare's own in-app browsers control their
WKWebView and inject `window.solana` — that path works. Social
in-app browsers (Instagram, TikTok, Twitter/X) are plain WKWebViews
whose host app cannot inject on the wallet's behalf, and Apple
prohibits third-party WKWebView hosts from running content scripts
from unrelated apps. `SFSafariViewController` inherits Safari
extensions but is not what social apps open.

Detect and redirect before attempting wallet detection:

```ts
const ua = navigator.userAgent;
const isInAppBrowser =
  /Instagram|FBAN|FBAV|Twitter|Line\//.test(ua) ||
  (/iPhone|iPad/.test(ua) && !/Safari\//.test(ua));
if (isInAppBrowser) showOpenInSafariBanner();
```

## Graceful fallback when no wallet is detected on mobile

```ts
async function resolveWalletStrategy() {
  const ua = navigator.userAgent;
  const isAndroid = /Android/.test(ua);
  const isIOS    = /iPhone|iPad/.test(ua);
  const wallets  = getWallets().get();   // Wallet Standard

  if (wallets.length > 0)
    return { strategy: 'wallet-standard', wallets };
  if (!isAndroid && !isIOS)
    return { strategy: 'install-prompt-or-walletconnect' };
  if (isAndroid)
    return { strategy: 'mwa-or-deeplink' };
  return { strategy: 'deeplink-or-walletconnect' };
}
```

For users on `deeplink-or-walletconnect`: show two tracks — an
"Open in Phantom" button (universal-link connect) and a "Connect
via QR" button (WalletConnect v2). Never show an empty adapter
list; users cannot self-diagnose it.

## Anti-patterns

- Reading `window.solana` synchronously at module load and showing
  "No wallet found" immediately on mobile.
- Shipping `@solana/wallet-adapter-wallets` to mobile without
  disabling extension-dependent adapters.
- Enabling Rocket Loader globally on a Solana DApp zone without a
  `data-cfasync="false"` exemption on the wallet-init script.
- Using `phantom://v1/connect` without a universal-link fallback
  (iOS shows a system error when Phantom is not installed).
- Invoking Mobile Wallet Adapter on iOS — it silently no-ops.

## Gotchas

- Phantom Safari Extension requires explicit per-site permission;
  never branch on "extension installed" as a proxy for "injection
  active."
- `cluster` defaults to `mainnet-beta` in deep-link params; a
  mismatch causes opaque transaction rejections.
- Use separate Reown project IDs per environment to prevent
  cross-environment session leaks.
- Social in-app browsers may strip or append query params on the
  redirect URL; validate only the params you own.

## Verification

- Load checkout on real iOS Safari with Phantom extension disabled;
  confirm the fallback modal appears within 2 s.
- Test a full Phantom deeplink round-trip: approve in the app,
  verify the callback decrypts to a valid user public key.
- Enable Rocket Loader; confirm `data-cfasync="false"` restores
  consistent desktop extension detection on hard-refresh.
- After a successful deeplink `connect`, send a
  `signAndSendTransaction` with the persisted `session` and
  confirm the transaction lands on-chain via Helius RPC.

## Related

- `payments/crypto-payments-integration.md`
- `payments/nowpayments-webhook-hmac-sha512.md`
- `payments/nowpayments-invoice-lifecycle-and-late-deposits.md`
- `payments/crypto-price-volatility-handling.md`
- `payments/payment-error-handling.md`

## Source URLs (verified 2026-08-17)

- https://docs.phantom.com/phantom-deeplinks/deeplinks-ios-and-android
- https://docs.phantom.com/phantom-deeplinks/provider-methods/connect
- https://phantom.com/learn/blog/the-complete-guide-to-phantom-deeplinks
- https://docs.solflare.com/solflare/technical/deeplinks
- https://docs.solflare.com/solflare/technical/deeplinks/provider-methods/connect
- https://docs.reown.com/advanced/providers/solana-adapter
- https://github.com/anza-xyz/wallet-adapter/issues/317
- https://github.com/anza-xyz/wallet-adapter/pull/346
- https://developers.cloudflare.com/speed/optimization/content/rocket-loader/
- https://docs.solanamobile.com/web/developing-for-web
