# Chargeback Representment Evidence Burden

**Issue:** When a cardholder disputes a transaction through the issuer (chargeback), the merchant has the right to represent the transaction back to the issuer with evidence supporting the validity of the charge. The representment process is governed by the card networks' reason codes and procedural rules; each reason code (Visa CE 3.0, Mastercard ECM, Amex, Discover) has its own evidence requirements and time windows. The merchant's representment win rate depends on the quality and timeliness of the evidence package: incomplete packages lose to the cardholder's dispute by default; well-constructed packages recover a meaningful share of chargebacks. Engineering the evidence pipeline means capturing the right artifacts at transaction time, indexing them for retrieval at representment time, and producing a complete package within the network's response window.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Evidence categories

1. **Transaction artifacts.** The signed checkout confirmation, the cart contents at the time of order, the IP address and timestamp, the AVS and CVV results, the 3DS authentication result, and the authorization code. These artifacts prove the transaction was authorized and processed in the normal flow.
2. **Fulfillment artifacts.** The shipping tracking number, the delivery confirmation, the signature on delivery (for high-value or restricted items), and the carrier's proof-of-delivery. For digital goods, the download or access log, the IP address that accessed the content, and the timestamp of access.
3. **Cardholder communication.** Pre-chargeback emails: order confirmations, shipping notifications, delivery notifications, customer-service correspondence. The communication record demonstrates that the cardholder was aware of the transaction, the product, and the delivery status before disputing.

## Reason-code-specific evidence

1. **Fraud (Visa 10.4, Mastercard 4837, Amex F24).** The cardholder claims they did not authorize the transaction. Representment evidence typically includes: AVS match, CVV match, 3DS authentication result, device fingerprint consistent with prior transactions on the same card, delivery to the cardholder's verified address, and a history of prior successful transactions on the same card.
2. **Product not received (Visa 13.1, Mastercard 4855, Amex C28).** The cardholder claims the product did not arrive. Representment evidence: proof of delivery with signature, carrier tracking showing delivery, communication with the cardholder about the delivery, and the carrier's signed delivery record.
3. **Product not as described (Visa 13.3, Mastercard 4853, Amex C32).** The cardholder claims the product does not match the listing. Representment evidence: the listing at the time of purchase (a web archive capture, not a current listing), the product description as it appeared at order time, the merchant's return policy as acknowledged at checkout, and any prior communication about the product.
4. **Duplicate charge (Visa 12.6, Mastercard 4863, Amex C18).** The cardholder claims they were charged twice. Representment evidence: the original transaction and any duplicates, with an explanation that they were for separate orders (different cart contents) or were correctly refunded.

## Time windows and process

1. **Response deadline.** The merchant typically has 7-30 days from chargeback notification to submit representment evidence. The window varies by network and reason code. Engineering must track the response deadline per chargeback case and surface it to the operations team.
2. **Channel of submission.** Most networks have moved to electronic representment platforms (Verifi/Order Insight for Visa, the Ethoca/Consumer Clarity network, Mastercard's Collaboration platform). The merchant submits the evidence package via the acquirer's portal or API; engineering must integrate the submission path to avoid manual uploads.
3. **Pre-arbitration and arbitration.** If the issuer rejects the representment, the merchant can escalate to pre-arbitration (Visa) or arbitration (Mastercard). Each network charges a filing fee; the loser typically pays the fee. The merchant must decide whether the case has enough merit to escalate.

## Engineering controls

1. **Capture-and-index pipeline.** Every transaction must capture the evidence artifacts at order, payment, fulfillment, and post-delivery stages. The artifacts must be indexed by transaction ID for fast retrieval. A chargeback received six months after the transaction must produce the artifacts in minutes.
2. **Reason-code-aware evidence builder.** The operations team selects the reason code at representment time; the system must surface the evidence categories specific to that reason code, not a generic evidence list. A 10.4 fraud case requires different artifacts than a 13.1 product-not-received case.
3. **Time-window monitoring.** Engineering must monitor the days-to-deadline metric for each open chargeback case. A case approaching its deadline without evidence submitted must be flagged for the operations team.
4. **Auto-accept thresholds.** Some chargebacks are best auto-accepted (low-value cases with clear product-not-received signals). Engineering should expose an auto-accept threshold that the operations team can tune, with the system automatically accepting cases below the threshold and skipping representment.

## Failure modes

1. **Missing evidence at representment time.** The most common representment failure is missing evidence. If the merchant cannot produce proof of delivery or proof of authorization, the chargeback is lost regardless of the merits. Engineering must own the evidence capture pipeline, not leave it to manual processes.
2. **Late evidence submission.** A representment submitted after the deadline is rejected outright. Engineering must build deadline-aware scheduling with alerts at 7 days, 3 days, and 1 day before the deadline.
3. **Wrong reason code chosen.** The operations team may select the wrong reason code at representment, leading the issuer to reject the evidence as inapplicable. Engineering should provide a reason-code recommendation based on the chargeback description and the transaction evidence available.

## Canonical sources

1. Visa, Visa Core Rules and the Visa Dispute Monitoring and Resolution Program Guidebook (CE 3.0), current edition. https://usa.visa.com/dam/VCOM/download/about-visa/visa-rules-public.pdf
2. Mastercard, Mastercard Chargeback Guide and the Dispute Resolution Management procedures under the Mastercard Rules, current edition. https://www.mastercard.us/content/dam/mccom/global/documents/dispute-resolution-management-guide.pdf
