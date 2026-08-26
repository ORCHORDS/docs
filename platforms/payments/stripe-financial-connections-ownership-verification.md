# Stripe Financial Connections ownership verification

**Issue:** An application treats a linked bank account as proof that the signed-in user owns it, or retains ownership data beyond the decision that required it.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

Stripe Financial Connections can expose account ownership data when supported and permissioned. Model linkage, permission, refresh, ownership record, verification decision, and revocation as separate states.

**Source:** [Stripe Financial Connections ownership documentation](https://docs.stripe.com/financial-connections/ownership)

## Controls

- request ownership permission only for a documented use case;
- retrieve records server-side and bind them to the correct Stripe account/session/customer;
- define matching rules for names, business owners, joint accounts, and incomplete data;
- encrypt and strictly limit retained personal data;
- handle revocation, refresh failure, and unsupported institutions;
- require additional verification for high-risk actions.

## Verification

Test individual/business/joint accounts, partial names, stale records, no support, revoked consent, duplicate sessions, wrong customer binding, and webhook retry. Confirm absence or mismatch follows reviewed policy rather than an automatic accusation.

## Gotchas

Linked does not mean owned, and an ownership name match is not legal identity proof. Coverage varies by institution and account type. Minimize storage of names, addresses, email, and phone data.
