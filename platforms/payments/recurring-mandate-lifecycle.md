# recurring-mandate-lifecycle

**Issue:** Recurring debits against cards, bank accounts, and UPI in India are not authorized per-charge: they run against a mandate, a standing consent the customer grants once with Additional Factor Authentication (AFA). The Reserve Bank of India's e-mandate framework makes that consent object a regulated artifact with its own lifecycle rules: AFA at registration, modification, and revocation; AFA on the first debit; per-transaction amount thresholds above which AFA is required again; advance pre-debit notification with a customer withdrawal right; and scope covering cards, UPI Autopay, and wallets uniformly. RBI's consolidated Digital Payments E-Mandate Framework (2026 directions, notified late 2025) raised the no-AFA per-transaction threshold to 15,000 rupees, simplifying higher-value subscriptions but resetting integrations built around the old 5,000 rupee general limit. Engineering must model the mandate as a first-class stateful entity, not as a flag on a subscription, or debits will be rejected at scale and churn will spike.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Mandate registration flow

1. **Model a full state machine.** Mandates move through created, pending-activation (AFA not yet completed), active, suspended, revoked-by-customer, revoked-by-merchant, and expired. Debit presentment must be legal only from active, and every transition must be persisted with the PSP's mandate reference alongside your subscription id.
2. **AFA gates four moments.** AFA (OTP, 3DS, or UPI PIN depending on rail) is required at mandate registration, at any modification (amount increase, frequency change), at revocation, and on the first transaction. Building modification flows that silently skip re-AFA will produce rejected mandates at the sponsor bank, not graceful degradation.
3. **Store the mandate cap at registration.** The registered maximum per-transaction amount and the mandate's own validity period bound every future debit. A subscription upgrade that exceeds the registered amount requires mandate amendment (with AFA), so product pricing changes must trigger a mandate-migration queue.

## Threshold and AFA rules

1. **Apply the 15,000 rupee no-AFA threshold per debit.** Under the 2026 framework, recurring transactions up to 15,000 rupees per transaction proceed without per-cycle AFA; amounts above that require AFA on that debit. The prior regime (5,000 rupees general, 15,000 for select categories like insurance and mutual funds) persisted for years, so older integration guides and PSP behaviors are stale: verify your PSP passes the new threshold before relying on it.
2. **Compute AFA need dynamically at presentment.** Do not bake the threshold into stored mandates; evaluate amount against the current regulatory limit at debit time, with the limit loaded from config that compliance can update. Currency-converted amounts (a USD price charged in INR) fluctuate across the threshold, so the AFA path must be available for any debit, not just plan upgrades.
3. **Handle AFA-required debits as a customer-facing flow, not a failure.** When a debit exceeds the threshold, the system must trigger a notification-and-approval interaction (PSP-driven AFA page or UPI request) and treat non-response as a retryable dunning event with a defined expiry, distinct from card decline codes.

## Pre-debit notification mechanics

1. **Send the notification with a withdrawal window.** RBI requires advance pre-debit notification to the customer with the ability to cancel that specific debit (commonly delivered a day ahead of presentment). The notification job is part of payment execution: debit scheduling emits notifications, waits out the withdrawal window, checks for cancellation, then presents.
2. **Debit details must match the notification.** Amount, date, and merchant name in the notification must match the actual presentment; mismatches are treated by banks as a compliance failure and can invalidate the mandate.
3. **Honor cancellation of a single debit separately from mandate revocation.** Customers can cancel one upcoming charge without cancelling the mandate; model per-cycle cancellation as its own entity so a skipped cycle does not corrupt subscription state.

## Debit execution and failure handling

1. **Present within the scheme's execution window.** E-mandate debits are expected on or after the agreed debit date within a defined window (per current RBI guidance, execution within a few days of the intended date); presenting months of back-debts at once after downtime is non-compliant and triggers returns. Backfill logic must cap catch-up cycles and fall back to a fresh mandate when the gap is too large.
2. **Suspend mandates after consecutive failures.** Define the failure-to-suspension threshold (commonly 2-3 failed cycles), enter the suspended state automatically, and route the customer to a re-authorization flow rather than hammering a dead instrument. UPI Autopay failures (insufficient balance is the dominant reason) need a retry cadence aware of salary-cycle timing.
3. **Distinguish rail-specific behavior.** Card mandates flow through e-mandate registration with the card network's recurring data; UPI Autopay mandates live with the NPCI ecosystem and have their own per-debit limits and pause/resume semantics. The mandate state machine is shared, but presentment adapters are per rail.

## Cross-scheme generalization

1. **Map PSP webhook events to state transitions explicitly.** Mandates registered at a PSP report lifecycle events (activated, amended, revoked, expired, failed); each must map to exactly one internal transition with idempotent handling, since PSPs redeliver mandate events as aggressively as payment events.
2. **Generalize beyond India.** SEPA direct debit mandates carry their own amendment and termination rules under the EPC scheme; card-on-file recurring in the US follows network stored-credential rules with MIT/CIT flags. Represent mandates with a scheme field and keep regime-specific rules (thresholds, notification duties) in per-scheme policy modules so the state machine core stays shared.
3. **Support customer-initiated revocation everywhere.** Regulators converge on requiring easy exit: expose revocation in-product and propagate it to the PSP immediately, because continuing to debit a revoked mandate converts a churn event into a regulatory one.
