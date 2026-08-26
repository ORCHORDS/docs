# open-banking-pay-by-bank-integration

**Issue:** Account-to-account payments — "pay by bank" — let customers authorize a transfer directly from their bank account via open banking APIs instead of pulling out a card. Adoption is compounding: the UK set records with roughly 30 million open banking payment initiations in a single month in 2025, and Mastercard projects European open banking use to double by 2027. For merchants the economics look attractive (near-card UX at well-below-card cost, no chargeback mechanism), but the integration differs fundamentally from cards: confirmation can be delayed, refunds must be engineered as separate transfers, recurring billing needs a different mandate construct (VRP), and buyer-protection expectations differ. Teams that treat pay-by-bank as "just another payment method in the drop-down" hit each of these in production.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How the flow actually works

1. **Bank selection and consent.** The customer picks pay-by-bank at checkout and selects their bank (from a provider's bank directory — coverage varies by country and aggregator), or the flow is embedded in a modal via an aggregator (Tink, Plaid, TrueLayer, GoCardless, Trustly).
2. **Redirect or embedded authentication.** The customer authenticates with the bank directly (redirect to bank web/app, or an embedded UI). Strong customer authentication happens at the bank — usually biometric/approval in the banking app — so no 3DS layer is involved.
3. **Payment initiation and confirmation.** A payment-initiation service provider (PISP) submits the transfer; the API returns success synchronously in most UK/EU open banking implementations, but actual funds settlement rides the underlying rails (Faster Payments in the UK, SEPA Instant or SEPA Credit Transfer in the EU), so reconciliation should key on the PSP's confirmation event plus settlement where exposed.
4. **State handling.** Treat it like a redirect flow: persistent PaymentIntent-equivalent state, idempotent webhook processing, and a timeout path for abandoned bank sessions. Bank-app deep links on mobile are a major completion-rate lever — never force desktop-style login on a mobile user.

## Where pay-by-bank wins, and where it does not

1. **Cost.** Pricing is typically a low fixed fee per transaction rather than a card-style percentage interchange plus scheme fees — decisive on high-ticket items (a 2.9% card fee on a EUR 900 invoice is real money; pay-by-bank is usually a fraction of it).
2. **No chargebacks.** Account-to-account push payments have no card-network dispute mechanism; "I didn't like it" cannot become a forced reversal. Fraudulent-transfers disputes run through bank complaint/ombudsman channels, not merchant representment (which cuts both ways — see refund model below).
3. **Failed-payment exposure differs.** There is no issuer soft-decline/insufficient-funds-try-again dance in the same shape: the bank authorization is decisive at initiation. But funds-availability checks are weaker on some rails, and returns (e.g., account closed) can arrive post-confirmation on non-instant rails.
4. **Checkout completion risk.** Bank-flows still shed more users than one-click wallets for small purchases; the strongest placements are bill pay, invoices, high-ticket retail, gambling/payouts-adjacent flows, and markets (Netherlands with iDEAL-heritage, Nordics with bank-ID culture) where bank payment is the default habit.

## Refunds and disputes: engineer them deliberately

1. **Refunds are outbound transfers, not reversals.** You must retain a mandate/reference to pay the customer back via an original-credit return (UK open banking refunds) or a separate transfer initiated by you; capture the customer's bank details reference at payment time — after they close the bank session it is much harder to collect.
2. **No representment, but also no chargeback shield.** Merchants gain protection from friendly-fraud chargebacks but inherit full responsibility for authorized-push-payment (APP) fraud complaints; expect scrutiny under PSD3's expanded fraud-data-sharing and verification-of-payee obligations (see psd3-psr-2026-legislative-state).
3. **Double-refund hazard.** Because refunds are asynchronous outbound transfers, a refund that fails after several days plus a customer-service goodwill credit can double-pay; track refund transfer status as a first-class state machine.
4. **Reconciliation keys.** Store the provider's payment ID and the end-to-end ID/remittance data; bank statements show transfer references your finance team must be able to match (see bank-statement-matching in this knowledge base).

## Recurring and variable payments: VRP, not card-style billing

1. **Variable Recurring Payments (VRP).** UK open banking supports VRP mandates — a consent with a payment limit and periodicity that lets the merchant initiate successive variable-amount payments without re-authenticating each time. Initially bank-mandated for sweeping (moving your own money), commercial VRP for third-party merchants rolled out from 2023-2025 with growing bank coverage.
2. **VRP is not a card-on-file.** Coverage is bank-by-bank, consent caps are real (per-payment and rolling limits), and customers can revoke consent at their bank — your billing engine must treat mandate revocation webhooks as immediately binding, unlike cards where revocation is soft.
3. **Non-VRP fallback.** Without VRP, recurring billing via open banking degenerates into collecting a Direct Debit mandate or per-cycle re-authorization; for pure subscription businesses SEPA Direct Debit or cards often remain the primary rail with pay-by-bank for top-ups and invoices.
4. **SEPA Request-to-Pay.** In the EU, SRTP is a request/confirmation layer (an electronic invoice the customer approves) rather than a pull-mandate; useful for bill-presentment flows, not invisible auto-charge flows.

## Integration pitfalls observed

1. **Bank coverage gaps.** No aggregator covers 100% of banks in any market; always render "your bank not listed" gracefully and consider an aggregator cascade or fallback method.
2. **Sandbox vs production bank behavior.** Bank APIs fail in ways PSPs do not (maintenance windows, consent timeouts, SCA-method not enrolled); test abandoned-consent, expired-consent, and timeout paths explicitly.
3. **Do not promise instant settlement you have not verified.** Instant-confirmation is common, but on SEPA Credit Transfer-backed implementations funds arrive later; decouple "order accepted" messaging from "funds settled" accounting.
4. **Contextual offering beats default listing.** Conversion is best when pay-by-bank is positioned where its strengths matter (invoice/bill/high-ticket contexts, or card-averse markets) rather than competing head-on with Apple Pay at the top of the wallet sheet.
