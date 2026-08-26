# Payment Orchestration — Multi-PSP Routing, Cascade Failover, and Cost Optimization

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your e-commerce platform processes payments through a single PSP.
When that PSP has an outage, all transactions fail for 45 minutes
and you lose $200K in revenue. Your authorization rate is 82% but
industry benchmarks show 90%+ is achievable with smart routing.
You add a second PSP for redundancy but hardcode the failover logic,
which does not distinguish between soft declines (retry-eligible)
and hard declines (stolen card — do not retry), causing duplicate
charges and fraud exposure.

## Context

Payment orchestration platforms sit above multiple PSPs, acquirers,
and local payment methods behind a single API. They handle three
core functions: smart routing (choosing the best PSP per transaction
based on cost, approval rate, and geography), cascade failover
(retrying soft declines through alternate providers), and unified
analytics across providers. The market is estimated at $2B in 2025,
projected to reach $6-9B by the early 2030s. Industry benchmarks
show AI-driven routing delivers an average 8% lift in authorization
rates, and dynamic cost-optimized routing saves 20-40% on processing
fees by selecting the cheapest eligible PSP per transaction.

## Smart routing

```
Smart routing evaluates per transaction:

  Signal                    Routing decision
  ──────────────────────────────────────────────────────────
  Card BIN / type           Domestic acquirer for local cards
  Currency                  PSP with best FX rates
  Transaction amount        High-value → highest-reliability PSP
  Customer geography        Regional PSP for lower cross-border fees
  MID capacity              Distribute across MIDs to avoid limits
  Time of day               Route around maintenance windows
  Historical approval rate  PSP with best rate for this card type

  Optimization targets (pick one primary):
    → Authorization rate (maximize approvals)
    → Cost (minimize processing fees)
    → Latency (minimize response time)
    → Risk-adjusted (balance rate vs fraud exposure)
```

## Routing rules configuration

```json
{
  "routingRule": {
    "name": "eu-card-cost-optimized",
    "conditions": {
      "currency": ["EUR"],
      "paymentMethod": "card",
      "country": ["DE", "FR", "NL"]
    },
    "priority": [
      { "psp": "acquirer_a", "weight": 70, "maxCostBps": 180 },
      { "psp": "acquirer_b", "weight": 30, "maxCostBps": 210 }
    ],
    "failover": {
      "onSoftDecline": ["acquirer_b", "acquirer_c"],
      "onTimeoutMs": 4000,
      "onHealthScoreBelow": 0.85,
      "maxCascadeAttempts": 2
    }
  }
}
```

```
Rule evaluation flow:

  1. Transaction received → match against routing rules
  2. Conditions evaluated: currency, country, payment method
  3. Weighted distribution across eligible PSPs
  4. If declined or timed out → evaluate failover policy
  5. Cascade to next PSP (if soft decline) or fail (if hard decline)
  6. Log routing decision + outcome for analytics
```

## Cascade vs failover

```
Two distinct mechanisms — often confused:

  Cascade (decline-driven):
    Triggered by a soft decline from the primary PSP.
    Retries the same transaction through an alternate PSP.
    Only for retry-eligible decline codes.
    Must distinguish soft vs hard declines.

  Failover (availability-driven):
    Triggered by PSP outage, timeout, or health score breach.
    Reroutes all transactions away from unhealthy PSP.
    Detected via continuous health monitoring.
    Circuit-breaker pattern — mark PSP unhealthy, route around.

  Soft decline examples: insufficient funds, temporary hold,
    do not honor (some issuers), network timeout
  Hard decline examples: stolen card, closed account,
    fraud block, invalid card number
```

## Provider health scoring

```
Continuous health monitoring signals:

  Metric              Healthy          Degrade threshold
  ──────────────────────────────────────────────────────────
  Latency P95         < 2s             > 4s
  Error rate          < 1%             > 5%
  Approval rate       > 85%            < 75% (rolling 15min)
  Uptime              > 99.9%          < 99.5%

  Health score formula (simplified):
    score = w1 × (1 - error_rate)
          + w2 × approval_rate
          + w3 × (1 - latency_normalized)

  When score drops below threshold:
    → Mark PSP as degraded
    → Shift traffic to healthy PSPs
    → Continue monitoring for recovery
    → Restore traffic gradually (not all at once)
```

## Cost optimization

```
True cost per transaction (all-in):

  Component              Example
  ──────────────────────────────────────────────────────────
  Base processing rate   1.5% + $0.30
  FX markup              0.5-2.0% on cross-currency
  Cross-border fee       0.3-0.5% on international
  Scheme assessment      0.01-0.15% (Visa/Mastercard)
  Chargeback fee         $15-25 per dispute

  Dynamic cost routing selects the cheapest eligible PSP
  per transaction considering all components, not just the
  headline processing rate.

  Reported savings: 20-40% on processing fees.
```

## Anti-patterns

- **Unbounded cascading** — retrying a hard decline (stolen card,
  fraud block) across multiple PSPs can trigger duplicate
  authorizations, increase fraud exposure, and violate card
  network rules. Cascade logic must distinguish soft vs hard
  decline codes.
- **No idempotency across retries** — failing to tag retried
  transactions causes double-charging when a "failed" transaction
  actually succeeded downstream before the failover fired. Use
  idempotency keys for all payment requests.
- **Routing on headline rate only** — ignoring FX markup, cross-
  border fees, and scheme assessments produces routing decisions
  that look cheaper but cost more in total.
- **Static routing rules** — rules set once and not revisited drift
  as PSP performance and pricing change. Review routing performance
  monthly against live approval-rate and cost data.

## Gotchas

- **Health checks too sensitive or too slow** — overly conservative
  thresholds delay failover during real outages (lost revenue).
  Overly sensitive thresholds cause flapping between PSPs on
  normal jitter. Tune based on historical variance.
- **Single point of failure in orchestration** — the orchestrator
  becomes the critical dependency. Without its own redundancy,
  multi-PSP routing does not actually buy resilience.
- **Card network retry rules** — Visa and Mastercard limit the
  number of retry attempts for certain decline codes. Exceeding
  retry limits can result in fines. Check network-specific rules
  before configuring cascade depth.
- **Treating cascade and failover as one mechanism** — conflating
  decline-driven retry with availability-driven rerouting leads
  to wrong responses, such as retrying at the same unhealthy PSP
  instead of rerouting to a healthy one.

## Verification

- Routing rules distinguish soft decline (cascade) from hard decline (fail).
- Idempotency keys used for all payment requests and retries.
- Provider health scoring monitored with appropriate thresholds.
- Cost optimization considers all-in cost, not headline rate only.
- Maximum cascade attempts capped per card network rules.
- Routing performance reviewed monthly against approval-rate data.

## Related

- `documentation/docs/policies/payments/network-tokenization-lifecycle.md`
- `documentation/docs/policies/payments/subscription-billing-dunning-retry.md`
- `documentation/docs/policies/architecture/api-gateway-patterns-rate-limiting-routing.md`

## Source URLs (verified 2026-08-16)

- What Is Payment Orchestration? Complete Guide 2026 — https://solidgate.com/blog/payment-orchestration/
- Payment Orchestration 2026 Guide — https://gr4vy.com/posts/payment-orchestration-2026/
- Failover and Cascading Payments — https://www.clearfunction.com/insights/failover-cascading-payments-ensuring-payments-go-through-even-when-things-go-wrong
- Dynamic Transaction Routing and Payment Orchestration — https://www.ixopay.com/blog/dynamic-transaction-routing-and-payment-orchestration-better-together
