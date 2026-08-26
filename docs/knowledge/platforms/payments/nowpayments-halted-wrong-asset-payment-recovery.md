# NOWPayments halted and wrong-asset payment recovery

**Issue:** A customer can send the wrong asset or repeat a deposit, leaving processing halted. An uncontrolled manual “continue” operation can apply a stale rate, misbind an order, or create duplicate fulfillment.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented — dashboard recovery capability; verify current account behavior

## Decision

Treat provider-assisted continuation as a privileged recovery workflow, not a normal payment transition. Reconcile the payment first, capture the proposed recovery terms, require authorized review, and make fulfillment idempotent after the provider reaches an accepted state.

## Controls

- Bind the provider payment ID to the expected internal order before recovery.
- Record received asset, amount, transaction hash reference, original quote, current proposed rate, fees, and reason for halt.
- Require role-based access and, for material values, four-eyes approval.
- Show the rate and expected outcome before confirmation.
- Never paste API keys, wallet secrets, or callback secrets into tickets or logs.
- Fetch provider state immediately before and after using the dashboard continuation control.
- Process resulting IPNs idempotently and reconcile independently.
- Preserve the pre-recovery state and audit actor, time, decision, and outcome.
- Escalate unsupported assets or ambiguous ownership instead of guessing.

## Verification

In an approved test environment, exercise wrong asset, repeated deposit, partial amount, stale quote, already-completed payment, concurrent operator actions, provider timeout, duplicate callback, and post-recovery reconciliation. Prove fulfillment occurs at most once.

## Gotchas

The dashboard control’s presence depends on why processing halted. Continuing a payment can have economic consequences from conversion and rates. A transaction hash alone does not prove it belongs to the intended customer or order.

## Sources

- [NOWPayments Help Center: Push button and halted payments](https://nowpayments.zendesk.com/hc/en-us/articles/21548394706717-Push-button-and-how-does-it-work)
- [NOWPayments dashboard](https://nowpayments.zendesk.com/hc/en-us/articles/18399924720157-NOWPayments-dashboard)
