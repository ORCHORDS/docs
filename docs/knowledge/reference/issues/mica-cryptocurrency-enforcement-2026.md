# MiCA Cryptocurrency Regulation — 2026 Enforcement

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your crypto-asset service provider (CASP) or stablecoin issuer operates in
the EU without MiCA authorization. As of 2026, unauthorized issuers face
delisting from EU-regulated platforms, and the first wave of administrative
fines has been issued. The transition period is over — compliance is now
mandatory.

## Context

The Markets in Crypto-Assets Regulation (EU 2023/1114, "MiCA") is the EU's
comprehensive framework for regulating crypto-assets. Stablecoin rules
(Titles III and IV) applied from 30 June 2024. The full regulation,
including CASP authorization requirements, became fully effective on
30 December 2024. By August 2026, enforcement has shifted from rule-
clarification to active supervision and penalties.

## Stablecoin framework

MiCA governs stablecoins under two classes:

| Type | Definition | Authorization |
|---|---|---|
| **E-money tokens (EMTs)** | Pegged to a single fiat currency | Issuer must be an authorized credit institution or electronic money institution (EMI) |
| **Asset-referenced tokens (ARTs)** | Backed by a basket of assets (fiat, commodities, crypto) | Requires specific MiCA authorization from a national competent authority |

### Reserve requirements

- EMT reserves must be bankruptcy-remote and held with qualifying
  custodians.
- ART reserves must be segregated, liquid, and subject to independent
  audits.
- Significant EMTs/ARTs (market cap > EUR 5B or > 10M holders) face
  enhanced requirements including EBA direct supervision.

## CASP authorization

All crypto-asset service providers operating in the EU must obtain MiCA
authorization from their home member state's national competent authority.
Services requiring authorization include:

- Custody and administration of crypto-assets
- Operation of a trading platform
- Exchange of crypto-assets for funds or other crypto-assets
- Execution of orders and placement
- Providing advice and portfolio management
- Transfer services

### Authorization deadline

ESMA set a firm authorization deadline of **1 July 2026** for all
stablecoin issuers. Any issuer that fails to secure full MiCA authorization
by that date is delisted from EU-regulated platforms.

## 2026 enforcement status

As of March 2026:

- **19 authorized EMT issuers** across 11 countries, issuing 29 e-money
  tokens.
- The first 18 months of enforcement have produced delistings, withdrawn
  authorizations, and administrative fines.
- Smaller CASPs have exited the market or merged — compliance costs have
  driven consolidation.

## Anti-patterns

- **Operating without authorization** — the transition period is over.
  Unauthorized CASPs face fines up to EUR 5M or 3% of annual turnover
  (for legal entities) and potential criminal liability in some member
  states.
- **Non-compliant stablecoin reserves** — holding reserves in volatile
  assets or without proper segregation violates reserve requirements and
  can trigger immediate suspension.
- **Ignoring whitepaper requirements** — MiCA requires a crypto-asset
  whitepaper with specific disclosures (risks, technology, rights) before
  offering tokens to the public. Failure to publish or publishing
  misleading information carries liability.
- **Cross-border assumptions** — MiCA authorization in one member state
  grants passporting rights across the EU, but this requires proper
  notification to host authorities.

## Gotchas

- **DeFi exemption is narrow** — truly decentralized protocols without an
  identifiable service provider may fall outside MiCA, but any interface,
  governance token, or DAO with identified participants may be in scope.
  The boundary is unclear and being tested.
- **NFTs** — unique, non-fungible crypto-assets are generally excluded from
  MiCA, but fractional NFTs or large collections of functionally fungible
  NFTs may be reclassified as crypto-assets.
- **Travel Rule** — MiCA incorporates the FATF Travel Rule (Regulation
  2023/1113, "Transfer of Funds Regulation"). CASPs must collect and
  transmit originator and beneficiary information for crypto transfers.
- **Marketing restrictions** — marketing communications must be fair,
  clear, and not misleading, and must be clearly identifiable as such.
  Influencer marketing of crypto-assets without proper disclosures
  triggers enforcement.

## Verification

- CASP authorization is obtained and published on the national authority's
  register.
- Stablecoin reserves are audited and compliant with segregation
  requirements.
- Crypto-asset whitepaper is published and meets MiCA disclosure
  requirements.
- Travel Rule compliance is implemented for all crypto transfers.
- Marketing materials are reviewed for MiCA compliance.
- AML/KYC procedures are integrated with CASP operations.

## Related

- `documentation/docs/policies/compliance/pci-dss-v4-requirements.md`
- `documentation/docs/policies/payments/anti-money-laundering-kyc.md`
- `documentation/docs/policies/compliance/eu-ai-act-article-5-prohibited-practices.md`

## Source URLs (verified 2026-08-16)

- MiCA Regulation full text — https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32023R1114
- Sumsub MiCA 2026 guide — https://sumsub.com/blog/crypto-regulations-in-the-european-union-markets-in-crypto-assets-mica/
- Hacken MiCA compliance — https://hacken.io/discover/mica-regulation/
- InnReg MiCA guide — https://www.innreg.com/blog/mica-regulation-guide
