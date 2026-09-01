# Chargeback Time-Limit Calendars

**Issue:** Each card network imposes time limits on when a cardholder can file a chargeback, when the merchant can respond, and when the network's arbitration process can be invoked. The time limits differ by network (Visa, Mastercard, Amex, Discover, JCB), by reason code (fraud, product not received, product not as described, duplicate, credit not processed), and by transaction type (card-present, e-commerce, recurring). Misalignment of the merchant's representment deadline with the network's calendar causes automatic loss of the dispute even when the evidence is strong. Engineering the time-limit tracking means understanding the network calendars, encoding them as configuration rather than hard-coded logic, and surfacing per-chargeback deadlines to the operations team with sufficient lead time to prepare the response.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Network calendars

1. **Visa CE 3.0.** Cardholder dispute window: 120 days from the transaction date or expected delivery date, depending on reason code. Merchant representment window: 30 days from chargeback notification (Visa Dispute Time Limits). Pre-arbitration: 30 days from representment rejection. Arbitration: 30 days from pre-arbitration rejection. All windows are calendar days, not banking days.
2. **Mastercard dispute resolution.** Cardholder dispute window: 120 days from transaction date, with reason-code-specific variations (4853 product not as described has a 120-day window from delivery, 4837 fraud has a 120-day window from transaction). Merchant representment window: 45 days from chargeback notification. Pre-arbitration and arbitration follow with similar windows.
3. **American Express dispute resolution.** Cardholder dispute window: 120 days, with reason-code-specific exceptions. Merchant response window: 20-30 days depending on the dispute type. Amex's process is more direct than Visa/Mastercard, with fewer escalation stages.

## Reason-code variations

1. **Fraud (10.4, 4837, F24).** The shortest cardholder windows. The cardholder has a defined period from the transaction date or from the date the card was reported compromised. The merchant must respond with the full fraud-defense evidence package: AVS, CVV, 3DS, device fingerprint, shipping, signature.
2. **Product not received (13.1, 4855, C28).** Cardholder window typically starts from the expected delivery date, not the transaction date. Engineering must capture the expected delivery date in the transaction record so that the time-limit calculator can use it as the anchor.
3. **Product not as described (13.3, 4853, C32).** Cardholder window starts from the delivery date or from the date the issue was identified, depending on the network. Engineering must capture the actual delivery date so that the time-limit calculator does not anchor to the wrong date.
4. **Credit not processed / duplicate.** Cardholder window is the shortest, often 30-90 days from the date the credit was expected. Engineering must process refunds promptly to avoid opening this dispute category.

## Banking days versus calendar days

1. **Most windows are calendar days.** Chargeback windows count calendar days including weekends and holidays. A dispute notification received on a Friday does not get an additional weekend buffer; the deadline is counted from the notification date.
2. **Network "extended" windows for certain reason codes.** Some reason codes (typically fraud) allow an extended window when the cardholder reports the card compromise late. The extension is conditional on the cardholder providing evidence of the compromise date; engineering should expect this on a minority of cases and not let the standard 120-day window be the only calendar tracked.
3. **Merchant response calendar.** Most merchant response windows are also calendar days. Engineering must use a calendar-day counter for merchant deadlines, not a banking-day counter.

## Engineering controls

1. **Per-chargeback deadline computation.** Each chargeback notification must produce a deadline timestamp on receipt. The deadline computation uses the network, the reason code, the transaction date, and the delivery date. Engineering should store the deadline on the chargeback record and surface it to the operations UI.
2. **Calendar refresh.** Network calendars are updated periodically. The Mastercard dispute window for 4853 (product not as described) was extended in a recent rule update; the merchant's calendar configuration must be versioned and reviewed against the network's current rules.
3. **Alert cadence.** Engineering must alert the operations team at 7 days, 3 days, and 1 day before the deadline, with an escalation alert if no evidence has been collected. The alerts must go to the case owner and to a backup assignee.

## Failure modes

1. **Anchoring to transaction date for delivery-anchored reason codes.** Using the transaction date as the anchor for product-not-received or product-not-as-described disputes produces an incorrect deadline — typically shorter than the actual allowed window, leading to early escalations or to missed representment opportunities.
2. **Static calendar configuration.** Hard-coded time limits in application code are wrong on the day the network updates its rules. The calendar configuration must be externalized and reviewed quarterly against the network's published dispute rules.
3. **Weekend-deadline slippage.** A deadline that falls on a Sunday or a holiday may receive late submission because the operations team is offline. Engineering should surface a "soft deadline" of one calendar day before the hard deadline for cases near weekends or holidays.

## Canonical sources

1. Visa, Visa Core Rules and Visa Dispute Monitoring and Resolution Program, including the dispute time limits schedule, current edition. https://usa.visa.com/dam/VCOM/download/about-visa/visa-rules-public.pdf
2. Mastercard, Mastercard Dispute Resolution Management Guide and the Customer Interface Specification time-limit tables, current edition. https://www.mastercard.us/content/dam/mccom/global/documents/dispute-resolution-management-guide.pdf
