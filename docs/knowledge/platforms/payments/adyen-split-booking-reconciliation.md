# Adyen split booking reconciliation

**Issue:** A platform calculates commission, seller proceeds, fees, tips, and refunds locally but omits or changes Adyen split instructions across authorization, capture, and refund. Funds can fall back to the liable balance account while the order ledger still claims the intended allocation.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation

Create an immutable split plan per payment operation with currency, minor-unit total, split type, destination balance account, and a unique reconciliation reference for every item. Validate that required amounts and accounts are present and the split sum follows the provider contract before sending.

Persist the exact instructions and provider references used at authorization. If capture overrides them, record a new version linked to the authorization; do not mutate history. Require explicit split instructions when capture amount changes and model payment-method limitations that do not support delayed capture. Generate refund/chargeback allocation from booked evidence and review every residual amount assigned to the liable account.

## Verification

Test immediate and delayed capture, partial/multiple capture, overcapture where supported, payment methods without delayed capture, currency conversion remainder, missing account/reference, duplicate request, partial and multiple refund, chargeback, webhook delay, and report reconciliation. Assert each booked minor unit has one ledger owner.

## Gotchas

Authorization splits are not guaranteed final booking instructions: capture can override them. Omitting a reference can aggregate report entries, and omitting an account may book funds to the platform's liable balance account.

## Sources

- Adyen Docs, [Split transactions between balance accounts](https://docs.adyen.com/platforms/online-payments/split-transactions)
- Adyen Docs, [Split payments at capture](https://docs.adyen.com/platforms/in-person-payments/split-transactions/split-payments-at-capture)
