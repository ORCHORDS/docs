# Commercial Invoice Payment Terms Disclosure

## Scope

This article covers the disclosure, drafting, and evidence controls that apply to payment terms on commercial invoices — the contractual instruments by which a seller demands payment from a buyer in a business-to-business context. The principal reference is Article 3 of the Uniform Commercial Code (Negotiable Instruments), particularly § 3-104 (definition of a negotiable instrument) and § 3-108 (issue of an instrument), which establish the formal requirements for a writing to function as a negotiable instrument and to be enforceable as such. The article addresses how those formal requirements, together with the merchant's payment-terms policy, should be reflected on the invoice face and in the merchant's records.

The scope covers commercial invoices issued under net-30, net-60, or net-90 terms, invoices that include a stated late fee, invoices that include a discount-for-early-payment provision (a "2/10 net 30" formulation), invoices that contemplate payment by check or electronic funds transfer, and invoices that are intended to be, or could be confused with, negotiable instruments. It does not cover consumer credit disclosures under Regulation Z, consumer lease disclosures under Regulation M, or factoring arrangements.

## Workflow or implementation guidance

Design the invoice face as a controlled document with a defined set of payment-term elements. The invoice should clearly state: the invoice number and date; the seller's legal name, address, and tax identification number; the buyer's billing and ship-to addresses; the terms of sale (Incoterms reference where appropriate); the payment terms (net days, discount terms, late-fee terms); the accepted payment methods; the currency; the total amount due; and the remittance instructions.

If the invoice is intended to function as a negotiable instrument — that is, an unconditional promise or order to pay a fixed amount of money, with or without interest, payable to order or to bearer on demand or at a definite time — it must satisfy the formal requirements of UCC § 3-104. A writing that is conditioned on the performance of a contractual obligation, that does not state a fixed amount, that does not contain an unconditional promise or order, or that is payable from a designated source may not be a negotiable instrument and may instead be a simple contract right. The merchant should know which kind of instrument it intends to issue and should not inadvertently create ambiguity.

For invoices that are not intended to be negotiable instruments, the merchant should still include the payment terms on the invoice face and should treat the invoice as the primary communication of those terms to the buyer. Late fees and discount terms should be expressed as a percentage of the unpaid balance or as a fixed amount, with the calculation basis stated. The merchant should ensure that the late-fee calculation, if any, is consistent with the governing contract and with applicable state usury or late-fee limits.

For invoices that contemplate payment by check, the merchant should not draft the invoice in a form that resembles a check (pre-printed routing and account number, a payable-to-blank line, a memo line that says "Net 30," or a signature line). Such a draft can be presented as a negotiable instrument under UCC § 3-104 and can be cashed by an unauthorized third party. The merchant should consider alternative payment instructions (electronic funds transfer, ACH, wire, or a merchant portal) where practical.

For invoices issued under a master supply agreement, the payment terms on the invoice should track the master agreement's payment-terms clause. The merchant should not unilaterally amend the payment terms on the invoice in a way that diverges from the master agreement.

## Controls

Establish an invoice-payment-terms control matrix keyed by customer, master agreement, and invoice template. Each template should reference the master agreement's payment-terms clause and should be governed by an approval workflow.

Technical controls should enforce: (1) the invoice face presents the required payment-term elements in a legible, consistent position; (2) the payment-terms logic (net days, discount terms, late fees) is calculated from a single source; (3) the merchant does not draft invoices in a form that resembles a check; (4) the merchant does not issue an invoice that purports to be a negotiable instrument when it does not satisfy UCC § 3-104; and (5) any change to the payment terms between invoices is approved and communicated to the buyer in writing.

Monitor late-payment rates, discount-take rates, disputes over payment terms, and complaints about invoice clarity. Investigate patterns that suggest the invoice face does not match the master agreement, that the late-fee calculation is inconsistent with the contract, or that an invoice was issued in a form that resembles a check.

## Validation evidence

Retain the master agreement's payment-terms clause, the invoice template versions, the issued invoices, the payment records, the late-fee applications, the discount applications, and any customer dispute correspondence. The merchant should be able to reconstruct the payment terms applicable to any historical invoice and demonstrate that the late fees and discount terms applied were consistent with the agreed terms.

Sample testing should retrieve a sample of invoices, confirm the payment terms match the master agreement, confirm the late-fee and discount calculations are correct, and confirm the invoice is not drafted in a form that resembles a check.

## Failure modes and correction

Common failures include an invoice face that omits the net days or the discount terms; a late-fee calculation that exceeds the contract or the state's usury or late-fee limit; a payment-terms clause in the master agreement that is contradicted by the invoice face; an invoice drafted in a form that resembles a check and is cashed by an unauthorized party; an invoice that purports to be a negotiable instrument but does not satisfy UCC § 3-104 and is later treated by the courts as a simple contract right; and a payment-terms amendment communicated only on the invoice face rather than by separate written notice to the buyer.

When a defect is identified, identify the affected invoices and the affected customers. Refund or reverse impermissible late fees; correct the invoice template and the master-agreement reference. For systematic defects, escalate to qualified counsel and conduct a bounded lookback.

## Limitations

This article addresses invoice-face payment-term disclosures and adjacent formal-instrument concerns under UCC Article 3, and is not a substitute for the merchant's master supply agreement, the UCC's other articles (in particular Article 2 on sales and Article 9 on secured transactions), or state-specific usury or late-fee limits. Where the invoice is governed by the law of a state that has not adopted the latest revision of Article 3, that state's law controls.

## Canonical sources

- Cornell Law School Legal Information Institute, **Uniform Commercial Code § 3-104 (Negotiable instrument)**: https://www.law.cornell.edu/ucc/3/3-104
- Cornell Law School Legal Information Institute, **Uniform Commercial Code § 3-108 (Issue)**: https://www.law.cornell.edu/ucc/3/3-108
- Cornell Law School Legal Information Institute, **Uniform Commercial Code Article 3 (Negotiable Instruments)** (full article context): https://www.law.cornell.edu/ucc/3
