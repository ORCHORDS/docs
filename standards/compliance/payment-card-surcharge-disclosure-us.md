# payment-card-surcharge-disclosure-us

**Issue:** Passing card-acceptance costs to customers as a surcharge is legal in most US states but only inside a tightly constrained box built from three overlapping rule systems: state statutes (a handful still prohibit or cap surcharges), card-network rules (Visa caps surcharges at 3 percent or actual cost of acceptance, whichever is lower; Mastercard at 4 percent or cost), and federal statute (the Durbin Amendment prohibits surcharging debit or prepaid cards outright). Checkout engineering that gets one input wrong — surcharging a debit run as credit, omitting the required posted disclosure at the door and receipt line, exceeding the cap in a state that sets a lower one — produces per-transaction consumer-protection violations and network fines. Surcharges are also legally distinct from cash discounts and convenience fees, which follow entirely different rules; conflating the three in one payment config is the classic bug.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The three legal layers

1. **State law layer.** No federal statute bans credit surcharging, but several states regulate it: prohibitions in a shrinking set (long-standing bans in states like Connecticut and Massachusetts remain on the books; California's Civil Code 1748.1 ban survived years of First Amendment challenges), and caps below the network maximums elsewhere (e.g., a 4 percent statutory cap in Colorado, Maine, and Massachusetts contexts; New York forbids surcharging above the merchant's cost of acceptance). The payment config needs a per-state rule table keyed to the merchant's location, since the law that applies is generally where the seller is, not the buyer.
2. **Network rule layer.** Visa requires merchants to notify acquirers 30 days before surcharging begins, caps credit surcharges at 3 percent or actual acceptance cost (whichever is lower), and mandates disclosure at the point of entry and on the receipt; Mastercard allows up to 4 percent or cost, with product-level rules for different card programs. Amex operates under a surcharge-equality rule — you may not surcharge Amex more than other networks.
3. **Federal debit layer.** Under Dodd-Frank/Durbin as implemented by Regulation II, merchants may not impose a surcharge on debit or prepaid transactions even when the debit card is routed through a credit network and presents as "credit." The BIN must be evaluated by card type, not by how the customer authenticates.

## Checkout engineering rules

1. **Classify by BIN, not by behavior.** The surcharge engine needs BIN-range intelligence: credit cards from issuers get surcharged; debit and prepaid never do, regardless of signature/PIN routing; prepaid cards follow debit rules. Misclassifying a debit run as credit is a Reg II violation per transaction, with no materiality floor.
2. **Cap selection must take the minimum of everything.** Compute effective cap as min(network cap, state cap, actual average acceptance cost for that card product); the "actual cost" defense requires the merchant to have data on their own effective rate, so store the cost input alongside the rule table and let the payment config reference it with an audit trail.
3. **Percent math on the pre-surcharge subtotal.** The surcharge applies to the goods subtotal before tax and may not itself be taxed in most states; round per the state's convention and validate that the surcharge line cannot compound on itself in a retry or partial-capture flow.
4. **Refund flows must return the surcharge.** When an order is refunded, the surcharge is part of the transaction and must be returned with it; partial refunds need proration logic that includes the surcharge proportion.

## Disclosure requirements

1. **Point-of-entry signage for card-present.** Network rules require notice at the store entrance and at the register — the dollar or percentage amount must be posted; digital signage versions should be versioned like other compliance copy.
2. **First disclosure on the e-commerce checkout page.** For online sales, the surcharge must be disclosed no later than the first page/screen where card options are presented, with the amount stated before the customer enters card details — meaning the surcharge estimate must render before the BIN is known, then true-up post-BIN.
3. **Receipt line item.** The surcharge must appear as a distinct line ("Credit Card Surcharge 3%: $2.70") on the receipt or confirmation, not folded into tax or shipping; confirmation emails inherit the same requirement.
4. **No surcharge plus convenience fee stacking.** Networks prohibit applying both a surcharge and a convenience fee to the same transaction; convenience fees are the alternative-payment-channel mechanism (phone/mail/online for a normally in-person merchant) and are flat-fee friendly, but the two regimes are mutually exclusive per transaction.

## Safer alternatives and their traps

1. **Cash discounting is lawful in all states.** Posting a higher price and discounting for cash/check/debit avoids the surcharge rulebook entirely, but the advertised price is then the card price and the discount must be clearly disclosed; several states regulate how the signage reads.
2. **True dual pricing** (separate card and cash prices on the shelf) is permitted in more states than surcharging but has its own signage rules and is restricted in a few jurisdictions.
3. **Reconcile monthly against network chargebacks.** Network assessments for surcharge violations arrive via the acquirer as fines and compliance items; route them to the same queue as rule-table updates so a penalty always triggers a config review, and keep the per-state table on a quarterly verification cycle because state caps move.
