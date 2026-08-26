# payment-surcharges-convenience-fees

**Issue:** Passing card processing costs to customers via a surcharge or convenience fee is legally fragile: rules differ by country, US state, card network, and payment type, and they keep changing. As of 2026 surcharging credit is legal in most US states but prohibited in Connecticut and Massachusetts, debit surcharging is banned nationwide under Durbin (with Louisiana adding an explicit statutory ban effective August 1, 2026), Visa caps credit surcharges around 3% and Mastercard at 4%, and acquirers can be fined (typically passed to the merchant) for improper programs. Engineering a surcharge feature means encoding a regulatory rule engine, not adding 3% to a total. This article covers the rules that matter and the systems needed to stay compliant.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Rule landscape

1. **Card network caps.** Visa and Mastercard limit credit surcharges to the lesser of your actual processing cost or a cap (commonly cited as 3% Visa / 4% Mastercard in the US). The surcharge must never exceed what you actually pay to accept that card — so the compliant maximum is per-merchant, not a universal constant.

2. **State prohibitions and conditions.** Connecticut and Massachusetts prohibit credit surcharges outright. New York requires posting the highest price a consumer might pay (including surcharge) — not just "3% fee applies." New Jersey requires surcharges to be cost-based. California's Civil Code 1748.1 has been largely unenforceable after litigation but still nominally prohibits. This set changes year to year; treat it as data, not code.

3. **Debit is never surchargeable in the US.** The Durbin Amendment's interchange regulation prohibits surcharging debit cards, including credit-card-branded debit run as credit. This forces BIN-level detection: you must know the funding type before applying a surcharge, which arrives only after payment details are entered or a wallet is decrypted.

4. **Registration and notice.** Merchants must notify their acquirer and the card networks (typically 30 days in advance) before surcharging, post disclosure at store entry and point of sale, and show the surcharge as a distinct line item on receipts. Digital checkouts need equivalent pre-selection disclosure.

5. **Outside the US.** The EU/UK prohibit consumer surcharging on card payments entirely; Australia caps surcharges at the merchant's cost of acceptance enforced by the RBA and ACCC. A global checkout cannot ship one surcharge rule — it needs per-jurisdiction policy.

## Rule engine design

1. **Encode rules as versioned data, evaluated at checkout.** A surcharge policy table keyed by (jurisdiction, funding type, card brand, channel) with effective dates — never hardcode percentages. When Louisiana's debit ban activated August 1, 2026, or when a state drops its prohibition, a data update should roll out without a code deploy.

2. **Resolve the rule after the funding type is known.** The surcharge cannot be computed until BIN data or a wallet response reveals credit vs debit vs prepaid. Design the checkout to show base prices everywhere, then present the itemized surcharge at review time once the instrument is known — with the option to switch to a non-surcharged method (this switching option is itself a compliance requirement in several regimes).

3. **Cap at effective processing cost.** Compute the surcharge as min(network cap, your effective rate for that transaction tier). For most merchants this means a fixed configured percent validated monthly against actual blended cost statements; store the evidence (statement, rate calculation) for dispute defense.

4. **Distinguish surcharge from convenience fee.** A convenience fee is charged for the channel of payment (e.g., paying by phone) rather than the card itself, follows different network rules, and is often flat. Mixing the two mechanisms in one checkout invites both being ruled non-compliant; pick one model per jurisdiction.

## Ledger, receipts, and refunds

1. **Store surcharge as a separate line item.** The order total should decompose into base amount, surcharge amount, tax treatment of each, and total — in the payment record, receipt, and your ledger. Some jurisdictions tax the surcharge; your tax engine needs the split.

2. **Refunds must return the surcharge.** A full refund refunds base plus surcharge; a partial refund refunds proportionally (or per policy — define it explicitly). Failing to return surcharges on refunded orders is both a chargeback trigger and a consumer-protection violation.

3. **Surcharge revenue is not revenue.** Account for surcharges as an offset to processing expense, not as sales revenue, and keep the payout/settlement reconciliation mapping surcharge amounts to the fee lines they offset. This matters at audit time and for accurate unit economics.

4. **Reconciliation with processor fees.** Because the surcharge is justified by cost, reconcile monthly: sum of surcharges collected vs processing fees paid per card type. Persistent gaps in either direction mean misconfiguration — either overcharging (compliance risk) or under-recovering (margin leak).

## Operational safeguards

1. **Automate the disclosure surface.** Generate the checkout disclosure text, receipt line, and (for retail) signage from the same rule data so they cannot drift apart. New York-style "highest price" requirements make inconsistent display itself a violation.

2. **Monitor rule changes on a schedule.** Assign a quarterly review of NCSL/state statute trackers and network bulletins, with changes flowing into the versioned policy table. The 2026 Louisiana change shows states actively legislating here; last year's table is already stale.

3. **Alert on surcharge disputes and chargebacks.** A rise in surcharge-related complaints or chargebacks with "incorrect surcharge" reason codes is the earliest signal your rule engine diverged from current law — treat it as a page-worthy incident, not support noise.

4. **Offer a free payment alternative.** Regulators (and card networks) expect at least one non-surcharged payment path (cash, ACH, debit in the US). If every method carries the fee, the program risks being reclassified as deceptive pricing rather than cost pass-through.
