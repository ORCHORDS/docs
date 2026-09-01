# Store Credit Expiry Communication

## Scope

This article covers the disclosure, communication, and recordkeeping controls that apply when a merchant issues store credit to a consumer and that store credit carries an expiration date, dormancy treatment, or other condition that may extinguish the consumer's right to redeem. The principal reference is the FTC Negative Option Rule, 16 CFR Part 425, which the Commission has read to cover certain merchant-issued credit balances that are contingent on the consumer's affirmative action (such as a "use by" date) to preserve value. The article applies that rule's disclosure and consent framework to store-credit programs as a structural baseline, alongside the general Section 5 unfair-or-deceptive-practices principle.

The scope covers merchant-issued store credit arising from returns, exchanges, refunds, warranty adjustments, gift-card conversions, and promotional credits. It does not address retailer-branded gift cards subject to the FTC Gift Card Rule (16 CFR Part 305), bank-issued prepaid cards subject to Regulation E (12 CFR Part 1005), or state-specific unclaimed-property escheatment.

## Workflow or implementation guidance

Treat each store-credit issuance as a controlled event with a defined communication surface. At issuance, the consumer should receive clear and conspicuous disclosure of (a) the amount of the credit; (b) the form of the credit (physical certificate, digital code, account balance, in-store credit); (c) the scope of the credit (single store, banner group, online or in-store only); (d) the expiration date or the rule that determines the expiration date (for example, "no expiration" or "12 months from issuance" or "the date printed on the certificate"); (e) any dormancy, inactivity, or maintenance fee; (f) the procedure for re-issuing a lost or stolen credit; and (g) the merchant's contact information for inquiries.

If the store credit carries a redemption-by date, the merchant should provide reasonable advance notice before the expiration event, through a channel the consumer has affirmatively agreed to. Notice timing should be consistent with the consumer's reasonable expectation based on the program's stated terms. Where the original disclosure did not include an expiration rule, the merchant should not impose one unilaterally; a unilateral imposition can render the original issuance representation misleading.

For store credit issued as part of a return, the disclosure of the credit terms should be presented at the moment the merchant offers the credit, before the consumer accepts. A consumer who is offered store credit in lieu of a refund should be able to compare the credit terms (amount, expiration, scope) to the refund terms and to make an informed choice.

For promotional credits (sign-up credit, loyalty credit, birthday credit), the merchant should ensure that the promotional terms disclosed at sign-up match the credit terms at issuance. A promotional representation of "free $10 credit" that is then issued as a $10 credit expiring in seven days can create a misleading-disclosure issue if the seven-day expiration was not part of the original promotional representation.

Store-credit records should be reconcilable to the underlying return, refund, or promotional event. The merchant should be able to demonstrate, for any historical store credit, when it was issued, on what terms, what communications were sent to the consumer, and when it expired or was redeemed.

## Controls

Establish a store-credit control matrix that maps each product or program to the credit form, the disclosure surface, the expiration rule, the dormancy rule, and the notice rule. Each issuance event should be logged with the credit identifier, the disclosure version, and the channel.

Technical controls should enforce: (1) the credit's expiration date (if any) is consistent with the disclosed rule; (2) the dormancy or inactivity rule (if any) is consistent with the disclosure and applied only after the disclosed threshold; (3) the advance notice is sent through the consumer-affirmative channel and within the disclosed window; (4) the store credit cannot be unilaterally expired or forfeited outside the disclosed rule; (5) the merchant can demonstrate that each issuance event produced the required disclosures; and (6) the store-credit balance is reconcilable to the underlying return, refund, or promotion.

Monitor consumer complaints, dispute volume, and regulatory inquiries about store credit. Investigate patterns that suggest credits are expiring sooner than disclosed, expiring without notice, or being unilaterally imposed contrary to the issuance representation.

## Validation evidence

Retain the issuance disclosure versions, the issuance logs, the expiration records, the notice records, and the redemption records for each store credit. For regulatory purposes, the merchant should be able to demonstrate that each consumer received the disclosed treatment.

Sample testing should retrieve a sample of issued credits, confirm the disclosure content matches the approved version, confirm the expiration rule matches the disclosure, confirm the advance notice was sent within the disclosed window, and confirm the credit was redeemed or expired consistent with the disclosed rule.

## Failure modes and correction

Common failures include a store-credit balance issued without an expiration disclosure but later subjected to an expiration policy; an expiration policy that is disclosed at issuance but not enforced consistently; a credit that is expired without the disclosed advance notice; a credit that is unilaterally forfeited contrary to the issuance disclosure; a credit that is offered in lieu of a refund without a clear comparison of terms; and an issuance disclosure that lists a discount or promotion that does not match the actual credit terms.

When a defect is identified, identify the affected credits and the affected consumers. Restore lost value where the disclosed treatment was not honored, and consider goodwill remediation. Update the issuance disclosure and the credit platform so that the corrected treatment is consistently applied. For systematic defects, escalate to qualified counsel and conduct a bounded lookback.

## Limitations

This article addresses the disclosure and platform-enforcement controls surrounding store-credit expiration and dormancy, and is not a substitute for state-specific consumer-protection, unclaimed-property, gift-card, or prepaid-card rules. The Negative Option Rule framework is used here as a structural baseline; the merchant should evaluate each store-credit program against the rule's specific definitions and the FTC's published guidance, and should seek counsel where the program's structure presents a close question.

## Canonical sources

- Electronic Code of Federal Regulations, **16 CFR Part 425 (Negative Option Rule)**: https://www.ecfr.gov/current/title-16/chapter-I/subchapter-B/part-425
- Federal Trade Commission, **Negative Option Rule landing page** (rule summary and business guidance): https://www.ftc.gov/legal-library/browse/rules/negative-option-rule
- Electronic Code of Federal Regulations, **16 CFR Part 305 (Gift Card Rule)** for the adjacent framework that applies to merchant-issued gift cards, which is structured similarly but governed by a separate rule: https://www.ecfr.gov/current/title-16/chapter-I/subchapter-B/part-305
