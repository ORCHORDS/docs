# Cryptocurrency Regulatory Risk for Platforms

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

example project integrates NOWPayments to accept Solana (SOL) and
other cryptocurrencies for premium features. A legal review
raises three questions: does accepting crypto payments make the
platform a FinCEN money services business (MSB) requiring
registration? Does the FATF Travel Rule apply to transactions
processed by NOWPayments? Does accepting crypto from EU users
trigger MiCA crypto-asset service provider (CASP) obligations?
Each question has a materially different answer depending on
the platform's custody model.

## Context

Crypto payment acceptance for platform services sits in a
regulatory gray zone. The platform does not custody crypto,
issue tokens, or operate an exchange — it uses NOWPayments,
which converts crypto to fiat before the platform receives
funds. This "merchant-only" architecture determines which
obligations attach. The analysis differs by jurisdiction: US
(FinCEN MSB), EU (MiCA), OFAC sanctions, and the FATF Travel
Rule, which travels with the funds regardless of jurisdiction.

## FinCEN MSB analysis (US)

```
31 CFR § 1010.100 — MSB definitions include:
  → Money transmitter
  → Cryptocurrency exchanger or administrator
    (FinCEN guidance FIN-2013-G001)

Scenario A (current): NOWPayments receives crypto from user
  → instantly converts to fiat → platform receives USD/EUR.
  Analysis: NOWPayments is the MSB (money transmitter +
  crypto exchanger). Platform is a merchant receiving payment
  for services. Merchants are EXCLUDED from MSB definition
  (31 CFR § 1010.100(ff)(8)(ii)).
  Conclusion: Platform is NOT an MSB under Scenario A.

Scenario B (avoid): Platform holds crypto in a platform-
  controlled wallet before conversion.
  Analysis: Holding + transmitting crypto for others triggers
  money transmitter classification.
  Conclusion: DO NOT hold crypto in platform-controlled wallets.

Scenario C (avoid): Platform issues its own token.
  Analysis: Token issuance = crypto administrator = MSB.
  Conclusion: Requires separate legal review + likely
  FinCEN registration. Penalties: up to $250,000/day/violation.
```

## FATF Travel Rule and OFAC sanctions

```
FATF Travel Rule:
  Applies to: virtual asset service providers (VASPs)
  US threshold: $3,000 per transaction (FinCEN rule)
  EU threshold: EUR 1,000 (Transfer of Funds Regulation)

  In the NOWPayments integration:
    → NOWPayments is the VASP receiving from user's wallet
    → Platform is the beneficiary merchant
    → Travel Rule obligation sits with NOWPayments, not platform
    → Caveat: if platform ever provides custodial wallets,
      it becomes a VASP and Travel Rule applies immediately

OFAC sanctions screening:
  → OFAC has listed 200+ crypto wallet addresses on SDN list
    as of 2026 (Suex, Garantex, Bitzlato enforcement cases)
  → OFAC violations carry strict liability — intent no defense
  → "I used a payment processor" is not a complete shield if
    screening was not contractually required

  Required contractual language in NOWPayments agreement:
    "NOWPayments must screen originating wallet addresses
    against the OFAC SDN list before processing payment."

  Defense-in-depth at platform level:
    → On payment webhook receipt: extract originating wallet
    → Screen against OFAC SDN list (Chainalysis / TRM Labs)
    → Block order fulfillment if wallet is SDN-listed
```

## EU MiCA CASP analysis

```
MiCA (EU 2023/1114) — CASP authorization required for:
  → Custody and administration of crypto-assets
  → Operation of a trading platform
  → Exchange for funds or other crypto-assets
  → Transfer services on behalf of clients
  (Full enforcement: 30 December 2024)

example project payment-only model:
  → Does not custody user crypto
  → Does not operate an exchange
  → Does not transfer crypto on behalf of users
  → NOWPayments performs conversion; platform receives fiat

  Conclusion: example project in payment-only mode is a MERCHANT,
  not a CASP. MiCA CASP authorization is NOT required.

  Risk triggers (would cross into CASP):
    → Platform stores crypto in wallets on behalf of users
    → Platform enables user-to-user crypto transfers
    → Platform issues its own token or stablecoin
```

## Anti-patterns

- **Assuming the payment processor handles all compliance** —
  OFAC strict liability means the platform cannot fully
  delegate sanctions screening. Require it contractually AND
  screen independently as defense-in-depth.
- **Holding crypto in platform-controlled wallets** — converts
  the platform from merchant to VASP/MSB, triggering Travel
  Rule, FinCEN registration, and potentially MiCA CASP
  authorization.
- **Issuing platform tokens or loyalty crypto** — token
  issuance is the fastest path to FinCEN MSB "crypto
  administrator" classification and MiCA issuer obligations.

## Gotchas

- **NOWPayments is not US-incorporated** — verify their OFAC
  compliance posture in the merchant agreement. Non-US
  processors may not apply US sanctions by default.
- **Solana transaction finality is fast (~400ms)** — sanctions
  screening must happen before confirming order fulfillment,
  not asynchronously. Gate fulfillment on the webhook, not
  the blockchain confirmation event.
- **IRS Form 1099-DA (new 2025)** — if the platform ever
  receives crypto directly (not fiat), broker reporting rules
  apply. Merchant-only fiat receipt is ordinary income.
- **State money transmitter licenses** — separate from FinCEN
  federal MSB registration. If the platform crosses into MSB
  territory, licenses may be needed in 40+ states; New York
  BitLicense is the most restrictive.

## Verification

- Platform never holds crypto in platform-controlled wallets.
- NOWPayments merchant agreement requires OFAC SDN screening.
- Platform independently screens wallet addresses from payment
  webhooks against OFAC SDN list before fulfilling orders.
- Platform does not issue tokens or custodial wallets.
- Legal memo on file confirming merchant-only classification.

## Related

- `documentation/docs/policies/issues/mica-cryptocurrency-enforcement-2026.md`
- `documentation/docs/policies/payments/anti-money-laundering-kyc.md`
- `documentation/docs/policies/compliance/pci-dss-v4-requirements.md`
- `documentation/docs/policies/issues/user-privacy-law-enforcement-requests.md`

## Source URLs (verified 2026-08-17)

- FinCEN MSB definition (31 CFR § 1010.100)
  — https://www.ecfr.gov/current/title-31/part-1010/section-1010.100
- FinCEN virtual currency guidance (FIN-2013-G001)
  — https://www.fincen.gov/sites/default/files/shared/FIN-2013-G001.pdf
- FATF Updated Guidance on VASPs (2021)
  — https://www.fatf-gafi.org/content/dam/fatf-gafi/guidance/Updated-Guidance-VA-VASP.pdf
- EU MiCA Regulation (EU 2023/1114)
  — https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R1114
- OFAC SDN list — cryptocurrency addresses
  — https://ofac.treasury.gov/specially-designated-nationals-and-blocked-persons-list-sdn-human-readable-lists
