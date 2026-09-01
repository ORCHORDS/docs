# Feature Flag Pattern Launch Darkly Style Rollout

## Scope

This article covers feature flags used for progressive delivery in the style popularized by commercial flag-management platforms: decoupling deploy from release, percentage rollouts keyed to identity or attribute, targeting rules per cohort, and kill switches. Scope covers flag lifecycle and taxonomy, evaluation architecture (local evaluation versus remote evaluation), rollout mechanics, and flag hygiene. It excludes simple compile-time configuration, permanent entitlement flags treated as product configuration (which need different governance), and A/B testing statistics except where rollout mechanics overlap.

## Workflow or implementation guidance

Begin with a taxonomy, because flags with different lifespans and owners need different processes: release flags (short-lived, hide incomplete work, die at full rollout), experiment flags (owned by growth, die with the experiment), ops flags (kill switches and degraded-mode switches, owned by on-call, may live for years), and permission flags (long-lived entitlement). Conflating them produces the classic pathology — a release flag that lived two years because removing it felt risky.

Architect evaluation for latency and correctness at the edge. The robust pattern is local evaluation: the full flag configuration — targeting rules, percentages, segment membership — is delivered to the runtime, and evaluation happens in-process with no network hop on the request path. Configuration propagates via streaming updates or fast polling; flags resolve in microseconds from a local structure:

```ts
function evaluate(flagKey: string, user: UserContext, cfg: FlagConfig): Variation {
  const flag = cfg.flags[flagKey];
  if (!flag) return flagDefaults[flagKey];           // fail-safe default, logged
  if (matchTargeting(flag.rules, user)) return flag.serve;
  return bucket(hash(flagKey + user.stableId), flag.percentage);
}
```

Two evaluation details carry most of the correctness weight. Hashing must combine the flag key with a stable user identifier, so a user's bucket assignment is deterministic across evaluations and independent across flags — hashing only the user id makes every 10 percent flag affect the same 10 percent of users, compounding exposure in ways experiments cannot untangle. And the stable identifier must be genuinely stable: session ids re-bucket users mid-experience, producing flicker where a feature appears and disappears between requests.

Rollout mechanics follow one progression: dark (zero percent) on production infrastructure, internal dogfood at one hundred percent for a staff cohort, small percentage ramp with monitoring gates at each step, then one hundred percent, then code cleanup and flag removal. The percentage steps should be defined in advance with the metric gates between them — error rate, latency, and business guardrails — so that pausing or rolling back is a decision already made, not a meeting scheduled at 2 a.m. Kill switches are the same machinery in reverse: a pre-positioned ops flag whose evaluation path is exercised daily by ordinary traffic, so that using it under incident pressure is not its first execution.

## Controls

Flag hygiene is the difference between a delivery accelerant and permanent technical debt, so control it with inventory and enforcement. Maintain a flag inventory with owner, type, creation date, and target removal date; enforce maximum age by type (release flags measured in weeks) with automated nagging to the owner and, ultimately, default-on removal where the team has agreed the default is safe. Require every flag to declare a fail-safe default — the variation served if evaluation infrastructure is unreachable — reviewed at creation, because the default is the behavior during your worst outage. Gate percentage increases behind monitoring: the rollout runbook specifies the metrics, thresholds, and the automatic rollback trigger for each flag. Segment governance for personalization-style targeting: rules that target protected attributes or individual users need review, since a mis-scoped rule silently ships to production. Audit flag changes: who changed what, when, and from where — the change history of a rollout is part of the incident record when something breaks. Cap concurrent active release flags per team; beyond a handful, the combination space of code paths exceeds anyone's ability to test.

## Validation evidence

Evaluation correctness is verified with property tests: for random flag configurations and user populations, assert determinism (same user and config always yields the same variation), monotonicity under percentage increase (users who had the feature keep it as percentage rises — critical for not yanking features mid-session), and independence across flags (bucket assignments for distinct flag keys are uncorrelated across a large user sample, catching the hash-input bug). Configuration propagation evidence: measure flag-change-to-runtime-visibility latency across the fleet under streaming and under polling, since a rollout gated on a metric assumes the fleet has actually received the new configuration. Fail-safe drill: sever evaluation infrastructure in staging and assert every flag serves its declared default with correct logging, never an error or an arbitrary value. Rollout rehearsal: run a full dark-to-100 progression against a synthetic metric in staging, exercising the ramp gates and the rollback trigger, before the first production use of the process. Production evidence for each real rollout: guardrail metric traces per ramp step with the decision (proceed, hold, rollback) recorded, plus the flag's removal diff and date — the completed lifecycle is itself the evidence that the hygiene controls function.

## Failure modes and correction

The most common failure is flag accumulation: flags ship, reach one hundred percent, and are never removed, each one a permanent branch in the codebase, until every change touches a matrix of stale variations. Correct with enforced age limits and by treating flag removal as part of the definition of done for the feature. The second is bucket instability: evaluation keyed on session ids or on a hash that excludes the flag key, so users flip between variations across requests and experiments return noise. Correct with stable user keys and per-flag hash salting, verified by the determinism and independence tests. The third is configuration drift at the edge: runtimes serving different flag configurations because streaming silently disconnected, so different parts of the fleet run different behavior. Correct with configuration version stamping exposed in diagnostics and an alert on fleet version divergence. A fourth is the unexercised kill switch: an ops flag that has never been flipped, whose code path is broken by an unrelated refactor — discovered during the incident it was built for. Correct by scheduling periodic kill-switch drills. A fifth is default-by-accident: evaluation failure returns a variation chosen by exception fallthrough rather than declared policy. Correct by making the fail-safe default an explicit, reviewed declaration per flag.

## Limitations

Flags multiply code paths combinatorially, and testing effort grows with the product of active flags — the pattern trades merge conflicts and long-lived branches for runtime branch complexity, which is usually the right trade but is not free. Local evaluation pushes full targeting configuration to every runtime, which leaks segment definitions and percentage logic to any party that can read runtime configuration — acceptable internally, sometimes not for fine-grained personalization. Flag changes bypass deploy pipelines: a misconfigured rollout affects production in seconds with no build, no review gate, and no artifact to roll back to, so the audit and guardrail controls are load-bearing rather than optional. Statistical validity of percentage rollouts degrades under small populations and correlated bucketing, and the pattern provides no experiment-design rigor of its own. Long-lived flags entrench divergence between what the code supports and what anyone uses, raising the cost of eventual removal the longer they live. Finally, identity-based targeting depends on identity quality: anonymous or shared-device contexts make per-user rollouts approximate at best, and any per-user guarantee must be scoped to authenticated traffic only.

## Canonical sources

- Fowler — Feature Toggles (one of the earliest systematic treatments of flag taxonomy and hygiene): https://martinfowler.com/articles/feature-toggles.html
- Microsoft — Manage feature flags in Azure App Configuration (flag lifecycle and configuration management): https://learn.microsoft.com/en-us/azure/azure-app-configuration/manage-feature-flags
- Microsoft Azure Architecture Center — External Configuration Store pattern (configuration delivery decoupled from deploy): https://learn.microsoft.com/en-us/azure/architecture/patterns/external-configuration-store
