# Payout Orphan Funds Recovery Procedure

**Issue:** "Orphan funds" are balances on a payments platform that cannot be paid out to a known payee: the original merchant bank account was closed, the payee's payment instructions are missing or invalid, the payee entity has been dissolved, or regulatory action (sanctions, account freeze) blocks the payout. Orphan funds accumulate over time — particularly in marketplaces, gig platforms, multi-party commerce, and cross-border payouts — and represent a real financial and reputational risk if not actively managed. Engineering the orphan-funds recovery procedure means identifying orphan balances quickly, holding them in a segregated account with interest tracking, applying the escheatment or unclaimed-property process according to the applicable jurisdiction, and returning the funds to the payee when they become reachable.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Identifying orphan balances

1. **Closed bank account indicators.** A payout that returns with a return code indicating closed account (ACH R02, SEPA invalid account, wire account-closed message) is an orphan candidate. The platform must stop attempting payouts to that account and surface the balance to the operations queue.
2. **Invalid payment instruction.** A payout that fails because the payment instructions are missing (no routing number, no IBAN, no SWIFT code) or malformed is an orphan. The platform must flag the balance and stop attempting until the payee provides valid instructions.
3. **Sanctions and regulatory blocks.** A payout that fails a sanctions screening (OFAC SDN list, EU sanctions, UK OFSI list) is an orphan of a different kind: the funds are blocked, not abandoned. The platform must hold the funds in compliance with the sanctions regime and not disburse until the block is lifted.

## Segregation and accounting

1. **Segregated account.** Orphan funds must be held in a segregated account, not in the platform's operating account. Segregation is a regulatory requirement in many jurisdictions (US state money transmitter laws, UK FCA safeguarding rules, EU PSD2 safeguarding requirements) and a best practice everywhere.
2. **Interest tracking.** Orphan funds may earn interest in the segregated account; the interest must be tracked and either paid to the original payee when they claim the funds or, where applicable, transferred to the state's unclaimed-property program as additional unclaimed property.
3. **Accounting entries.** Each orphan balance must be tracked in the platform's ledger with: the original payee ID, the original transaction reference, the date the balance became orphan, the amount, the currency, and the segregation status. The ledger entries must be auditable for the retention period.

## Escheatment and unclaimed property

1. **State-by-state rules in the US.** Unclaimed property laws in the US are state-administered. Each state has a dormancy period (typically 3-5 years), an escheatment process, and a holder reporting requirement. A platform with US-based orphan funds must track per-state rules and report to the relevant state when the dormancy period elapses.
2. **International equivalents.** Many jurisdictions have unclaimed-property regimes with their own dormancy periods, holder obligations, and reporting cycles. The platform must maintain a jurisdiction matrix and apply the local rules to orphan balances held for payees in each jurisdiction.
3. **Annual reporting.** The annual holder reporting to state unclaimed-property programs (and equivalent international programs) is a regulated deadline with significant penalties for late or missed filings. The platform's compliance team must own the reporting process, with engineering providing the data extract.

## Recovery workflows

1. **Payee reaches out.** The original payee may reach out to claim the orphan funds years after the orphan event. The platform must have a recovery workflow that: verifies the payee's identity, verifies the original transaction reference, releases the funds to a verified bank account, and reconciles the ledger.
2. **Third-party claim.** A payee may authorize a third party (a collection agency, a court-appointed receiver, a bankruptcy trustee) to claim the orphan funds. The platform must have a documented third-party claim process with identity verification, authorization evidence, and disbursement controls.
3. **Government claim.** A government entity (tax authority, court, regulator) may make a claim against orphan funds as part of a tax debt or a regulatory action. The platform must have a documented process for handling government claims with the appropriate legal review.

## Engineering controls

1. **Orphan detection job.** Engineering must build a job that detects orphan balances across all payment products (ACH, wire, card, wallet, crypto). The job must produce a report with the orphan balance, the reason, the dormancy status, and the segregation status.
2. **Segregation ledger.** The segregation ledger tracks orphan balances in a dedicated account or sub-account. The ledger must reconcile against the bank statement daily, with discrepancies flagged for investigation.
3. **Reconciliation with the unclaimed-property program.** Engineering must produce the annual reporting extract for each state and each international jurisdiction. The extract format varies by jurisdiction; the engineering team must maintain the export templates and run the extracts on schedule.
4. **Recovery API.** The operations team must be able to recover orphan funds to a verified payee account with a documented audit trail. Engineering should expose a recovery API with multi-party approval for high-value orphan balances.

## Failure modes

1. **Operating funds used to cover orphan balances.** Using the platform's operating account to absorb orphan balances (rather than holding them in segregation) is a regulatory breach and a customer-trust failure. The segregation must be enforced in the ledger, not as a policy that can be overridden.
2. **Missing escheatment deadlines.** A platform that misses an escheatment filing deadline faces penalties and potential class-action exposure. Engineering must surface the deadline calendar to the compliance team with adequate lead time.
3. **Recovery without identity verification.** Releasing orphan funds to a payee without verifying identity creates a fraud vector. Engineering must enforce identity verification as a hard gate on the recovery workflow, with no exception path.

## Canonical sources

1. US state unclaimed property laws administered by the National Association of Unclaimed Property Administrators (NAUPA) and state-specific holder reporting requirements. https://unclaimedproperty.nasra.org/
2. UK Financial Conduct Authority, FCA Handbook CASS (Client Assets Sourcebook) on safeguarding client money, including the orphan money handling requirements for payments firms. https://www.handbook.fca.org.uk/handbook/CASS/
