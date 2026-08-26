# Network Tokenization — Visa and Mastercard

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your card-not-present (CNP) transaction authorization rate is below
industry benchmarks (85-90%). Customers experience failed recurring
payments when cards expire or are reissued. You store raw PANs (Primary
Account Numbers) in your vault, increasing PCI DSS scope and exposure to
breaches. You are paying full interchange rates without leveraging
tokenization-based incentives.

## Context

Network tokenization replaces the primary account number (PAN) with a
token issued by the card network (Visa, Mastercard, Amex) rather than by
the merchant's payment processor or gateway. Network tokens are domain-
restricted (tied to a specific merchant), lifecycle-managed (automatically
updated when cards are replaced), and cryptographically secured with
transaction-specific cryptograms. By 2026, tokenized transactions are
projected to reach 283 billion globally, with Visa and Mastercard aiming
for near-universal adoption by 2030.

## How network tokens work

```
Customer card → Card network (Visa/MC) issues token
                      ↓
Token (DPAN/TPAN) stored by merchant
                      ↓
Transaction: merchant sends token + cryptogram
                      ↓
Card network de-tokenizes → routes to issuer with real PAN
                      ↓
Issuer approves (higher confidence due to cryptogram)
```

### Token types

| Type | Full name | Use case |
|---|---|---|
| **DPAN** | Device PAN | Mobile wallets (Apple Pay, Google Pay) |
| **TPAN** | Token PAN | Card-on-file / e-commerce |
| **MPAN** | Merchant PAN | Merchant-specific recurring billing |

## Authorization rate uplift

Network tokens consistently improve authorization rates for CNP
transactions because issuers have higher confidence in tokenized requests:

- **Visa**: average 4.6% authorization rate uplift on CNP transactions
  compared to raw PANs.
- **Mastercard**: average 2.1% uplift.
- **Combined effect**: fewer false declines, higher revenue, better
  customer experience.

The uplift comes from:

1. **Pre-validation** — the card network validates the token before the
   authorization reaches the issuer.
2. **Cryptogram** — a transaction-specific cryptogram proves the token is
   being used by the authorized merchant.
3. **Lifecycle management** — the token automatically reflects card
   reissues, so stale credentials never reach the issuer.

## Lifecycle management

The most operationally significant benefit: network tokens update
automatically when the underlying card changes.

| Event | Raw PAN behavior | Network token behavior |
|---|---|---|
| Card expires | Transaction fails; customer must re-enter card | Token automatically maps to new card |
| Card reissued (lost/stolen) | Transaction fails | Token updated by the network |
| Card number changes | Transaction fails | Token updated transparently |

This eliminates "involuntary churn" — subscription cancellations caused by
failed recurring payments on expired/reissued cards.

## Implementation approaches

### 1. PSP-managed tokenization (simplest)

Your payment service provider (Stripe, Adyen, Braintree) manages network
token provisioning and usage transparently. You use your existing
integration and the PSP handles tokenization behind the scenes.

- Stripe: network tokens enabled by default for eligible cards.
- Adyen: network tokenization via the Adyen Token Service.
- Braintree: network tokens via the Braintree Vault.

### 2. Direct network integration

Large merchants can integrate directly with Visa Token Service (VTS) and
Mastercard Digital Enablement Service (MDES). This provides maximum
control but requires significant development and ongoing maintenance.

### 3. Token service provider (TSP)

Third-party TSPs (Spreedly, Basis Theory) provide a unified API across
card networks, simplifying multi-network tokenization without direct
network integration.

## PCI DSS impact

Network tokens reduce PCI DSS scope because:

- Tokens are not usable outside the merchant-network relationship. A
  stolen token cannot be used at another merchant.
- Tokens do not require the same storage protections as PANs under
  PCI DSS v4.0.1.
- Merchants can replace vault-stored PANs with network tokens,
  potentially reducing their CDE (Cardholder Data Environment) footprint.

## Anti-patterns

- **Storing both PAN and token** — defeats the purpose of tokenization.
  Once a network token is provisioned, delete the raw PAN from your vault.
- **Not requesting cryptograms** — submitting a network token without a
  cryptogram loses most of the authorization rate uplift. Always include
  the cryptogram in the authorization request.
- **Ignoring token lifecycle events** — the card network sends lifecycle
  notifications (token status changes, card updates). Failing to process
  these events negates the lifecycle management benefit.
- **Assuming all cards are tokenizable** — not all cards or issuers
  support network tokenization. Implement fallback to raw PAN for
  non-tokenizable cards.

## Gotchas

- **Multi-PSP setups** — if you use multiple payment processors, each
  needs its own token provisioning. A network token provisioned through
  Stripe cannot be used through Adyen (the domain restriction is per-
  merchant-per-PSP relationship).
- **3DS interaction** — network tokens and 3D Secure are complementary,
  not exclusive. Use both for maximum authorization rate uplift and
  liability shift.
- **Cost** — card networks charge token provisioning and management fees
  (typically $0.01-0.03 per token provisioned). This is usually offset
  by the authorization rate uplift and reduced churn.
- **Regional availability** — network tokenization coverage varies by
  issuer and region. Coverage is highest in North America and Europe,
  lower in APAC and LATAM.

## Verification

- Network tokenization is enabled for card-on-file and recurring
  transactions.
- Authorization rate uplift is measured against a control group (raw PAN).
- Token lifecycle events are processed — no stale tokens in the vault.
- Cryptograms are included in all tokenized authorization requests.
- PCI DSS scope is reassessed after token migration.
- Fallback to raw PAN is implemented for non-tokenizable cards.

## Related

- `documentation/docs/policies/payments/pci-dss-compliance.md`
- `documentation/docs/policies/payments/3ds-strong-customer-authentication.md`
- `documentation/docs/policies/payments/stripe-webhook-integration.md`
- `documentation/docs/policies/security/tls-certificate-lifecycle-management.md`

## Source URLs (verified 2026-08-16)

- Spreedly network tokenization — https://www.spreedly.com/blog/network-tokenization-explained
- Solidgate authorization rate uplift — https://solidgate.com/blog/network-tokenization-authorization-rates/
- Payment token standards 2026 — https://webpayme.com/blog/payment-token-standards-2026
- myPayAdvisor tokenization — https://www.mypayadvisor.com/insights/tokenization-for-higher-approval-rates
