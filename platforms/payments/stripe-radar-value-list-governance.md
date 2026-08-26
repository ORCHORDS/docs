# Stripe Radar value-list governance

**Issue:** Fraud teams paste identifiers into Radar rules without lifecycle, provenance, or scope controls, causing stale blocks and accidental denial of legitimate payments.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

Stripe Radar value lists let rules reference managed sets of values. Treat each list as security configuration: define its value type, owner, evidence, expiry policy, and deployment environment.

**Source:** [Stripe Radar lists documentation](https://docs.stripe.com/radar/lists)

## Controls

- separate test/live lists and allow/block purposes;
- choose the correct Stripe value-list item type;
- add items through least-privilege server workflows with audit context;
- avoid raw sensitive data when a supported fingerprint/token type exists;
- expire and review entries; require approval for broad lists;
- version dependent Radar rules with list changes.

## Verification

Test add/delete, duplicate item, wrong type, rule ordering, test/live separation, rollback, API retry, propagation delay, and legitimate-user appeal. Monitor match volume and false positives by list revision.

## Gotchas

A value-list match is a signal, not identity proof. Allow rules can bypass later blocks depending on rule order. Never store full card numbers or secrets as arbitrary list strings.
