# PSD2 SCA Exemption Traffic Analysis

**Issue:** PSD2 Strong Customer Authentication (SCA) applies to in-scope card payments in the EEA, but the Regulatory Technical Standards (RTS) on SCA and Common and Secure Communication carve out six exemption categories that acquirers and issuers can apply under defined thresholds. Exemption selection is not a single decision: each transaction is a candidate for low-value, low-risk, trusted beneficiary, recurring, secure corporate payment, or SCA-delegation exemption treatment, with fraud-rate ceilings and Transaction Risk Analysis (TRA) thresholds that differ per acquirer risk band. Engineering the analysis around exemption traffic means measuring exemption hit rate, TRA pass-through, authentication fall-back rate, and the issuer-side rejection of exemption requests, because an exemption that is declined by the issuer forces a full SCA challenge that the merchant did not plan for.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Regulatory frame

1. **Six exemption categories.** Article 16 of the Commission Delegated Regulation 2018/389 enumerates low-value (≤€30, with cumulative cap), low-risk (TRA-based, threshold varies by acquirer fraud rate), trusted beneficiary (whitelisted by the payer), recurring (subsequent installments of a fixed-amount, fixed-frequency series), secure corporate (dedicated corporate processes), and SCA delegation (outsourced to a payment initiation provider). Each has its own eligibility facts and fallback rule.
2. **TRA thresholds are acquirer-specific.** The RTS binds the low-risk exemption ceiling to the acquirer's reported card-not-present fraud rate. Above 0.13% fraud rate the merchant cannot request low-risk exemption under the lowest threshold; the higher thresholds (€100, €250, €500) are unlocked only at progressively lower fraud rates, with the loosest ceiling of €500 reserved for acquirers reporting CNP fraud at or below 0.006%. The acquirer must apply the threshold the merchant actually has access to, not the headline figure.
3. **Issuer vetoes the exemption.** A request for an exemption is exactly that — a request. The issuer reviews the merchant category, transaction context, and its own risk decision, and may reject the exemption and require full SCA. A high exemption request rate with low exemption grant rate signals misaligned TRA tuning, not infrastructure failure.

## Data needed for exemption decisioning

1. **Cardholder authentication history.** Recurring and trusted-beneficiary exemptions depend on prior successful authentications. Track the date of last successful SCA, the Authentication Reference (AR), the 3DS Server Transaction ID, and the Data Exchange Reference (DER) — the issuer uses these to validate the recurring/beneficiary chain without forcing a new challenge.
2. **Transaction context.** Amount, currency, merchant category code, cardholder billing country, and acquiring country determine whether the transaction is in scope at all. EEA-issued cards spent at non-EEA merchants may still be in scope depending on the issuer's enforcement; the analysis must classify per card BIN, not per merchant.
3. **Fraud signal payload.** The TRA exemption requires feeding issuer-acceptable risk indicators: device fingerprint, behavioral signal, historical chargeback rate, and any high-risk merchant flag. Submitting the 3DS AReq with exemption-requested but no TRA evidence is a structural mistake — issuers cannot grant the exemption and the transaction falls back to challenge.

## Operational instrumentation

1. **Funnel by exemption class.** Track the share of transactions entering the gateway that go through each exemption path versus full SCA challenge, with the count of exemption requests granted versus denied. The denied-count is the diagnostic that exposes whether the acquirer's exemption profile is aligned with the issuer's risk appetite.
2. **Threshold monitoring.** Where the acquirer operates a TRA exemption, the merchant must monitor its own CNP fraud rate because breaching the band downgrades the available ceiling. Pre-emptive alerts at 0.10%, 0.12%, and 0.13% CNP fraud rate give engineering time to retighten exemption rules before the regulatory ceiling shifts.
3. **Recurring-installment hygiene.** Many recurring-series break because the first installment was authenticated with one set of card data and a subsequent installment uses an updated card or different amount. Track per installment: amount variance from the initial authenticated amount, frequency adherence, and cardholder authentication reference continuity. Any breach is a structural exemption failure.

## Failure modes

1. **Trusted beneficiary opt-in friction.** Payer-side opt-in is required: the issuer must surface the whitelist in the authentication flow. Merchants that attempt to add payers to their trusted beneficiary list without issuer-managed opt-in are in structural violation, and exemptions will be denied.
2. **Recurring exemption misclassification.** Recurring applies only to fixed-amount, fixed-frequency series with the same payee and the same payer's authentication reference. Subscription businesses that vary amounts (metered billing, usage charges, variable tax) cannot rely on the recurring exemption and must either use the low-value exemption with a SCA fallback for ceiling breaches or request full SCA at the first transaction and store the credentials for subsequent MITs.
3. **Exemption granted but later disputed.** A SCA exemption that the issuer grants is not a fraud liability shield. Chargeback reason codes for "no SCA where required" still apply where the regulatory exemption was not actually applicable. The exemption decision must be auditable per transaction for the duration of the chargeback window.

## Canonical sources

1. European Commission, Commission Delegated Regulation (EU) 2018/389 of 27 November 2017 supplementing Directive (EU) 2015/2366 with regard to regulatory technical standards for strong customer authentication and common and secure open standards of communication. https://eur-lex.europa.eu/eli/reg_del/2018/389/oj
2. European Banking Authority, Final Report on the Technical Standards on SCA and CSC under PSD2 (EBA/RTS/2017/02). https://www.eba.europa.eu/regulation-and-policy/payment-services-and-electronic-money/regulatory-technical-standards-on-strong-customer-authentication-and-common-and-secure-communication
