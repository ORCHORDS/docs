# NOWPayments Recurring Subscription State and Balance Controls

**Issue:** Crypto subscription charging can use different assets from the plan currency and can produce partial, waiting, paid, or expired periods, so a simple monthly boolean creates incorrect access and accounting.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Create plans and subscriptions through authenticated server-side calls, binding the provider customer/sub-partner identity to one internal tenant. Persist provider plan, subscription, and period-payment identifiers separately. Model documented payment states—waiting, paid, partially paid, expired—as explicit transitions rather than truthy strings.

The provider documents that available sub-user balance in another currency may fund the plan through conversion. Record the charged asset, amount, quoted plan value, conversion outcome, fees, and provider timestamps so accounting and customer support can explain differences. Grant access only under a documented policy for paid or tolerated partial states.

Verify callbacks using the existing webhook-security control, then fetch current subscription/payment state before irreversible changes. Run scheduled reconciliation because expired or delayed flows may not align with callback expectations. Cancellation must prevent future periods without erasing historical ledger rows.

## Verification

Test exact funding, different-currency funding, insufficient and partial balance, expiration, duplicate callbacks, delayed deposit, plan change, cancel near renewal, API timeout, and reconciliation after missed notification. Prove each period produces at most one access/ledger transition and preserve decimal precision by currency.

## Gotchas

Recurring crypto payment behavior is not card autopay. Exchange movement and conversion affect amounts. Email addresses are identifiers/contact data, not authorization. Never place bearer tokens, API keys, or callback secrets in client code or logs.

## Sources

- [NOWPayments API recurring payments documentation](https://documenter.getpostman.com/view/7907941/2s93JusNJt)
- [NOWPayments subscriptions](https://nowpayments.io/subscription)
