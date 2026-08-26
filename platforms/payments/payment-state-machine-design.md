# payment-state-machine-design

**Issue:** A payment is not a single action — it is a multi-step, asynchronous conversation between your system, the processor, the issuing bank, and sometimes the shopper (3DS). Teams that model payments as a boolean "paid" flag inevitably hit races: a webhook arrives while a user cancels, a capture succeeds after a refund was issued, or two workers process the same event and grant entitlement twice. Stripe's own PaymentIntent API is explicitly a state machine, and payment backends that mirror it with an explicit, validated state machine survive partial failures, concurrency, and unreliable providers. This article covers how to design one.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Core state model

1. **Enumerate states explicitly; never store implicit state.** At minimum: requires_payment_method, requires_confirmation, requires_action (3DS/redirect), processing, succeeded, canceled, and a terminal failed path. A single text/enum column with an application-level whitelist beats scattered booleans (paid, refunded, pending) that can contradict each other.

2. **Separate the PSP's state from your domain state.** Your order can be pending, paid, fulfilled, or refunded while the underlying PaymentIntent moves through its own lifecycle. Store both — the external PSP status and your derived domain status — plus the mapping between them. Never derive business entitlement by parsing raw PSP status strings at read time.

3. **Make terminal states terminal.** succeeded, failed, and canceled must have no outgoing transitions. The only post-success mutation is a separate refund object that references the payment; it never flips the payment back to processing. This one rule eliminates the worst class of double-fulfillment bugs.

4. **Track why, not just what.** Store the transition reason (webhook event id, user action, expiry timer, manual ops override) with each state change. When a payment is stuck in requires_action for six hours, the reason trail tells you whether to nudge the customer or fix your return URL.

## Transition enforcement

1. **Define a transition table and validate every write against it.** Encode legal edges (processing -> succeeded, processing -> failed, requires_action -> succeeded, requires_payment_method -> canceled) in one place — a matrix in code or a transitions table in the DB. Every state update goes through a helper that checks the edge and rejects illegal moves with a loud error, rather than a bare UPDATE that overwrites whatever was there.

2. **Use optimistic concurrency on state columns.** UPDATE payments SET status = 'succeeded' WHERE id = ? AND status IN ('processing','requires_action') — and check the affected row count. If zero rows changed, someone else transitioned first: re-read and reconcile instead of blindly writing. This guards against webhook-vs-API races without distributed locks.

3. **Persist transitions as an append-only event log.** Keep a payment_status_history table (payment_id, from_state, to_state, source, event_ref, created_at). The current state column is a cached projection of the last event. This gives you replayability for debugging, a free audit trail for compliance, and protection against lost updates.

4. **Idempotent transitions by source event.** Key each transition on the triggering event (webhook event id, API request idempotency key) so redelivered events are detected before they attempt a transition. A duplicate payment_intent.succeeded should be a no-op, not an error.

## Fulfillment idempotency is a separate boundary

A durable webhook-event state machine is necessary but **not sufficient**. The downstream fulfillment operation must also be safe to execute more than once.

A common partial-failure sequence is:

1. claim event `E` as `processing`;
2. grant the license / allocate inventory / increment a sold counter successfully;
3. fail while writing `E = completed`;
4. mark `E = failed`, or let its processing lease expire;
5. retry `E` and execute fulfillment again.

If the fulfillment function itself does not atomically recognize that the same Checkout Session/order was already fulfilled, the retry can grant entitlement twice, increment inventory/sold counters twice, send duplicate downstream commands, or otherwise repeat an irreversible side effect even though the webhook-event wrapper looked "idempotent".

Stripe's current Checkout fulfillment guidance explicitly requires fulfillment to handle being called multiple times, including concurrently, for the same Checkout Session, and to perform fulfillment only once per payment. Stripe's webhook guidance likewise warns that webhook endpoints can receive duplicate deliveries and retries after non-2xx responses.

**Sources:**
- https://docs.stripe.com/checkout/fulfillment
- https://docs.stripe.com/webhooks

### Correct pattern

Use a domain-level fulfillment key in addition to the webhook event id. Good keys are the immutable provider payment/Checkout Session id or a server-created order id that is uniquely bound to that provider payment.

The fulfillment transaction should atomically do something equivalent to:

- read the order / entitlement / inventory reservation;
- if `fulfilled_payment_id == payment_id` (or terminal `fulfilled=true` with the same immutable provider reference), return the existing success result with **no counter mutation**;
- if another payment id already fulfilled the order, reject and reconcile;
- otherwise perform the one-time domain transition and store the provider payment/session id in the same transaction as the entitlement/inventory/counter mutation.

Then the outer event state can safely move to `completed`. If that final event-state write fails, the retry calls the fulfillment function again, observes that the payment/session has already been fulfilled, and returns the same success without repeating side effects.

### Concurrency rule

Do not implement the fulfillment check as a separate read followed by an unconditional write. Two concurrent deliveries can both observe "not fulfilled". Put the terminal fulfillment marker and the side-effect counters/entitlement writes in one serializable/transactional boundary, or use a unique database constraint/conditional update that provides the same exactly-once domain transition.

### Verification

Test the failure **between** the business side effect and the event-completion marker:

- first attempt performs fulfillment successfully;
- inject a failure writing the webhook event's `completed` state;
- retry the same event / Checkout Session;
- assert entitlement exists exactly once;
- assert sold/inventory counters changed exactly once;
- assert the second fulfillment invocation returns idempotent success rather than mutating state again.

Also test two concurrent calls with the same Checkout Session and ensure only one wins the fulfillment transition.

## Outbound payouts need a submitted state before retry

