# Stripe Revenue Recognition input governance

**Issue:** Automated accounting output is only as reliable as its source transaction dates, currencies, invoice lines, refunds, disputes, and rule configuration. Treating a generated schedule as unquestionable can preserve upstream mistakes.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented — accounting policy requires qualified review

## Decision

Use Stripe Revenue Recognition as a controlled accounting subsystem. Define ownership of source data and custom rules, reconcile generated schedules to the ledger, and require qualified accounting approval for policy choices.

## Controls

- Document which Stripe objects and imported transactions feed each recognition process.
- Keep service periods, contract changes, credits, refunds, disputes, and write-offs explicit.
- Separate presentment, settlement, and functional-currency treatment.
- Apply least privilege to rule and settings changes.
- Record who changed a rule, the effective date, rationale, and affected reporting periods.
- Test custom rules against representative historical fixtures before activation.
- Reconcile recognized, deferred, and excluded amounts to the general ledger each close.
- Use a controlled close/reopen procedure; never silently rewrite a closed period.
- Preserve exports and audit evidence under the organization’s retention policy.

## Verification

For each close, tie beginning deferred balance plus additions minus recognized and adjustments to ending deferred balance. Sample invoice lines through source object, rule, schedule, journal entry, and ledger. Test refunds, disputes, multi-currency activity, mid-period changes, and imported data. Investigate every unexplained difference.

## Gotchas

The software does not decide the correct accounting standard or policy for the business. Product configuration, contract terms, and local requirements can change recognition. Dashboard totals are not a substitute for ledger reconciliation.

## Sources

- [Stripe Revenue Recognition documentation](https://docs.stripe.com/revenue-recognition)
- [Stripe: how Revenue Recognition works](https://docs.stripe.com/revenue-recognition/methodology)
- [Stripe Revenue Recognition reports](https://docs.stripe.com/revenue-recognition/reports)
