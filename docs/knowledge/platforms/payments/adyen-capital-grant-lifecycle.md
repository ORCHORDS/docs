# Adyen Capital grant lifecycle

**Issue:** Capital offers and grants have eligibility, terms, disbursement, repayment, and state transitions. Showing stale offers or treating a grant as ordinary balance funds can create misleading financial commitments.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** restricted financial product

## Controls and implementation

Fetch offers server-side, bind them to the correct legal entity/account and currency, persist terms/version/expiry, and require explicit borrower acceptance. Keep grants and repayments in a dedicated audited ledger and reconcile provider events idempotently. Restrict access and retain required disclosures.

## Verification

Test expired/withdrawn offers, duplicate acceptance, timeout-after-accept, partial/failed disbursement, repayment events, account closure, currency mismatch, sandbox isolation, and webhook disorder.

## Gotchas

Availability is jurisdiction/account dependent and requires legal/compliance review; an API response is not advice.

## Sources

- Adyen Docs, [Capital](https://docs.adyen.com/platforms/capital/)