Outbound money movement has a different partial-failure boundary from inbound webhook fulfillment. The dangerous gap is the moment **after a transfer may have reached the network but before the application has durably recorded the transfer identifier**.

Never treat a post-send database error as evidence that the payout failed. Likewise, never reclaim a stale `processing` row by simply sending a fresh transfer when the previous attempt may already have submitted one.

A safe payout state machine separates at least:

- `reserved` / `debited` — internal balance is held exactly once;
- `submitting` — one worker owns the right to submit;
- `submitted` — the provider/network transfer id or transaction signature is durably attached to the payout row;
- `confirmed` / `finalized` — reconciliation has proved the external transfer reached the required settlement level;
- `failed_pre_submit` — nothing was sent; refund/retry is safe;
- `failed_post_submit` / `unknown` — submission may have happened; **reconcile the recorded transfer/signature instead of resubmitting or refunding blindly**;
- terminal `refunded` only after the application has proved no successful external payout exists.

Current Solana payout guidance uses exactly this application-level deduplication pattern: persist the transfer identifier for each payout row, and on retry skip/resume rows that already have a transfer id. For a transfer that stays pending beyond the expected window, re-poll the existing transfer instead of submitting a new one; only a settled `failed` outcome is safe to replace with a new transfer. Solana's production-readiness guidance also distinguishes `confirmed` from `finalized` and recommends finalized settlement for large withdrawals/compliance-sensitive flows.

**Sources:**
- https://docs.platform.solana.com/docs/payments/send-payouts
- https://solana.com/docs/payments/production-readiness

### Required persistence ordering

The durable boundary should make the transfer identifier recoverable before a generic retry can send again. Depending on the payment rail, this may mean:

1. create an application payout row with a unique idempotency key;
2. build/sign the outbound transaction so its signature/id is known;
3. persist `submitted` + signature/transfer id under a conditional/transactional state transition;
4. submit/confirm with provider-aware retry semantics, or use a provider API whose execute call itself accepts an idempotency key and returns a durable transfer object;
5. reconcile the **same** signature/transfer id after timeouts or worker crashes;
6. move to `confirmed/finalized` only when the required settlement evidence is observed;
7. refund only a payout that is proven not to have succeeded externally.

If the chosen library combines build/send/confirm into one call and exposes the signature only after the call returns, the application still must distinguish "call definitely failed before submit" from "call may have submitted but local persistence failed". A catch block that refunds every exception across send + persistence collapses those two cases and recreates the double-spend window.

### Retry rule

A stale `processing` lease is **not** sufficient proof that it is safe to submit again. Before a second send, inspect the payout row for a persisted transfer/signature and reconcile it. If the transfer identifier itself could have been lost after a successful external submission, treat the state as unknown/manual-reconciliation rather than manufacturing a second payout.

### Verification

Fault-inject all relevant boundaries:

- fail before external submission → balance restored exactly once;
- external transfer succeeds, then persistence of `submitted/completed` fails → no refund and no second transfer; reconciliation recovers the existing transfer;
- worker dies after submit → retry polls the existing transfer/signature rather than resubmitting;
- same idempotency key retried concurrently → one external transfer at most;
- pending transfer → re-poll, never fresh-submit merely because a local lease expired;
- high-value payout → do not mark terminal success before the configured finalized settlement level.

## Asynchronous synchronization

1. **Treat webhooks as the sync mechanism, not the trigger of record.** The PSP state is the source of truth for the money; webhooks are how you learn about changes. Design so that a missed webhook never causes permanent divergence: every state can also be refreshed by polling the PaymentIntent on a schedule or on user-driven reads.

2. **Handle out-of-order events.** A succeeded webhook can arrive before your create-call response returns, or a charge.refunded before charge.succeeded. Resolve by comparing event timestamps AND current state, and prefer reconciling against a fresh GET of the PSP object when an event looks stale. Never process events strictly in arrival order assuming ordering.

3. **Build an active-payment sweeper.** A cron job finds payments stuck in non-terminal states past their expected dwell time (processing > 15 minutes, requires_action > 24 hours) and reconciles them against the PSP. This is your safety net for dropped webhooks and is standard practice in production payment backends.

4. **Expire abandoned intents deliberately.** requires_action and requires_payment_method states should have a TTL after which your system transitions to canceled (and cancels the PSP intent if needed). Open-ended pending states accumulate and pollute metrics and reconciliation.

## Design pitfalls

1. **Booleans instead of states.** The is_paid + is_refunded + is_pending triple can represent impossible combinations (paid and pending simultaneously). An enum with validated edges makes illegal states unrepresentable.

2. **Transitioning on the client's say-so.** The checkout return page saying "success" is a hint, not a state transition. Only confirmed PSP signals (webhook or verified API status) move money-adjacent states. Otherwise a crafted return URL grants free entitlements.

3. **State machines for payments and subscriptions entangled in one table.** Keep the payment FSM and the subscription FSM separate, linked by ids. A subscription going past_due after a failed renewal is a subscription-level state driven by a payment-level failure; collapsing them creates combinatorial states nobody can reason about.

4. **No observability into dwell time.** Alert on state dwell percentiles (e.g., p95 time in processing). Rising dwell time is an early signal of PSP degradation or a stuck 3DS return flow — well before customers complain.

5. **Assuming an idempotent webhook claim makes fulfillment idempotent.** Event deduplication and fulfillment deduplication protect different boundaries. A crash or database error after fulfillment but before the event-completion marker can replay the same domain side effect unless the fulfillment transition itself is keyed and atomic.

6. **Refunding any exception after a payout send call.** Exceptions after submission can be persistence/confirmation failures, not evidence that the recipient was unpaid. Blindly refunding internal balance after a successful external payout creates a direct double-spend.
