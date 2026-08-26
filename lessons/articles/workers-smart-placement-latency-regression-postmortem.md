# Workers Smart Placement Latency Regression Postmortem

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

p95 API latency jumped from 38 ms to 340 ms immediately after enabling Smart Placement
on our primary orchestration Worker. No code changes shipped simultaneously. All requests
remained functional; only tail latency degraded. The regression persisted for 11 hours
before root cause was identified and Smart Placement was disabled.

## Context

Smart Placement (`placement: { mode: "smart" }`) is a Cloudflare feature that uses
historical invocation data to move a Worker closer to its back-end dependencies rather
than to the requesting user. Our orchestration Worker calls a Hyperdrive-connected
PostgreSQL primary in `eu-west-1` and a handful of third-party APIs headquartered in
Europe. Our user base is 70 % North American.

We enabled Smart Placement expecting it to shorten round-trips to the database. Instead
Cloudflare's algorithm, seeded by the first few hours of invocation telemetry, chose
`IAD` (Ashburn, VA) as the optimal location — an east-coast US PoP that added an
Atlantic round-trip to every database call rather than removing one.

---

## Timeline

| UTC | Event |
|-----|-------|
| 09:14 | `wrangler deploy --env production` with `placement: { mode: "smart" }` added to `wrangler.toml` |
| 09:16 | p95 latency begins climbing; alerting threshold (200 ms) breached at 09:21 |
| 09:35 | On-call engineer rules out D1 and KV issues; assumes cold-start spike |
| 11:00 | Second engineer notices Smart Placement was activated in the deploy; not yet correlated |
| 14:40 | Analytics Engine breakdown by `cf.colo` shows 68 % of requests now served from `IAD` instead of distributed PoPs |
| 20:22 | Smart Placement disabled; `placement` key removed; rollback deploy issued |
| 20:25 | p95 latency returns to 36 ms |

---

## Why Smart Placement Chose the Wrong PoP

Cloudflare's placement algorithm trains on actual invocation data after opt-in. During
the initial learning window (roughly the first 24–48 hours) the algorithm receives noisy
signal. Our Worker emits subrequests to Hyperdrive and to a European payment gateway.
Because North American users generated more traffic in the first hours, the subrequest
round-trips to `eu-west-1` appeared asymmetrically expensive from US PoPs — but the
algorithm did not account for the fact that the database latency budget from `IAD`
(~85 ms to `eu-west-1`) was still worse than distributing the Worker globally and
accepting per-user round-trip variance (~25 ms average across European PoPs).

Smart Placement optimises for **subrequest latency from the Worker** not for
**end-to-end latency including the user-to-PoP hop**. When most users are in North
America but all back-ends are in Europe, the algorithm can converge on a US PoP that
minimises its own round-trip to the origin while maximising the user-to-Worker hop.

---

## The Missed Validation Step

```toml
# wrangler.toml — change that triggered the incident
[placement]
mode = "smart"
```

We had no pre-deploy checklist item that required validating `cf.colo` distribution
before and after enabling placement features. The deploy was treated as a configuration
flag toggle, not a behavioural change that warranted traffic observation.

---

## Fix: Pin Placement or Disable Until Traffic Is Balanced

Option A — disable Smart Placement if back-ends and users are geographically opposed:

```toml
# wrangler.toml — back to default (user-proximate routing)
# [placement] section removed entirely
```

Option B — explicitly declare a preferred PoP set while Smart Placement trains:

```toml
[placement]
mode = "smart"
# Cloudflare does not yet expose a preferred_colo hint in wrangler.toml;
# use Waiting Room or Route weights to steer traffic while telemetry matures.
```

Option C — query the analytics to validate placement before trusting it:

```sql
-- Analytics Engine: check colo distribution after enabling Smart Placement
SELECT
  blob1   AS colo,
  count() AS requests,
  quantilesMerge(0.95)(latency_quantiles) AS p95_ms
FROM analytics_events
WHERE timestamp > NOW() - INTERVAL '2' HOUR
  AND index1 = 'orchestration-worker'
GROUP BY colo
ORDER BY requests DESC
```

If a single PoP accounts for > 50 % of volume within 2 hours of enabling Smart
Placement, treat that as a signal the algorithm is converging prematurely and disable.

---

## Anti-patterns

- Treating Smart Placement as a zero-risk configuration flag. It changes request routing
  globally and immediately, with no gradual rollout mechanism.
- Enabling Smart Placement during peak traffic when the learning window coincides with
  your busiest period — noisy early telemetry biases the model.
- Not alerting on `cf.colo` distribution changes; the PoP histogram shift was visible
  30 seconds after deploy but no alert existed for it.
- Assuming the feature optimises for end-to-end latency. It optimises for Worker-to-back-end
  subrequest latency only.

---

## Gotchas

- Smart Placement cannot be gradually rolled out via a percentage deployment; it is
  all-or-nothing per Worker script version.
- Disabling Smart Placement requires a new deploy (wrangler version increment); the
  previous placement decision is not immediately reverted in-flight.
- The Cloudflare dashboard does not display current Smart Placement decisions in real
  time; you must query Analytics Engine or use `cf.colo` headers to diagnose routing.
- Smart Placement ignores Waiting Room configurations — users held in a queue may be
  served from a different PoP than your intended PoP after release.

---

## Verification

After re-enabling Smart Placement in future:

1. Deploy to a non-production environment first and observe `cf.colo` distribution for
   at least 48 hours before promoting.
2. Add an Analytics Engine alert: if any single PoP exceeds 60 % of request share
   within 4 hours of a Smart Placement deploy, page on-call.
3. Capture p95 latency baseline 24 hours before and compare against 24 hours after
   enablement using the same Analytics Engine query.
4. Keep the previous wrangler version pinned and tested for rollback; confirm rollback
   restores the expected PoP distribution within 5 minutes.

---

## Related

- `workers-binding-version-drift-production-incident.md`
- `workers-subrequest-limit-fan-out-exceeded-incident.md`
- `cost-optimization-cloudflare-stack.md`
- `zero-downtime-deployment-workers.md`
- `hyperdrive-connection-string-rotation-zero-downtime.md`

---

## Sources

- Cloudflare Docs — Smart Placement: https://developers.cloudflare.com/workers/configuration/smart-placement/
- Cloudflare Blog — "Announcing Smart Placement for Cloudflare Workers"
- Analytics Engine SQL API reference: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Internal incident ticket INC-2026-0341
