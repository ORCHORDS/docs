# NOWPayments Payout Allowlist and Two-Step Authorization

**Issue:** A compromised payout credential or automation host can turn a payment integration into an irreversible withdrawal path unless destination, source-network, approval, and ledger controls are independent.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Separate collection credentials from payout authority. Enable the provider's source-IP and wallet-address allowlists for payout operations and treat any allowlist change as a privileged, delayed administrative event. Validate the destination address and any required memo/tag through the provider's validation endpoint before creating a payout.

Keep two-step verification enabled. If payout verification is automated with a time-based one-time-password seed, store that seed independently from the API key and never expose either in repository files, workflow output, process arguments, or logs. Prefer a human or policy approval for new destinations and high-value withdrawals; automation should operate only inside pre-approved currency, amount, address, and velocity limits.

Generate an internal payout intent with an immutable idempotency key and expected currency, chain, address, memo/tag, gross amount, fee ceiling, and approval record. Re-read this intent immediately before provider submission. Record the provider payout identifier and reconcile terminal status against the internal ledger rather than treating API acceptance as settlement.

## Verification

In a provider sandbox or controlled low-value environment, test invalid addresses, missing/wrong memo, non-allowlisted source IP, non-allowlisted wallet, invalid/expired OTP, duplicate submission, timeout after create, delayed verification, fee/amount drift, and provider rejection. Prove a retry queries existing state before creating another withdrawal. Exercise credential rotation and emergency payout disablement.

Alert on allowlist changes, failed validations, repeated OTP failures, payout velocity anomalies, ledger mismatches, and long-pending transfers. Logs must contain references and status, never private keys, OTP seeds, API keys, or full sensitive headers.

## Gotchas

Address validation does not prove ownership or intended beneficiary. Network allowlisting is defense in depth, not identity. Blockchain finality and provider status transitions vary; define per-currency confirmation policy. Never reuse customer-supplied callback data as an approved payout destination.

## Sources

- [NOWPayments API documentation: payout flow, validation, allowlists, and verification](https://documenter.getpostman.com/view/7907941/2s93JusNJt)
- [NOWPayments payouts product documentation](https://nowpayments.io/payout)
