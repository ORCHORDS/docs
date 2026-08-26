# mica-regulation

**Issue:** MiCA (Markets in Crypto-Assets Regulation) EU 2023/1114 — crypto-asset service obligations
**Date:** 2026-08-11
**Status:** documented

## Symptom
example.com is considering NFT features or a
creator token economy. Someone asks if MiCA
applies. You say "probably not, NFTs are excluded."
But the answer depends on whether the NFT is
really fungible in disguise. The fine is up to
€5M or 3% of annual turnover.

## Root cause
**MiCA Regulation (EU) 2023/1114 is fully in force.**
Title III and IV (ART/EMT issuers) from 30 June 2024.
Title V (CASPs) from 30 December 2024.

**Source:** EUR-Lex 2023/1114:
https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R1114

## The "asset categories" pattern (Art. 2-3)

For three MiCA asset types:
1. **Asset-Referenced Tokens (ARTs):** Backed by
   basket of currencies, commodities, crypto
   (e.g. a stablecoin backed by EUR+USD)
2. **E-Money Tokens (EMTs):** Pegged 1:1 to a
   single fiat currency (e.g. USDC, EURC)
3. **Other crypto-assets:** Everything else —
   utility tokens, access tokens, fan tokens

**NFTs** are explicitly excluded (Recital 6, Art. 2(3)):
"unique, not fungible with other crypto-assets"
are outside scope. But: if issued in a large
series where individual items are identical or
near-identical, regulators may treat them as
fungible → in scope.

## The "exclusions" pattern (Art. 2)

For what is excluded from MiCA:
- **True NFTs** — unique, non-fungible, single purpose
- **DeFi protocols** — fully decentralised, no issuer
- **CBDCs** — central bank digital currencies
- **Financial instruments** under MiFID II
- **Securitisation positions** under EMIR
- **Deposits** under Deposit Guarantee Schemes
- **Small issuances** — crypto-assets with <€1M
  aggregate value over 12 months (Art. 4(2)(b))

## The "CASP authorisation" pattern (Title V, Art. 59)

For Crypto-Asset Service Providers (CASPs):
- **Authorisation required** to provide services in EU
- **CASP services (Art. 3(1)(16)):**
  - Custody and administration
  - Operation of trading platforms
  - Exchange for fiat currency
  - Exchange for other crypto-assets
  - Order execution
  - Placing crypto-assets
  - Reception and transmission of orders
  - Providing advice
  - Portfolio management
  - Transfer services

If example.com runs a marketplace where users
buy/sell creator tokens for EUR → this is exchange
for fiat → CASP authorisation required.

## The "white paper" pattern (Art. 4-19)

For other crypto-asset issuers (not ART/EMT):
- **Mandatory white paper** before offering
- **Contents (Annex I):** Issuer info, project,
  rights granted, risks, underlying tech, tokenomics
- **File with NCA** at least 20 working days before
  offering (Art. 8)
- **No prior approval needed** — NCA can object
- **Liability:** Issuer liable if white paper is
  misleading, inaccurate, or incomplete (Art. 15)
- **Exemptions:** Offers <150 persons per member state,
  total <€1M over 12 months, free tokens (airdrops),
  mining rewards, employee tokens

## The "fines" pattern (Art. 111-114)

For fines on CASPs:
- Up to **€5M** or **3% of annual turnover**
  (whichever higher) for most infringements
- Up to **€700k** for natural persons

For white paper violations:
- Up to **€5M** or **3% of turnover**

## The "NFT risk" pattern

For example.com NFT feature assessment:
- **Single edition, unique content** (1/1 art NFT): excluded
- **Limited edition series** (e.g. 10,000 identical
  profile pictures): likely excluded if genuinely unique
- **Fractionalised NFTs** or **NFT bundles** that behave
  as fungible instruments: likely in scope as "other
  crypto-asset" → white paper required
- **Creator subscription tokens** (access to content
  for recurring fee): likely "utility token" → white
  paper required unless exempt

## What example.com must do

1. **Legal classification first:** For every planned
   token/NFT feature, obtain legal opinion on whether
   it is a MiCA crypto-asset or a genuine NFT.
2. **NFT design:** Ensure NFTs are genuinely unique
   and non-fungible. Avoid large-series identical
   drops without legal review.
3. **Utility tokens:** If issuing creator access
   tokens, assess white paper requirement. If
   aggregate value <€1M/year, use the small-issuance
   exemption (Art. 4(2)(b)) and document it.
4. **No exchange service:** Do not operate a
   EUR↔token exchange without CASP authorisation.
   Use established CASP as intermediary.
5. **Secondary market:** If facilitating peer-to-peer
   resale of tokens for fiat, seek CASP advice.
6. **UK parallel:** The UK FCA's crypto regime (under
   FSMA 2023) is separate. MiCA passport does not
   cover UK. Assess UK cryptoasset registration
   separately if example.com serves UK users.
