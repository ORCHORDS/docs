# Strong Customer Authentication (SCA) and 3D Secure 2 — PSD2/PSD3 Compliance

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your European payment flow has a 12% cart abandonment rate at the
3D Secure step because you redirect users to a full-page bank
authentication portal. Your mobile app uses a WebView-based 3DS
flow that feels foreign to users and breaks the native experience.
Soft declines (issuer code 65) are surfaced as payment failures
instead of being automatically retried with SCA. Your exemption
logic applies the same rules globally instead of tuning per
corridor and BIN range, causing unnecessary challenges for low-risk
transactions and missed exemptions for eligible ones.

## Context

Strong Customer Authentication (SCA) is mandated under PSD2's
Regulatory Technical Standards, requiring two-factor authentication
(knowledge, possession, or inherence) for electronic payments in
the EEA and UK. 3D Secure 2 (3DS2) is the primary implementation
protocol — the merchant sends a rich data payload (device fingerprint,
browsing context, transaction history) to the issuer's ACS via
directory server. The issuer runs risk analysis and returns either
a frictionless authentication (no cardholder interaction) or a
challenge (OTP, biometric, bank app approval). PSD3 and the new
Payment Services Regulation (PSR) reached political agreement in
November 2025, with phased application through 2026-2028. 3DS1
is being sunset by card networks and should not be relied on
architecturally.

## 3DS2 authentication flow

```
Frictionless flow (no cardholder interaction):

  1. Merchant collects payment + device data
  2. PSP sends authentication request to Directory Server
  3. Directory Server routes to issuer's ACS
  4. ACS performs risk analysis on rich data payload
  5. ACS returns frictionless result → authentication complete
  6. Authorization proceeds normally

Challenge flow (cardholder interaction required):

  1-4. Same as frictionless
  5. ACS determines challenge is needed
  6. Cardholder prompted for OTP / biometric / bank app
  7. Cardholder completes challenge
  8. ACS returns challenge result → authentication complete
  9. Authorization proceeds

Rich data payload includes:
  → Device fingerprint (browser/device characteristics)
  → Browsing context (IP, timezone, screen size)
  → Transaction history (previous purchases with merchant)
  → Cardholder account age and activity
  → Shipping vs billing address match
```

## SCA exemptions

```
Exemption               Conditions                   Liability
──────────────────────────────────────────────────────────────
Low-value               < €30 (cumulative caps       PSP requesting
                        apply: €100 or 5 txns)       exemption

TRA (Transaction        PSP fraud-rate thresholds:   PSP requesting
Risk Analysis)          < €100 at 0.13% fraud rate   exemption
                        < €250 at 0.06% fraud rate
                        < €500 at 0.01% fraud rate

Recurring / MIT         First transaction requires   Merchant
(Merchant-Initiated)    SCA; fixed-amount recurring  (after initial
                        charges exempt thereafter    SCA)

Whitelisting            Cardholder adds merchant     Issuer
(Trusted Beneficiary)   as trusted with issuer

Delegated               PSP performs SCA on          PSP by
Authentication          issuer's behalf under        agreement
                        prior agreement

Note: an exemption REQUEST does not guarantee approval.
The issuer can still force a challenge on any transaction.
Liability sits with whoever requests the exemption.
```

## Implementation with Stripe and Adyen

```
Stripe:
  PaymentIntents API:
    → request_three_d_secure: "automatic" or "any"
    → stripe.js handles frictionless/challenge client-side
    → Automatic retry of soft-declined charges with 3DS forced
    → Mobile SDK for native 3DS2 (no WebView redirect)

  Soft decline handling:
    → Issuer returns decline code 65 / 1A-family
    → Stripe auto-retries with 3DS invoked
    → Not surfaced to customer as failure

Adyen:
  /payments API:
    → authenticationData.threeDSRequestData
    → nativeThreeDS for in-app mobile flows
    → Dynamic 3D Secure: selectively apply based on risk rules
    → Configurable soft-decline auto-retry with 3DS

  Risk-based exemption:
    → Per-corridor and per-BIN exemption logic
    → Real-time fraud scoring to decide TRA eligibility
    → Exemption requested in authorization message
```

## Mobile SDK integration

