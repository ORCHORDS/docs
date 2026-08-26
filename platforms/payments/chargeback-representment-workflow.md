# chargeback-representment-workflow

**Issue:** A customer disputes a charge and you decide to fight it. Representment (Visa calls the merchant's response "second presentment" in Mastercard's lifecycle) is a multi-stage workflow with hard network deadlines, reason-code-specific evidence requirements, and escalation tiers where losing costs more than the original dispute. Teams that treat it as "reply to the Stripe email" auto-lose on deadlines, submit unusable evidence, and escalate marginal cases into arbitration fees. This article covers the full workflow beyond the basics already in chargeback-response-process.md: Visa Compelling Evidence 3.0, pre-arbitration, arbitration economics, and repeat-offender prevention.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Escalation tiers and where you stand in them

1. **Stage 1: first chargeback.** Issuer debits you (plus PSP fee) and you get a respond-by date — typically 7-21 days depending on network and reason code; in Stripe the exact deadline is on the dispute object. No response = automatic loss; calendar it the moment the webhook lands.
2. **Stage 2: representment.** You submit evidence; the issuer reviews and either reverses or upholds. Winning here means money returned minus processing fees — it is the only stage where fighting is cheap, so this is where evidence quality matters most.
3. **Stage 3: pre-arbitration (a.k.a. second chargeback).** The cardholder's issuer can re-dispute after your representment wins, claiming new evidence. On Visa, merchants pay roughly $15 per pre-arb filing whether they win or lose; network filing windows are on the order of 120 days from the transaction. At this stage, honestly re-evaluate: most PSPs advise accepting liability unless evidence is overwhelming.
4. **Stage 4: network arbitration.** If you refuse pre-arb liability, the card network rules bindingly. Visa's arbitration filing fee rose from $500 to $600 effective April 1, 2025, charged to the loser; Mastercard's combined fees run around $400 with ~$500 to appeal. Only go to arbitration when the amount dwarfs the fee and your evidence is airtight — a loss costs dispute + fees + your dispute-rate ratio damage.

## Evidence packaging that actually wins

1. **Match evidence to the reason code, not a generic template.** "Fraud, card-absent" (Visa 10.4) wants device/IP history and prior undisputed transactions; "product not received" wants delivery proof with timestamps and address match; "not as described" wants your product page as it existed at purchase time plus terms accepted.
2. **Assemble the SaaS core pack.** For subscription disputes: signup IP and timestamp, email verification and receipt delivery logs, ToS/checkout consent capture with timestamp, login/usage logs proving consumption, prior undisputed charges on the same card, and cancellation-policy acknowledgment. A chargeback is decided by an issuer employee in minutes — a single organized PDF in chronological order beats a folder of raw exports.
3. **Exploit Visa Compelling Evidence 3.0 (10.4 fraud).** CE 3.0 lets you kill friendly-fraud disputes by proving prior undisputed usage: two prior undisputed transactions on the same card, 120-365 days older than the disputed transaction, each sharing at least two matching data elements with it (IP address, device ID/fingerprint, shipping address, billing address, email, phone). If you qualify, disputes can be blocked pre-dispute via Verifi Order Insight instead of fought. Note Visa's October 2025 CEDP data-rule updates tightened what qualifies — validate element capture in your checkout now.
4. **Digital goods are harder, not hopeless.** There is no signed delivery receipt, so substitute authenticated usage: login events, feature usage, API call logs, and content downloads tied to the account, plus the device fingerprint chain from signup to usage. Courts of network rules accept server-side logs; they do not accept "our dashboard shows they were active" screenshots.
5. **Never submit contradictory evidence.** If any artifact (a partial refund, a support ticket admitting fault, a shipping delay) undermines your claim, the issuer will find it. Self-audit the customer's full history before submitting — conceding a losing dispute early costs less than fighting and pre-arbing it.

## Deadline discipline

1. **Track the respond-by date in your own system, not the PSP inbox.** Mirror dispute webhooks (charge.dispute.created) into a queue with SLA alerts at T-7, T-3, and T-1 days. Stripe dispute objects carry `evidence_details.due_by` — persist it, do not recompute it.
2. **Budget for evidence gathering time.** Logs live in multiple systems (auth provider, app DB, email provider, PSP). A runbook that pre-maps reason code -> evidence sources -> owner turns a 3-day scramble into a 3-hour assembly.
3. **Submit before the last day.** Networks reject late or partial evidence; some PSPs mark evidence "submitted" before validation. Target internal completion 48h before due-by.

## Economics: when not to fight

1. **Know your true cost per dispute.** A 2025 Mastercard/Javelin report put internal handling cost around $82 per chargeback before the disputed amount and PSP fees — a $9.99 dispute is a guaranteed loss no matter the outcome.
2. **Small amounts: refund-and-block.** For sub-$25 disputes where fraud signals are ambiguous, accept liability, block the payment method/customer, and move on. Your dispute-rate ratio (disputes per 100 transactions, thresholds around 0.9% Visa / 1.5% Mastercard for monitoring programs) is worth more than one representment win.
3. **Win-rate realities.** Merchants win a substantial share of well-evidenced representments, but "win" at pre-arb/arbitration is much rarer and fee-laden. Track win rate per reason code per network and let the data decide which codes you fight — not outrage at the customer.

## Preventing repeat disputes

1. **Blocklist the instruments, not just the user.** Block the card fingerprint, email, and device ID (PSPs expose these) of customers who file fraud claims you believe are abusive; a repeat offender with a new account reuses the card or device more often than you would think.
2. **Subscribe to network alerts.** Ethoca (Visa) and Verifi (Mastercard) alerts tell you a dispute is coming before it files, letting you refund proactively — the refund avoids the dispute counting against your ratio. Order Insight/CE 3.0 data sharing does this automatically for qualifying fraud claims.
3. **Feed representment outcomes into risk rules.** Every lost dispute with "unrecognized descriptor" as the root cause is a statement-descriptor fix; every friendly-fraud win is a signal to tighten Radar-style rules for that segment. Close the loop monthly between disputes and fraud-rule tuning.
