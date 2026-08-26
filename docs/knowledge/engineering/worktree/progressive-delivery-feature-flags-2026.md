# progressive-delivery-feature-flags-2026

**Issue:** The team adopted feature flags but still couples "deploy" to "release." Code is merged but hidden behind `if (false)` blocks, or releases are batched into scary big-bang deployments. The team doesn't know how to decouple deployment from release using progressive delivery.
**Date:** 2026-08-13
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

A team deploys to production 5x/day but releases to users 1x/week — because every "release" is a coordinated event. Code sits merged but dormant behind manual config edits or commented-out blocks. When something goes wrong, rollback means redeploying old code (slow, risky). The team has feature flags but uses them as on/off switches, not as a delivery strategy.

## The core idea: deploy ≠ release

| Term | What it means | Triggered by |
|---|---|---|
| **Deploy** | Code reaches production servers | CI/CD pipeline (automated, frequent) |
| **Release** | Users can access the feature | Feature flag / config (decoupled, controlled) |
| **Rollout** | Gradually turning a flag on for more users | Progressive delivery (percentage, cohort, segment) |
| **Rollback** | Turning a flag off (code stays deployed) | Flag toggle (seconds, no redeploy) |

Once these are separate, you can deploy continuously without user-visible risk, and release/rollback without shipping code.

## The 5-stage progressive delivery funnel

1. **Dark launch** — code in production, flag off for everyone. Run the new path in shadow (log results, don't return them). Catch prod-only bugs with zero user impact.
2. **Internal dogfood** — flag on for employees only (`@company.com` segment). Eat your own dog food before users do.
3. **Canary** — flag on for 1-5% of users (random or beta cohort). Watch error rates, latency, conversion.
4. **Ramp** — increase to 25% → 50% → 75% over hours or days, gated on metrics staying green.
5. **General availability** — flag on for 100%. Optionally remove the flag (see "flag debt" gotcha) after a stable period.

At any stage, if metrics degrade, **kill the flag** — instant rollback, no redeploy.

## Platform choice in 2026

| Platform | Model | Best for |
|---|---|---|
| **LaunchDarkly** | SaaS, enterprise | Large teams, strong RBAC, experimentation |
| **Unleash** | Open-source, self-hostable | Privacy-sensitive, on-prem needs |
| **Statsig / DevCycle / Flagsmith** | SaaS + edge | Good free tiers, developer-friendly |
| **GrowthBook** | Open-source + experiment-aware | Teams doing A/B testing natively |
| **In-house (Redis/DB + SDK)** | Custom | Small scale or exotic constraints |

Rule of thumb: start with Unleash or GrowthBook (free, self-hosted) until you need LaunchDarkly's enterprise features. Do NOT build your own flag service for >5 flags — the edge cases (consistency, audit, offline) are harder than they look.

## Anatomy of a well-behaved flag

```typescript
// Good: short-circuit early, evaluate server-side, log the decision
if (flags.evaluate('new-checkout-flow', { userId, tier })) {
  return newCheckout();
}
return legacyCheckout();
```

- **Evaluate server-side or at the edge** — client-side flags leak unreleased features and are flickery.
- **Log flag decisions** — you cannot debug a rollout without knowing who saw what. Pipe evaluations to your analytics/metrics store.
- **Default to safe** — if the flag service is down, default to the legacy path, not the new path. Failure mode is "feature off," not "feature on for everyone unexpectedly."

## Metrics-gated rollouts (the real power)

Wire the rollout to your observability stack:
- **Error budget**: if error rate for new-path traffic > baseline + 1%, auto-rollback the flag.
- **Latency SLO**: if p95 for new path > threshold, pause ramp.
- **Conversion guardrail**: if conversion drops > X% vs. control, stop and investigate.

Tools like LaunchDarkly and GrowthBook can automate this: flag ramps up only while metrics stay green; it auto-reverts if a guardrail trips. This is the difference between "feature flags" and "progressive delivery."

## Gotchas

- **Flag debt**: flags accumulate. Every flag is a branch in your code that must be maintained, tested, and eventually removed. Enforce a TTL: every flag has an expiry date; after it, a cleanup ticket auto-creates. Aim to remove flags within 2-4 weeks of full rollout.
- **Testing the dead branch**: CI must test BOTH flag states. A common bug — the new path works, the flag is flipped off, and the legacy path has rotted because nobody tested it. Add a CI matrix that runs tests with each flag on and off.
- **Client-side flicker**: if flags are evaluated client-side, users see the old UI flash before the new one loads (or vice versa). Use server-side rendering or a bootstrap to inject the flag state into the initial HTML.
- **Cross-flag interactions**: flag A and flag B individually work; together they break. If flags are not independent, document dependencies and gate rollouts so incompatible combos can't co-activate.
- **"Just a quick flag" becomes permanent**: developers add a flag to "safely ship," then never remove it. Five years later the codebase has 200 flags, half referring to dead features. The TTL rule is the only cure.
- **Rollback ≠ undo data side-effects**: flipping a flag off hides the feature but doesn't un-write the database rows it created. For destructive or data-migrating features, the rollback path must include a data-cleanup plan, not just a flag toggle.
- **Identity-based rollouts cause inconsistency**: if a user is in the 50% cohort, they see the new feature; if they switch devices or clear cookies (client-side flags), they flip-flop. Use a stable server-side identifier (user ID, account ID), never a random client-side hash.

## Related
- `feature-flags-2026.md`
- `feature-flag-rollout.md`
- `canary-deployment-strategy.md`
- `rollback-strategy.md`
- `trunk-based-development-2026.md`
