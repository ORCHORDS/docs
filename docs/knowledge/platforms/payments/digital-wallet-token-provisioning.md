# Digital Wallet Token Provisioning

**Issue:** Apple Pay, Google Pay, Samsung Pay, and Garmin Pay issue scheme-managed tokens at the wallet layer rather than at the merchant or acquirer. The tokenization handshake happens inside the OEM's secure environment (Secure Element on iOS, StrongBox / TEE on Android) and is opaque to the merchant. The merchant receives a Payment Network Token (typically DPAN or FPAN per scheme rules) plus a network cryptogram that proves the token was bound to a specific device attestation. Engineering the wallet provisioning flow means understanding the in-app and web flows, the in-store contactless flows where they intersect with the merchant's token usage, the differences between issuer-side provisioning (issuer-hosted) and merchant-side push provisioning (PAN-in-app), and the merchant's role in detokenization for chargeback evidence.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Provisioning modes

1. **In-app provisioning (issuer-side).** The cardholder adds a card inside the wallet app; the wallet performs an authentication with the issuer (often an account-verification step or a one-time OTP), and the issuer provisions the token. The merchant is not in the loop. Engineering impact is downstream: the merchant sees an Apple Pay or Google Pay authorization with a network cryptogram and an opaque DPAN.
2. **In-app push provisioning (merchant-initiated).** A merchant with stored card-on-file PAN can offer to push the card into the customer's wallet via Apple's `passkit` Android's `wallet-api`, or the scheme-specific push APIs. The merchant-side component calls the wallet SDK, which initiates the issuer verification flow. The merchant's role ends at the SDK call; the token lifecycle is then wallet-managed.
3. **Web provisioning (browser-side).** Apple Pay on the Web, Google Pay on the Web, and Click to Pay (the EMVCo scheme) tokenize a stored card without the device-bound secure element, using a browser-side attestation. The merchant integrates the wallet's web SDK and receives a DPAN with a network cryptogram per transaction. The web token is bound to the browser session, not the device.

## Cryptogram mechanics

1. **EMV-mode cryptogram.** Each wallet transaction generates an Application Request Cryptogram (ARQC) computed over transaction data using a TRID-bound key. The merchant submits the cryptogram alongside the authorization. The network validates the cryptogram and either accepts (with liability shift) or rejects (forcing a fall-back to PAN or a hard decline).
2. **Cryptogram window.** Cryptograms are single-use and time-bound. Network rules typically allow a window of a few minutes between token usage and authorization, after which the cryptogram is treated as expired. Retry logic must generate a fresh cryptogram per attempt.
3. **Transaction token versus payment credential.** Wallets can issue either a single-use transaction token (one cryptogram for one authorization) or a recurring payment credential (multiple cryptograms for an ongoing subscription). The merchant must integrate with the appropriate flow and store the right metadata.

## Merchant integration points

1. **SDK tokenization in checkout.** When the wallet button is tapped, the SDK returns a one-time payload containing the DPAN, the network cryptogram, and transaction metadata. The merchant passes this to the acquirer in place of a PAN-based authorization. The acquirer and network process the authorization against the token; the merchant does not need to detokenize.
2. **Recurring transactions on wallet credentials.** Apple's recurring payments API and Google's equivalent allow a stored wallet credential to be used for merchant-initiated transactions (MITs). The merchant stores the wallet credential reference, not the DPAN, and submits a CIT (customer-initiated transaction) at first use, then MITs for subsequent charges. The network cryptogram is regenerated per transaction.
3. **Refunds and partial captures.** Wallet refunds use the same token and require a fresh cryptogram from the SDK. Engineering must surface a "refund to original payment method" path that walks the cardholder back through the wallet SDK — you cannot refund a wallet payment by tokenizing a PAN the merchant never had.

## Operational concerns

1. **Card-replacement propagation.** Wallet tokens bind to the device and to the underlying card. When the issuer replaces the card, the wallet provider updates the token; the merchant's account-on-file reference may or may not be updated depending on the integration. Account updater integration is critical.
2. **Wallet unlinking and device loss.** When the cardholder removes the card from the wallet or reports the device lost, the wallet provider suspends the token. Subsequent attempts to authorize on the suspended token decline at the network layer. Engineering must surface a re-add flow at next checkout.
3. **Liability shift envelope.** Wallet transactions carry liability shift in most cases. The merchant receives the cryptogram and a network-verified authentication result. Engineering must not treat the wallet's approval as an unconditional liability shield — issuer chargeback reason codes can still apply for specific fraud categories.

## Failure modes

1. **Storing wallet cryptogram as a credential.** A wallet cryptogram is a single-use token, not a card-on-file reference. Merchants that store the cryptogram for recurring use are submitting single-use credentials to the network, which yields network-level declines or chargeback risk on the first reuse.
2. **Submitting wallet DPAN without the cryptogram.** A DPAN without its accompanying cryptogram is treated as an unverified token by the network and often declines. Engineering must ensure the SDK payload — DPAN, expiry, cryptogram, ECI indicator — travels together through the acquirer connection.
3. **Wallet SDK version drift.** Apple, Google, and Samsung update their SDKs on different cadences. A checkout that works on the current iOS SDK may fail on the previous major because the cryptogram format or the response payload structure changed. Pin SDK versions and test across versions before release.

## Canonical sources

1. EMVCo, EMV Contactless Specifications for Payment Systems and EMV Payment Tokenization Specification. https://www.emvco.com/specifications/
2. PCI Security Standards Council, Payment Card Industry Data Security Standard, Version 4.0, including the dedicated mobile payment acceptance guidance. https://www.pcisecuritystandards.org/document_library
