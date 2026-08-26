# mobile-digital-wallets-apple-pay-google-pay

**Issue:** Apple Pay and Google Pay are the highest-converting payment methods on mobile — one biometric tap instead of typing a 16-digit card — but they are not buttons you drop in. A wallet button that renders when the wallet is not set up, the region is unsupported, or the funding method is rejected produces a dead-end checkout, and the tokenization model (device-specific tokens, not raw PANs) means the server side must decrypt and verify payloads it never sees as plain card numbers. Both ecosystems also gate live traffic behind merchant certification and review. Teams integrating wallets need to handle availability gating, the payment-sheet flow, server-side token verification, and failure modes — or they leak the exact conversion gains wallets exist to provide.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How wallet payments actually work

1. **Tokenization, not card numbers.** When a user taps Pay, the device sends the card as a network token (a DPAN) encrypted for your payment processor — the app and your backend never receive the real PAN. This is why wallet flows sidestep most PCI scope while raw-card forms do not.
2. **The processor is the decoder.** Apple Pay returns an encrypted PKPaymentToken; Google Pay returns a tokenized payload. Only your PSP (Stripe, Adyen, or gateway) can decrypt with your merchant keys. Plan the backend around forwarding the token, never around parsing card data out of it.
3. **Certification gates go-live.** Both Apple (merchant ID + domain verification for web, entitlement for app) and Google (merchant center configuration) require approval before production charges succeed. Budget days, not hours, and test with sandbox entitlements until certified.
4. **Merchants, not apps, are verified.** Verification binds your domain (Apple) or gateway merchant ID (Google) to your business. A mismatch between the certified domain and the one requesting payment is a common production-only failure.

## Availability gating before rendering

1. **Three independent gates.** A wallet button is only usable when the device has the wallet enabled with a funded card, your region supports that wallet, and the transaction's currency/funding method is accepted. All three must pass — checking one and hoping is how dead buttons ship.
2. **Query capability APIs, not device version.** Use isCanMakePayments (Apple) and the PaymentsClient isReadyToPay query (Google) at checkout time. Feature detection on OS version misfires because a user may simply have no card added.
3. **Hide rather than disable.** When a wallet is unavailable, remove the button instead of greying it: disabled buttons read as broken checkout. Keep at least one always-available method (card entry) as the floor.
4. **Show wallets early and above the fold.** When available, wallet buttons belong at the top of the payment sheet; on iOS the Apple Pay mark has strict placement and branding rules from the App Store marketing guidelines.

## Transaction flow implementation

1. **Server-driven amount and line items.** The client should request the payment sheet contents (amount, items, merchant capability, shipping methods) from your backend at checkout time. Client-computed totals let a tampered app charge wrong amounts; the server must re-derive the final charge.
2. **Use PaymentSheet-style SDK components where possible.** PSP SDKs (Stripe Payment Sheet, Adyen drop-in) handle the sheet UI, gateway availability, and token forwarding. Hand-rolling the native sheets (PKPaymentRequest / PaymentDataRequest) is only worth it for heavily customized flows.
3. **Authorize, then confirm server-side.** After the sheet authorizes, send the token plus your cart/session ID to your backend, which creates the charge with the PSP and returns the authoritative result. Never treat the client-side sheet dismissal as payment success — authorization must be confirmed by a server call, idempotently keyed.
4. **Handle shipping and billing updates.** Both sheets can call back with updated shipping address/method to recalculate totals. Implement these callbacks to re-price tax and shipping, or the charged amount diverges from the sheet display.

## Failure modes and edge cases

1. **User cancellation is not an error.** Sheet dismissal before biometric completion is a normal path — return the user to the payment method list quietly, without a red error toast.
2. **Biometric failure fallback.** Device passcode is the fallback when Face ID/Touch ID fails; but repeated cancels usually mean the user wants another method. Offer the card form one tap away.
3. **Declines still happen on wallets.** Insufficient funds and issuer declines occur post-authorization; your order state machine must handle authorized-but-declined and retry with a different method without duplicating orders (idempotency keys again).
4. **Test the full matrix before launch.** Sandbox Apple Pay needs test cards in the device wallet and a certified sandbox merchant; Google Pay needs the environment flag flipped (TEST/PRODUCTION) and staging gateway credentials. Verify success, cancel, decline, and refund paths in both, plus on at least one low-end Android device where Play Services is outdated.

## Operational concerns

1. **Reconcile daily.** Match PSP settlement reports against your orders table; wallet transactions flow through the same reconciliation as cards but can settle with different fees.
2. **Refunds use the token.** Refund via the PSP charge ID from the original transaction — you cannot store a wallet token for later charges unless you built a recurring billing session through the PSP.
3. **Monitor wallet-specific metrics.** Track wallet button display rate, tap-to-authorize conversion, and authorization failure codes separately by wallet; gating regressions (a PSP config change silently disabling isReadyToPay) are invisible in aggregate payment dashboards.
