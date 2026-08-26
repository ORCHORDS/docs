# feature-flags-2026

**Issue:** A team deploys a feature half-finished. The team merges incomplete code to main. The build breaks. The team reverts. The feature is delayed 2 weeks. The team needs feature flags.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Feature flags decouple deploy from release. The 2026 default: every merge goes to main; flags control exposure. Trunk-based development without flags is fragile; flags without trunk is overhead.

## Root cause

A feature flag is a runtime check that determines whether a code path is active. The 4 flag types cover the 2026 use cases.

## The 4 flag types

| Type | Use case | Lifecycle |
|---|---|---|
| Release flag | ship incomplete code; turn on when ready | short (days to weeks) |
| Experiment flag | A/B test, canary rollout | medium (weeks) |
| Operational flag | kill switch, dynamic config | long (months to permanent) |
| Permission flag | user/role/tenant gating | long (permanent) |

The 4 types serve different purposes; the lifecycle is the main difference.

## The 5 flag system features (2026 default)

A 2026 production flag system has 5 features.

1. **Boolean toggles** — on/off
2. **Percentage rollouts** — 1% → 10% → 50% → 100%
3. **Targeted rollouts** — by user ID, segment, region
4. **Kill switch** — instant off for emergencies
5. **Audit log** — who changed what, when

The 5 features cover the 2026 use cases.

## The 5 commercial flag systems

| System | Strength | Trade-off |
|---|---|---|
| LaunchDarkly | full-featured, enterprise | $$$$ |
| Unleash | open source, self-hostable | operational burden |
| Flagsmith | open source + commercial | mid-tier |
| PostHog | open source, integrated with product analytics | tied to PostHog |
| ConfigCat | simple, fast | less enterprise |

The 2026 default for small teams: PostHog or Flagsmith. For enterprise: LaunchDarkly.

## The 5 best practices

1. **Decouple deploy from release.** Merge incomplete code behind a flag; turn on when ready.
2. **Use the simplest flag type.** Boolean for most; percentage rollout for gradual; targeted for segments.
3. **Track flag lifecycle.** Create, default off, default on, remove. Don't let flags rot.
4. **Test both flag states.** The code must work with flag on and flag off.
5. **Document the flag.** A flag is technical debt; the team should know what each flag does.

## The 4 anti-patterns

1. **No flag retirement.** Old flags accumulate; the code becomes unmaintainable.
2. **Flag for everything.** Each flag adds a branch; thousands of flags = thousands of branches.
3. **No default.** A flag with no default is a runtime crash waiting to happen.
4. **Flag for one-time migrations.** Use config or migration script, not a flag.

## The 5-step flag lifecycle

1. **Create** — name, description, default (usually off), owner
2. **Use** — `if (flags.isEnabled('feature-x')) { ... }` in code
3. **Roll out** — 1% → 10% → 50% → 100% (canary)
4. **Remove** — delete the flag, delete the code branch
5. **Audit** — log who changed what, when, why

The 5-step lifecycle is the 2026 production pattern.

## The 5 pattern types in code

```typescript
// 1. Boolean (release flag)
if (flags.isEnabled('new-checkout')) {
  return newCheckout();
} else {
  return oldCheckout();
}

// 2. Percentage rollout
if (flags.percentageEnabled('new-checkout', userId, 25)) {
  return newCheckout();
}

// 3. Targeted (segment)
if (flags.inSegment('new-checkout', { region: 'us-west' })) {
  return newCheckout();
}

// 4. Kill switch (operational)
if (flags.isKilled('payment-processor-v2')) {
  return oldPaymentProcessor();
}

// 5. Permission (role/tenant)
if (flags.hasPermission('beta-features', { userId, tenantId })) {
  return betaFeatures();
}
```

The 5 patterns cover the 2026 use cases.

## The 4 flag naming conventions

| Convention | Example | Strength |
|---|---|---|
| `feature-{name}` | `feature-new-checkout` | clear purpose |
| `{system}-{name}` | `payment-v2` | clear system |
| `exp-{name}` | `exp-pricing-test` | clear experiment |
| `kill-{system}` | `kill-payment-v2` | clear operational |

The 4 conventions are 2026 standard. Pick one; stick to it.

## The 4 technical integration patterns

