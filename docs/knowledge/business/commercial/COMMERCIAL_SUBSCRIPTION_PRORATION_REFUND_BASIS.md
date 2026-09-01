# Subscription Proration and Refund Basis

## Scope

This article covers the calculation, disclosure, and evidence controls that govern how a subscription merchant computes a prorated refund, a cancellation credit, or a fee for early termination when a consumer cancels a subscription. The principal reference is the FTC Negative Option Rule, 16 CFR Part 425, which governs offers or sales of goods or services that continue unless the consumer takes affirmative action to cancel. The rule requires clear disclosure of the material terms of the negative-option feature before the consumer pays, an affirmative-consent mechanism, and a simple cancellation mechanism.

The scope covers continuous-service subscriptions (monthly boxes, streaming, software-as-a-service), membership programs that renew automatically, consumable replenishment, free-trial-to-paid conversions, and prepaid subscription programs. It does not address consumer leases governed by 12 CFR Part 1013 (Regulation M), consumer credit cards governed by Regulation Z, or installment loans.

## Workflow or implementation guidance

Design the proration and refund policy at the same time the negative-option enrollment flow is designed. The enrollment flow must (i) clearly disclose the material terms of the negative-option feature, including the recurring charge, the billing interval, the cancellation mechanism, and any cancellation fee or refund-treatment; (ii) obtain the consumer's affirmative consent to those terms before charging; and (iii) make the cancellation mechanism simple and discoverable after the consumer has enrolled.

The proration or refund basis should be expressed in the enrollment disclosure: is the refund prorated by days, by billing cycles, by usage, by delivered shipments, or none at all? Is there a cancellation fee? Are partially used periods refunded or treated as fully consumed? Are annual subscriptions eligible for a refund beyond the cooling-off period, and if so, on what basis?

For proration by days, the merchant should use the actual number of days in the billing period rather than a nominal 30-day month, so that the per-day rate is consistent across months of different lengths. For proration by delivered shipments, the merchant should clearly state which shipments count toward the consumed value. For a non-refundable first month, the merchant should clearly disclose that the first month's charge is non-refundable and should not describe the program as cancellable at any time if cancellation does not result in a refund of the most recent charge.

The cancellation mechanism must be at least as easy as the enrollment mechanism. A customer who enrolled with one click should be able to cancel with one click or one call, and the cancellation mechanism should not require the customer to navigate away from the cancellation path to find a fee, an opt-in, or a survey.

For refunds, the merchant should use the same payment instrument the consumer used for the original transaction, unless the consumer affirmatively agrees to another method. Refunds should be processed within a documented timeframe consistent with the merchant's policy and any applicable payment-network rules. The merchant's refund record should be auditable: who requested the refund, when it was processed, the basis for the refund amount, and the payment instrument to which the refund was issued.

## Controls

Establish a proration and refund control matrix keyed by subscription product, enrollment cohort, and policy version. Each enrollment event should reference the policy version in effect at the time. Each cancellation event should reference the policy version applied to compute the refund or fee.

Technical controls should enforce: (1) the enrollment flow presents the negative-option disclosures in close proximity to the consent surface; (2) the consumer's affirmative consent is captured and stored; (3) the cancellation mechanism is at least as easy as the enrollment mechanism; (4) the proration or refund calculation uses the policy version in effect at the time of cancellation; (5) the refund is issued to the original payment instrument unless the consumer agrees otherwise; (6) the cancellation record references the policy version applied and the calculation inputs.

Monitor cancellation friction (time to cancel, support contacts required), refund volume, and complaints or chargebacks tied to "unrecognized subscription." Investigate patterns that suggest the cancellation mechanism is more difficult than the enrollment mechanism or that the disclosed refund terms do not match the actual refund issued.

## Validation evidence

Retain the enrollment disclosure versions, the affirmative-consent records, the cancellation records, the refund calculations, the refund payment records, and the policy-version references. For regulatory purposes, the merchant should be able to demonstrate that each consumer received the disclosed cancellation treatment.

Sample testing should retrieve a sample of cancellation events, confirm the cancellation record references the policy version in effect, recalculate the refund independently, and verify that the amount matches the disclosed policy.

## Failure modes and correction

Common failures include an enrollment flow that discloses the negative-option terms but obtains consent on a separate surface; a cancellation flow that requires the consumer to call a phone number when enrollment was online; a "free trial" that converts to a paid charge without the consumer's affirmative consent to the recurring charge; a proration calculation that uses a 30-day month rather than the actual billing period; a cancellation fee not disclosed at enrollment; a refund issued to a different payment instrument without consumer agreement; and a policy amendment applied retroactively to existing subscribers.

When a defect is identified, identify the affected consumers by enrollment cohort and date range. Refund amounts that were not authorized by the disclosed policy, restore lost service where the cancellation was improperly rejected, and consider goodwill remediation. Update the enrollment flow, the cancellation flow, and the proration calculation so that the corrected treatment is consistently applied. For systemic defects, escalate to qualified counsel and conduct a bounded lookback.

## Limitations

This article addresses the disclosure, consent, and refund controls surrounding subscription cancellation and is not a substitute for state-specific consumer-protection laws, payment-network rules on refunds, or tax-treatment of cancellation fees. The Negative Option Rule applies to specific structures of offer and sale; the merchant should evaluate each subscription product against the rule's definitions rather than assume coverage.

## Canonical sources

- Electronic Code of Federal Regulations, **16 CFR Part 425 (Negative Option Rule)**: https://www.ecfr.gov/current/title-16/chapter-I/subchapter-B/part-425
- Federal Trade Commission, **Negative Option Rule landing page** (rule summary and business guidance): https://www.ftc.gov/legal-library/browse/rules/negative-option-rule
- Consumer Financial Protection Bureau, **Rules and policy** (adjacent consumer-disclosure framing where the subscription involves credit): https://www.consumerfinance.gov/rules-policy/
