# Gift Card Expiry Disclosure

## Scope

This article covers the consumer-facing disclosures and merchant-side controls that apply to gift cards, store gift cards, general-use prepaid cards, and certificate programs subject to the Federal Trade Commission's Gift Card Rule, 16 CFR Part 305. The rule limits dormancy, inactivity, and service fees on gift cards and requires specific disclosures about expiration, fees, and the process for replacing a lost or stolen card. The article addresses issuance disclosures, point-of-sale presentation, on-card text, packaging, and online terms.

The scope covers traditional plastic gift cards sold at retail, virtual gift cards delivered by email or SMS, gift cards issued through loyalty programs that meet the rule's definition, and store-branded gift cards used only at the issuing merchant. It does not address prepaid cards issued by a bank or other financial institution that are subject to Regulation E (12 CFR Part 1005) rather than the FTC Gift Card Rule; prepaid debit cards linked to a deposit account are governed by the CFPB rather than the FTC.

## Workflow or implementation guidance

Treat the issuance of a gift card as a controlled event that produces both the underlying value record and the consumer-facing disclosures required by the rule. At the point of issuance, the consumer must receive clear and conspicuous disclosures of (a) the fact that the card does not expire, or, if the card is subject to an expiration date permitted by the rule, that date; (b) the fee schedule that applies, including dormancy, inactivity, and service fees, and the conditions under which they will be imposed; (c) the procedure for replacing a lost or stolen card, including the information the consumer must provide; and (d) the issuer's contact information for inquiries.

If the card has an expiration date for funds, that date must be at least five years from the date of issuance or the date funds were last loaded. If the card has an expiration date for the plastic (separate from the funds), the rule permits the card to expire on a shorter horizon so long as the consumer can be issued a replacement card without charge and the funds do not expire. Both scenarios must be reflected in the disclosure.

Disclosures should be presented in close proximity to the purchase decision, before the consumer pays. They may appear on the card itself, on the packaging, on a separate disclosure sheet, or in an equivalent online or mobile surface that the consumer reaches before purchase. The disclosure text should not be embedded in a long terms-of-use document that the consumer is unlikely to read.

For virtual cards, the same disclosures should be presented on the purchase-confirmation surface and in the email or SMS that delivers the card. The virtual representation should not rely on a click-through link to a separate terms page as the sole means of disclosure.

For loyalty-program-issued cards that fall within the rule, the disclosures must accompany the issuance event, not merely be available in the program's general terms.

## Controls

Establish a gift-card issuance control matrix that maps each product (plastic, virtual, loyalty) to the disclosure surfaces, the disclosure text version, and the fee schedule. Each issuance event should be logged with the card identifier, the disclosure version, the channel, and the timestamp.

Technical controls should enforce: (1) a card does not have a funds expiration date earlier than the rule's minimum; (2) dormancy and inactivity fees are not imposed until the rule's minimum dormancy period has elapsed and only after the consumer has been notified; (3) a lost or stolen card replacement request is processed in a documented window with the information required by the rule; (4) the disclosure text on the card and the disclosure text in the system match the approved version; and (5) the merchant can demonstrate that each issuance event produced the required disclosures.

Audit dormancy-fee schedules, replacement-fee schedules, and any expiration-date assignments. Investigate patterns of dormancy fees applied shortly after issuance or before the rule's threshold.

## Validation evidence

Retain the approved disclosure text versions, the issuance logs, the fee-schedule snapshots, and the replacement-request records for each card. For audit purposes, the merchant should be able to demonstrate that each card was issued with a disclosure that meets the rule and that each fee applied to a card was permitted by the rule.

Sample testing should retrieve a card from each product, confirm the disclosure content matches the approved version, confirm the fee schedule matches the disclosure, and confirm the expiration treatment matches the rule.

## Failure modes and correction

Common failures include applying a dormancy or inactivity fee before the rule's minimum dormancy period has elapsed; failing to disclose a fee that the merchant actually charges; imposing a fee for replacing a lost or stolen card that the rule does not permit; setting a funds-expiration date earlier than the rule's minimum; relying on a buried terms-of-use link as the only disclosure surface; and failing to deliver virtual-card disclosures in the delivery message itself.

When a defect is identified, identify the affected cards by issuance channel, date range, and product. Refund any impermissible fees with documented evidence. Update the disclosure text and the fee schedule so that the corrected treatment is consistently presented. For systemic defects, escalate to qualified counsel and conduct a bounded lookback across the affected population.

## Limitations

This article addresses the FTC Gift Card Rule's disclosure and fee limits and is not a substitute for state-specific gift card laws (some of which provide stronger protections, including prohibitions on expiration or limits on replacement fees) or for unclaimed-property escheatment rules. The CFPB's Regulation E applies to a different set of prepaid products, and the consumer protections for those products differ.

## Canonical sources

- Electronic Code of Federal Regulations, **16 CFR Part 305 (Gift Card Rule)**: https://www.ecfr.gov/current/title-16/chapter-I/subchapter-B/part-305
- Federal Trade Commission, **Consumer information on gift cards**: https://consumer.ftc.gov/articles/gift-cards
- Electronic Code of Federal Regulations, **12 CFR Part 1005 (Regulation E)** for the adjacent prepaid-account framework that applies to bank-issued prepaid cards: https://www.ecfr.gov/current/title-12/chapter-X/part-1005
