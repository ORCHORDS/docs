# feature-flag-deploy-coupling

**Issue:** How to decouple code deployment from feature release using flags so rollback is instant
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams ship code and features at the same time. When a feature causes a regression the only fix is a full rollback, which also reverts unrelated changes. Feature flags break this coupling — code ships dark, the feature lights up separately.

## Pattern / Solution
**Ship dark, release deliberately**
```
Deploy (code off by default) → QA in prod → % rollout → 100% → flag cleanup
```

**Flag taxonomy**
| Type | Lifetime | Example |
|---|---|---|
| Release flag | Days–weeks | `new_checkout_flow` |
| Experiment flag | Sprint | `checkout_cta_text` |
| Ops / kill switch | Permanent | `payments_enabled` |
| Permission flag | Permanent | `beta_access` |

**Implementation pattern (SDK-agnostic)**
```typescript
// Evaluate at request time, never at startup
const useNewCheckout = await flags.evaluate('new_checkout_flow', {
  userId: user.id,
  env: process.env.APP_ENV,
});

if (useNewCheckout) {
  return newCheckoutHandler(req, res);
}
return legacyCheckoutHandler(req, res);
```

**Coupling rules**
- Flag evaluation must be synchronous and cached locally (≤1 ms) — never block a request on a remote call
- Default value must be the safe/old path (`false` = old behavior)
- Flags must be evaluated server-side for consistent bucketing; client-side flags for UI-only changes only
- Remove flags within one sprint of 100% rollout to avoid flag debt

## Gotchas
- Nested flags create combinatorial complexity — avoid more than 2 levels deep
- "Default on" flags confuse rollback; always default to the known-good state
- Flag state is not versioned with code — document in the PR what flag gates the change
- Do not gate database migrations behind flags; migrations and flags operate at different layers

## Related
- `feature-rollout-strategies.md`
- `canary-deployments.md`
- `rollback-runbook.md`
- `environment-promotion-gates.md`