```
Native 3DS2 (EMVCo-compliant):

  iOS/Android SDKs run authentication in-app:
    → No WebView redirect (reduces abandonment)
    → Native UI elements (OTP input, biometric prompt)
    → Better UX than browser-based 3DS1 redirect

  Benefits:
    → Reduced cart abandonment at authentication step
    → Faster authentication cycle
    → Better pass-through rates (more device data available)
    → Liability shift to issuer on successful authentication

  SDKs: GPayments ActiveSDK, Netcetera 3DS SDK,
         Stripe iOS/Android SDK, Adyen 3DS2 SDK
```

## PSD3 / PSR changes (2026-2028)

```
Political agreement: November 2025
Expected application: phased through 2026-2028

Key changes:
  → SCA remains mandatory, exemption rules refined
  → Clearer biometric/mobile-only authentication rules
  → Accessibility requirements for vulnerable users
  → Liability shifts FULLY to PSP if SCA required but
    not applied
  → New "confirmation of payee" name-matching checks
    before payment execution
  → Stronger open banking provisions
  → Enhanced fraud data sharing between PSPs
```

## Anti-patterns

- **Treating exemptions as a global toggle** — applying the same
  exemption logic across all corridors, BINs, and amounts. TRA
  eligibility varies by PSP fraud rate per corridor. Tune per
  market.
- **Not handling soft declines programmatically** — issuer code
  65 means "retry with SCA," not "payment failed." Surfacing
  soft declines to users as failures loses recoverable revenue.
- **WebView 3DS on mobile** — redirecting to a bank's web page
  in a WebView feels foreign and increases abandonment. Use native
  EMVCo-compliant 3DS2 SDKs for in-app authentication.
- **Failing to pass rich device data** — sparse authentication
  requests kill TRA eligibility and increase challenge rates. Send
  device fingerprint, browsing context, and transaction history.
- **Relying on 3DS1 fallback** — card networks are actively
  sunsetting 3DS1 support. Fallback paths are shrinking and should
  not be part of the architecture in 2026.

## Gotchas

- **Frictionless rates are trending down** — even as overall 3DS
  success rates improve, issuers are challenging more transactions.
  "Maximize frictionless" strategies are losing effectiveness.
  Focus on TRA calibration per corridor instead.
- **Exemption does not guarantee approval** — the issuer can
  override any exemption request and force a challenge. Build
  flows that gracefully handle challenge after exemption request.
- **Japan 3DS2 mandate (April 2025)** — requires 3DS2 on
  essentially all card-not-present transactions, causing
  measurable (~1.6pp) conversion dips where implementations
  were rushed. Test thoroughly before regional rollouts.
- **French issuer behavior (March 2025)** — French Central Bank
  guidance has issuers soft-declining exemption requests not sent
  via EMV 3DS, pushing PSPs toward compliant integration paths.

## Verification

- 3DS2 implemented with native mobile SDKs (no WebView redirect).
- Soft decline auto-retry with 3DS configured in PSP.
- TRA exemption logic tuned per corridor and BIN range.
- Rich device and behavioral data included in auth requests.
- Challenge flow UX tested and optimized for conversion.
- PSD3/PSR timeline tracked for upcoming requirement changes.
- 3DS1 fallback removed or scheduled for removal.

## Related

- `documentation/docs/policies/payments/payment-orchestration-multi-psp-routing.md`
- `documentation/docs/policies/payments/network-tokenization-lifecycle-management.md`
- `documentation/docs/policies/compliance/pci-dss-4-engineering-requirements.md`

## Source URLs (verified 2026-08-16)

- Adyen — PSD3: Everything You Need to Know — https://www.adyen.com/knowledge-hub/psd3
- Stripe — A Guide to PSD3 — https://stripe.com/guides/what-platforms-and-marketplaces-can-expect-from-psd3
- GPayments — 3D Secure and PSD2 SCA Guide for EU/UK PSPs — https://www.gpayments.com/blog/article/3d-secure-and-psd2-strong-customer-authentication-a-guide-for-european-and-uk-psps/
- Adyen Docs — 3D Secure for Regulation Compliance — https://docs.adyen.com/online-payments/3d-secure-for-regulation-compliance
