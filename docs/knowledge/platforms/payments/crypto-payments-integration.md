# crypto-payments-integration

**Issue:** Accepting cryptocurrency payments for SaaS or e-commerce
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Crypto payments require waiting for on-chain confirmations, handling volatile exchange rates, and managing wallet addresses. Providers like Coinbase Commerce or NOWPayments abstract the complexity.

## Pattern / Solution
Use a hosted provider such as Coinbase Commerce. Create a charge via the API with a fixed fiat amount — the provider converts to crypto at time of payment. Poll the charge or listen to the charge:confirmed webhook. Set expiry windows of 15-30 minutes due to price volatility.

## Gotchas
Partial payments are possible with crypto — handle underpayment scenarios. Confirmations required vary by blockchain. Stablecoins like USDC simplify the volatility problem but require wallet infrastructure.

## Related
payment-provider-abstraction, multi-currency-handling, payment-testing-stripe-test-mode
