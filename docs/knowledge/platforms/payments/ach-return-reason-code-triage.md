# ACH Return Reason Code Triage

**Issue:** ACH entries that cannot be posted by the RDFI are returned to the ODFI with a Nacha-defined return reason code (R01-R85, plus administrative and dishonored returns). Each code identifies a specific failure condition and dictates the resubmission rules, the timing, and the customer communication requirements. Engineering the triage logic means mapping every inbound return code to an originating-system action: do-not-retry (account closed, unauthorized), retry with corrected data (routing number corrected), retry with different timing (insufficient funds — wait and try again later), or escalate to a manual workflow (administrative return). Treating returns as a single class ("it failed") loses information and forces the operations team to interpret each return individually.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Return categories

1. **Administrative returns (R02, R03, R04).** Account closed, no account / unable to locate, invalid account number. These are terminal for the specific account. The originating system must mark the stored payment method as invalid, surface a re-collection flow at next interaction, and not retry the entry against the same account.
2. **Authorization-related returns (R05, R06, R07, R08, R10, R11, R29).** Unauthorized debit, returned per ODFI's request, authorization revoked, payment stopped, customer advises unauthorized, customer advises entry not in accordance with authorization terms. These carry dispute implications and may require Reg E or NACHA Rule compliance steps. The originating system must flag the entry as disputed and route to the operations team.
3. **Account-status returns (R01, R09, R14, R15, R16, R17, R20, R23).** Insufficient funds, uncollected funds, representative payee deceased, beneficiary or account holder deceased, account frozen, account frozen due to OFAC, non-transaction account, credit entry refused. The originating system must distinguish between retry-eligible (R01, R09 — wait and retry with customer notification) and terminal (R14, R15 — close the payment method).

## Timing and resubmission rules

1. **Standard return window.** RDFIs must return most ACH entries within two banking days of settlement. Same-Day ACH returns can arrive faster. Administrative returns (R02, R03, R04) have a 24-hour return window — RDFIs that miss the window lose the right to return for those specific reasons.
2. **Resubmission limits.** The Nacha Operating Rules limit the number of times an entry can be resubmitted for insufficient funds. Two resubmissions is the typical operational cap; some ODFIs allow a third if the receiver has authorized it. Engineering must track the resubmission count per entry and not exceed the cap.
3. **Notification of change (NOC) versus return.** A returned entry that contains correctable information comes back as an NOC, not a return. Common NOC codes include C01 (incorrect bank account number), C02 (incorrect transit/routing number), C03 (incorrect transit/routing number and bank account number). Engineering must process NOCs by updating the stored payment method, not by treating them as failures.

## Dishonored returns

1. **What a dishonored return means.** The RDFI accepted the entry and posted it, then later returned it. Dishonored returns (the original return was honored, then the RDFI dishonored its own return) are rare but signal systemic issues — typically a customer dispute resolved in the customer's favor, or an RDFI-side processing error.
2. **Funds recovery from the receiver.** Once the RDFI has honored the return, the originating system must pull funds back from the receiver. The receiver has no obligation to make funds available a second time. A dishonored return on a credit entry (the customer received funds and spent them) creates a hard loss.
3. **Time limit on returns.** The dishonored return window closes for most entries after two banking days from the original return settlement. The originating system must monitor for late dishonored returns and reconcile them against the original entry, not against new billing.

## Engineering controls

1. **Return code lookup table.** Maintain a versioned return code table that maps each code to an action class: retry-with-corrected-data, retry-with-different-timing, terminal-mark-invalid, manual-review. The lookup table must align with the version of the Nacha Operating Rules the ODFI is operating under; older ODFIs may use slightly different code subsets.
2. **Customer notification templates.** Insufficient-funds returns, administrative returns, and authorization-related returns require different customer communication. Insufficient funds typically warrants a soft notification with a retry option; administrative returns require immediate payment-method update prompts; authorization-related returns require written notice and dispute process.
3. **Reconciliation tie-out.** Every returned entry must reconcile back to the original origination. The originating system tags each batch with an internal batch ID, the ODFI's trace number, and the SEC code; the return must match. A return that does not match signals a routing error and must be escalated before resubmission.

## Failure modes

1. **Treating all returns as failures.** A returned entry may carry information that the originating system needs to update (an NOC) or that signals a customer dispute (R10, R11). Treating the return as a generic failure loses the corrective signal and forces a manual review.
2. **Retrying past the resubmission cap.** Insufficient-funds retries past the Nacha cap can trigger ODFI fines and receiver complaints. Engineering must hard-stop retry attempts at the cap and route to manual intervention.
3. **Missing the dishonored return window.** A dishonored return that arrives after the operating-system's reconciliation has closed the original entry creates an unreconciled item. Engineering must monitor dishonored returns as a distinct stream and re-open the original entry on receipt.

## Canonical sources

1. Nacha (National Automated Clearing House Association), Nacha Operating Rules & Guidelines, including the return reason code appendix and the dishonored return provisions, current edition. https://www.nacha.org/rules
2. Consumer Financial Protection Bureau, Regulation E (12 CFR Part 1005), including the error resolution procedures and timing for unauthorized electronic fund transfers. https://www.consumerfinance.gov/rules-policy/final-rules/electronic-fund-transfers-regulation-e/