| Pattern | How | When |
|---|---|---|
| Library call | `flags.isEnabled('name')` | most languages |
| Config file | `flags.json` with values | simple apps |
| Edge function | flag check at CDN | global rollouts |
| Server-side | flag SDK on backend | complex targeting |

The 4 patterns cover the 2026 use cases. Most teams use library call + config file.

## The 5 launch-darkly alternatives (OSS / mid-tier)

| Tool | License | Hosted? | Strength |
|---|---|---|---|
| Unleash | Apache 2.0 | yes + self-host | full-featured OSS |
| Flagsmith | BSD-3 | yes + self-host | simple, fast |
| PostHog | MIT | yes | analytics integration |
| ConfigCat | MIT / commercial | yes | simple, fast |
| GrowthBook | MIT / commercial | yes + self-host | A/B testing focus |

The 2026 default for OSS-first: Unleash or GrowthBook.

## The 4 step migration to flags

For a team that doesn't have feature flags:

1. **Pick a tool** — PostHog, Unleash, or Flagsmith
2. **Set up the SDK** — install the library, configure the API key
3. **Wrap one feature** — start with the next planned change
4. **Establish the lifecycle** — create, use, roll out, remove, audit

The 4 steps take 1-2 weeks; the benefit is forever.

## The 5 step flag hygiene

For each flag in the codebase:

1. **Owner** — who's responsible
2. **Created date** — when
3. **Default** — on or off
4. **Rollout state** — what percentage, what segment
5. **Removal date** — when to remove

The 5 fields are the 2026 minimum flag metadata. Store in the flag system; review monthly.

## The 5 step anti-flag (static config)

For very simple apps, a static config file replaces a flag system.

```typescript
// config/features.json
{
  "new-checkout": false,
  "payment-v2": "v1",
  "max-upload-mb": 100
}

// In code
import config from './config/features.json';

if (config['new-checkout']) {
  return newCheckout();
}
```

The 5-step anti-flag is appropriate for: <5 features, no percentage rollout, no targeting. Anything more complex: use a flag system.

## The 5 flag system integration with CI

Add flag tests to CI.

```yaml
# .github/workflows/flag-tests.yml
name: Flag tests
on: [pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Test flag defaults
        run: |
          for flag in $(cat config/flags.json | jq -r 'keys[]'); do
            if [ "$(cat config/flags.json | jq -r ".$flag")" == "null" ]; then
              echo "Flag $flag has no default"
              exit 1
            fi
          done
      - name: Test flag code paths
        run: npm test -- --grep "feature-flag"
```

The 5 step CI integration catches missing defaults and broken code paths.

## Verification

The tell that feature flags are real:

- A flag system is in use (PostHog, Unleash, Flagsmith, etc.)
- Flags are created, used, rolled out, removed per the 5-step lifecycle
- Every merge goes to main; flags control exposure
- Code paths are tested with both flag states
- Flag metadata is documented (owner, date, default, removal)

The tell it isn't:

- Long-lived feature branches in production
- "No flag; we just merge and hope"
- Old flags accumulate; the code is unmaintainable
- No default for a flag
- Flag state not in CI

## Gotchas

- **Flags are technical debt.** Every flag adds a branch; retire them.
- **Test both states.** The code must work with flag on and off.
- **Audit the lifecycle.** Monthly review; remove dead flags.
- **Naming matters.** `feature-new-checkout` is clearer than `flag1`.
- **Don't flag migrations.** Use a config or migration script; flags are for runtime.

## Related

- `worktree/branch-strategies-2026.md` — trunk-based development
- `worktree/feature-flags-2026.md` — this entry
- `worktree/release-please-semantic-release.md` — release automation
- `lessons/ai-rollout-strategy-2026.md` — AI rollout patterns

## Source URLs (verified 2026-08-10)

- https://launchdarkly.com/ — LaunchDarkly
- https://docs.getunleash.io/ — Unleash
- https://flagsmith.com/ — Flagsmith
- https://posthog.com/feature-flags — PostHog feature flags
- https://configcat.com/ — ConfigCat
- https://growthbook.io/ — GrowthBook
- https://martinfowler.com/articles/feature-toggles.html — Martin Fowler on feature toggles
- https://www.atlassian.com/continuous-delivery/principles/feature-flags — Atlassian on feature flags
- https://www.getunleash.io/blog/feature-flags-best-practices — Unleash best practices
- https://launchdarkly.com/blog/feature-flags-12-best-practices/ — LaunchDarkly best practices
