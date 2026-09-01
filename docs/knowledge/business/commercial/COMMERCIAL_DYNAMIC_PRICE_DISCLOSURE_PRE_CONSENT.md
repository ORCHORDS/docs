# Dynamic Price Disclosure and Pre-Consent

## Scope

This article covers the consumer disclosures and pre-consent controls that apply when a merchant changes a displayed or quoted price after the customer has begun a transaction but before payment authorization. It is anchored in the Consumer Financial Protection Bureau's Regulation E, 12 CFR Part 1005, which governs electronic fund transfers and the related pre-acquisition and authorization disclosures, and in adjacent consumer-disclosure framing under Regulation Z for credit-sale contexts. The article's purpose is to ensure that a price change between quote and authorization is properly disclosed and that the customer affirmatively consents before the merchant debits a different amount.

The scope covers dynamic-pricing contexts in which the displayed price can change before payment is taken: hospitality and lodging, transportation, fuel pumps with delayed-pump authorization, pay-at-table tablets that may add a service charge, mobile-app checkout flows that may add a tip or convenience fee, and subscription enrollment flows with proration. It does not address vending-machine coin-slug disputes, government-imposed tax changes that become effective at a documented date, or auction-style open-outcry price formation.

## Workflow or implementation guidance

When a price can change between the moment it is displayed and the moment payment is authorized, the merchant should treat the authorization screen as a disclosure surface, not merely a confirmation surface. The displayed authorization amount should be the final amount the customer will be charged for the goods or services at issue, including any mandatory fees, surcharges, taxes, gratuities, and service charges that the merchant knows about and can calculate upfront.

If the merchant must obtain pre-authorization for an amount that differs from the final charge (a "hold" or "pre-auth"), the merchant should disclose both amounts: the pre-authorization amount and the maximum amount that could ultimately be charged. The disclosure should occur before the customer authorizes the hold. Pre-authorization holds should be released in a documented timeframe and in compliance with the merchant's payment-network rules and Regulation E error-resolution procedures when the customer disputes the hold.

If the price changes after a quote but before authorization (for example, surge pricing, dynamic fuel pricing, or a recalculated service charge), the merchant should re-display the new price and obtain affirmative consent from the customer before continuing. Affirmative consent may take the form of a fresh "pay" or "confirm" tap, not merely the absence of a cancel action. The merchant's records should capture both the originally displayed price and the customer-confirmed price.

For credit-card transactions where the merchant initially displays a base amount and then authorizes a higher amount, the merchant should consider the closed-end credit disclosure framing of Regulation Z, 12 CFR Part 1026, particularly for transactions where a credit sale is being offered. Even where TILA does not directly apply, the same conspicuousness principle — that the final charge and its components are clear before the customer commits — applies.

## Controls

Establish a pre-consent control matrix that maps each dynamic-pricing context to the disclosure language, the consent mechanism, and the evidence captured. Each entry should specify which price is displayed at each step, when the customer can withdraw, and what record the merchant retains.

Technical controls should enforce: (1) the authorization amount shown to the customer equals the amount the merchant will charge; (2) any pre-authorization hold is disclosed with the maximum charge; (3) any change to a displayed price triggers a fresh consent surface; (4) the merchant retains both the originally displayed and customer-confirmed amounts; and (5) the merchant's reconciliation process detects unauthorized or unreconciled holds and releases them within a documented window.

For pay-at-table tablets and mobile-checkout flows, monitor the rate of customer-removed service charges and the rate of abandonment at the consent surface. Investigate patterns that suggest customers are consenting to charges they did not understand.

## Validation evidence

For each transaction type, retain the displayed price at each step, the consent event (with timestamp and identity), the authorization record, the final charge, and the reconciliation record. For pre-authorization holds, retain the hold record, the release record, and any customer dispute. For dynamic-pricing transactions, retain the originally displayed price and the customer-confirmed price with the delta and the reason.

Sample testing should replay a transaction through the customer journey, confirm that the disclosure is presented at each price-change point, and confirm that the consent capture matches the merchant's policy.

## Failure modes and correction

Common failures include a price that changes between display and authorization without a fresh consent surface; a "no tip" or "remove fee" option that does not actually remove the fee; a pre-authorization hold that exceeds the final charge by an undisclosed amount; a service charge presented as a tip; a price change communicated only after the customer has authorized payment; and a receipt that does not reconcile to the disclosed authorization amount.

When a defect is identified, identify the affected transactions and assess the appropriate correction under Regulation E error-resolution procedures (where the dispute is an EFT error) or under the merchant's voluntary correction policy. For systematic defects, suspend the affected flow, deploy a corrected flow, and conduct a bounded lookback.

## Limitations

This article addresses the disclosure and consent controls surrounding dynamic price changes and is not a substitute for Regulation E's full error-resolution framework, Regulation Z's closed-end credit disclosure analysis, or any state's specific disclosure or surcharge rule. Pre-authorization hold limits and release timing are governed in part by payment-network rules, which the merchant must observe alongside the consumer-disclosure framework.

## Canonical sources

- Electronic Code of Federal Regulations, **12 CFR Part 1005 (Regulation E, Electronic Fund Transfers)**: https://www.ecfr.gov/current/title-12/chapter-X/part-1005
- Electronic Code of Federal Regulations, **12 CFR Part 1026 (Regulation Z, Truth in Lending)**: https://www.ecfr.gov/current/title-12/chapter-X/part-1026
- Consumer Financial Protection Bureau, **Rules and policy** (CFPB's published Regulation E and Regulation Z guidance): https://www.consumerfinance.gov/rules-policy/
