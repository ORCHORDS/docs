# sepa-direct-debit-return-handling

**Issue:** SEPA Direct Debit is a pull instrument with unusually strong payer rights: a debtor can demand a refund of any core-scheme direct debit within 8 weeks of the debit date with no justification at all, and up to 13 months for collections taken without a valid mandate. For the merchant (creditor), this means a SEPA payment is never truly final on settlement day: revenue recognized from direct debits must be provisioned against a multi-week return window, and the engineering system must ingest R-transactions (the SEPA family of reject, return, refund, reversal, refusal, and recall messages), decode their reason codes, reverse ledger entries, and react in the subscription state machine, all potentially weeks after the original payment. The Stripe-level integration article covers accepting SEPA; this one covers what happens when the money comes back.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## R-transaction taxonomy

1. **Know the six types and their timing.** A Reject happens before settlement (the debtor bank refuses the collection, funds never move). A Return happens after interbank settlement (funds moved, then came back). A Refund is debtor-initiated via the 8-week right. A Reversal is creditor-initiated correction of their own error. A Refusal and a Recall cover refusal by the debtor bank and the creditor bank pulling the file, respectively. Your ledger reaction differs: rejects never credited revenue, returns and refunds claw back revenue that may already be recognized.
2. **Design ingestion for asynchronous arrival.** Returns typically arrive one to three business days after collection; refunds under the 8-week right can arrive up to two months later, interleaved arbitrarily with new successful debits. The reconciliation pipeline must match each R-transaction to its original collection by mandate reference plus end-to-end id (not amount), including the degenerate case where the original collection predates a system migration.
3. **Treat the B2B scheme differently.** SEPA B2B direct debit has no unconditional refund right and requires the debtor bank to mandate-check pre-validation; return profiles and reason-code distributions differ from core. Tag schemes explicitly so reporting does not blend them.

## Reason codes and automation

1. **Parse, do not string-match.** Reason codes follow the ISO 20022 structured format (for example MS03 with a proprietary issuer/code pair carrying MD01 no mandate, MS02 insufficient funds, SL01 debtor's bank name). The EPC's Guidance on Reason Codes for SEPA Direct Debit R-transactions (version 8.0, November 2024) is the authoritative mapping; encode it as a lookup table with tests.
2. **Route codes to reactions.** Insufficient-funds (MS02) routes to dunning retry; no-mandate (MD01/MD06-family issues) routes to mandate re-confirmation and suspension; account-closed codes route to terminal instrument removal. Codes you cannot classify should land in a manual queue with the raw payload attached, never a default guess.
3. **Watch MD06 specifically.** Refund request by debtor means the customer exercised the no-questions-asked right; this is a churn/involuntary-cancel signal more than a payment-failure signal, and should suppress further debits immediately rather than entering the retry cadence.

## Payer rights windows

1. **Encode the 8-week rule into revenue logic.** Every SEPA collection carries an unfinalized window of eight weeks from debit date during which an unconditional refund can arrive. Revenue recognition, available-balance computation, and payout projections for SEPA-heavy books must either hold a return provision or accept restatement when late returns land.
2. **Track the 13-month unauthorized window separately.** Collections without a valid mandate (never registered, revoked before debit, amount outside mandate terms) can be returned for thirteen months. The differentiator is mandate validity, so store mandate lifecycle evidence (registration timestamp, amendment history, revocation timestamp) queryable per collection.
3. **Preserve mandate evidence for disputes.** When a 13-month claim arrives, the creditor bank will investigate mandate validity. Retrieve the original mandate reference, signed registration, and the collection history within the bank's response deadline; keeping signed mandate artifacts addressable by mandate id is the difference between winning and auto-losing these claims.

## Ledger and subscription reactions

1. **Reverse with symmetric double entries.** A return must produce the exact mirror of the original collection posting (debit revenue/bank, credit the customer balance), plus a separate posting for any return fees charged by your bank. Never net fees against the reversal amount.
2. **Pause debits before investigating.** On any mandate-family return code, suspend the mandate immediately so scheduled debits stop while the customer is contacted; debiting a customer who just refunded a charge is the fastest route to a bulk revocation complaint.
3. **Handle re-presentation policy deliberately.** Some banks and schemes allow re-presentment of returned collections (within limited attempts and timelines), but every re-presentation against an active refund dispute is a customer-service hazard. Default to contacting the customer and re-collecting with consent rather than automatic re-presentation.

## Scheme change management

1. **Version your rulebook handling.** The EPC updates SEPA rulebooks on a defined schedule; the 2025 rulebook updates took effect 5 October 2025, with technical and scheme-alignment changes that can shift message formats and code usage. Subscribe to EPC change notifications and regression-test reason-code parsing against each new rulebook version's sample files.
2. **Test with real R-transaction files.** PSP sandboxes rarely reproduce the messiness of production returns (unknown codes, missing proprietary fields, batch files mixing types). Maintain a fixture corpus of anonymized production R-transactions and run every parser change against it.
3. **Reconcile return fees monthly.** Your acquirer bills return handling fees on a separate statement cadence from collections; match them into the ledger against return events so the true cost of SEPA as a rail (nearly free to collect, expensive when returned) stays visible.
