# gateway-failover-circuit-breakers

**Issue:** When a payment service provider goes down or degrades, a system without failover does not just return errors: checkout requests hang until timeout, users abandon, and naive retry storms amplify the PSP's distress while doubling authorization risk. Payment routing needs failure detection fast enough to reroute within the customer's checkout attention span (a few seconds at most), but not so twitchy that a handful of random declines trips it. The engineering answer combines circuit breakers (per-endpoint failure detection with closed/open/half-open states), health probing, and decline-aware rerouting onto a secondary PSP, while respecting the hard constraint that rerouting a payment is not free: tokens, auth holds, and idempotency all cut across provider boundaries.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Failure detection

1. **Classify failures before counting them.** Only some failures indicate a PSP problem: connection errors, TLS failures, 5xx responses, and timeouts are infrastructure signals; 4xx and card declines are business outcomes. A circuit breaker keyed on total error rate will trip on a fraud attack's decline spike; key it on infrastructure-class failures only.
2. **Use a sliding window, not consecutive counts alone.** Trip on a rate threshold (for example, more than 50% infrastructure failures over a 20-30 request window) or a small consecutive-failure count. Guidance for critical payment flows suggests aggressive thresholds of 2-3 failures, because every additional failed attempt is a customer lost; non-critical reads can tolerate 10.
3. **Treat latency as a failure mode.** A PSP that responds in 15 seconds is effectively down for checkout. Track p95/p99 per endpoint and trip a latency circuit when the slow bucket exceeds a budget (commonly 2-3 seconds for synchronous card authorization), so the request can be rerouted rather than burned.

## Circuit breaker design

1. **Implement the three-state model.** Closed (normal traffic, failures counted), Open (requests fail fast without touching the PSP), and Half-Open (limited probe traffic to test recovery). This is the canonical pattern from the Azure/AWS architecture guidance, and it exists precisely to stop callers from hammering a failing dependency.
2. **Scope breakers per endpoint and operation.** A breaker per PSP is too coarse: the capture endpoint can be failing while authorization is healthy. Scope by PSP plus operation (authorize, capture, refund, webhook verification, currency conversion), and consider regional scoping when the PSP has geographically isolated incidents.
3. **Fail fast with a reroute, not an error.** When a breaker is open, the checkout path should immediately attempt the secondary PSP within the same request, using the remaining timeout budget. The customer should never see the outage.

## Failover routing mechanics

1. **Solve the tokenization mismatch first.** Cards vaulted with PSP A's token are unusable at PSP B; this is the single biggest constraint on rerouting stored credentials. Network tokens (device PANs from Apple Pay/Google Pay, or network tokenization services) and multi-PSP vault designs are the two structural answers; decide before you need failover, not during it.
2. **Reroute only idempotent-safe requests.** A timeout is ambiguous: the authorization may have succeeded at the PSP even though you never saw the response. Before rerouting a timed-out authorize, query the original attempt by your idempotency key at PSP A (or reconcile asynchronously) to avoid double-charging. Rerouting on connection-refused is safe; rerouting on read-timeout is not.
3. **Budget the total request time.** Split the checkout timeout budget across attempts (for example, 3s primary, 2s fallback) so the customer waits a bounded 5-6 seconds worst case rather than two full sequential timeouts.

## Decline-code-aware rerouting

1. **Reroute only retryable outcomes.** Hard declines (stolen card, invalid card, do-not-honor on fraud grounds) will fail identically everywhere; rerouting them just burns fees and doubles risk signals. Route soft and infrastructure-adjacent failures (issuer unavailable, gateway timeout, processor error) to the alternate PSP.
2. **Maintain a decline-code normalization table.** Each PSP documents decline codes differently. Normalize to an internal taxonomy (hard/soft/transient/auth-required) so routing rules, retry logic, and customer messaging operate on one vocabulary.
3. **Cap reroute attempts per payment.** One primary, one fallback is the sane ceiling for customer-initiated flows. More attempts increase authorization holds, fraud flags at the issuer, and latency.

## Observability and recovery

1. **Probe with synthetic traffic.** Half-open recovery based only on real customer traffic is unethical A/B testing on revenue. Run low-rate synthetic authorizations (zero-amount or test-BIN) against a degraded PSP to detect recovery before shifting customers back.
2. **Replay failed payments where consent allows.** Queue payments that failed during the outage window (before the breaker opened) and retry them on the healthy PSP, respecting user consent for delayed charges; subscriptions give more latitude than one-off checkouts.
3. **Chaos-test failover quarterly.** Inject PSP latency and errors in staging (or via a feature flag on a small traffic slice in production) and verify: breaker trips within the target time, reroute succeeds, no duplicate charges appear in reconciliation, and alerts fire. Failover code that has never executed is a hypothesis, not a capability.
