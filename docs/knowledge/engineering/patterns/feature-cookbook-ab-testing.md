# feature-cookbook-ab-testing

**Issue:** A/B testing — variants, metrics, significance
**Date:** 2026-08-09
**Status:** documented

## Symptom
You change a button color. You have no idea if it
improves conversions. You guess. You ship. The
conversion drops. You wish you'd tested.

## Root cause
**Without A/B testing, you guess.** Run experiments.

**Source:** Optimizely docs.

## The "A/B test" pattern

For A/B testing:
1. **Hypothesis:** "Red button converts 10% better"
2. **Variants:** A (control), B (red)
3. **Split:** 50/50 random
4. **Measure:** Conversion rate
5. **Significance:** p < 0.05

```ts
function getVariant(user: User): 'A' | 'B' {
  // Hash the user to a stable variant
  const hash = sha256(user.id);
  return parseInt(hash.slice(0, 8), 16) % 2 === 0 ? 'A' : 'B';
}
```

The user is split.

## The "feature flag" pattern

For feature flags as A/B tests:
```ts
const variant = await getVariant(user, env);
if (variant === 'A') {
  return renderButton({ color: 'blue' });
} else {
  return renderButton({ color: 'red' });
}
```

The variant is rendered.

## The "metric tracking" pattern

For metric tracking:
```ts
async function trackConversion(userId: string, variant: 'A' | 'B', env: Env): Promise<void> {
  await env.ANALYTICS.writeDataPoint({
    blobs: ['ab_test', 'conversion', userId, variant],
    doubles: [1],
    indexes: ['ab_test'],
  });
}
```

The conversion is tracked.

## The "statistical significance" pattern

For significance, use a t-test or chi-square:
```ts
function isSignificant(
  conversionsA: number,
  visitorsA: number,
  conversionsB: number,
  visitorsB: number,
): { significant: boolean; pValue: number } {
  const rateA = conversionsA / visitorsA;
  const rateB = conversionsB / visitorsB;
  const p = (conversionsA + conversionsB) / (visitorsA + visitorsB);
  const se = Math.sqrt(p * (1 - p) * (1 / visitorsA + 1 / visitorsB));
  const z = (rateB - rateA) / se;
  // Approximate p-value
  const pValue = 2 * (1 - normalCdf(Math.abs(z)));
  return { significant: pValue < 0.05, pValue };
}
```

The significance is computed.

## The "sample size" pattern

For sample size, before the test:
```ts
function requiredSampleSize(baseline: number, mde: number, alpha = 0.05, power = 0.8): number {
  // mde = minimum detectable effect
  // Simplified
  const zAlpha = 1.96;
  const zBeta = 0.84;
  return Math.ceil(2 * Math.pow((zAlpha + zBeta) / mde, 2) * baseline * (1 - baseline));
}

// 5% baseline, 10% MDE, 5% significance, 80% power
requiredSampleSize(0.05, 0.10);  // ~30k per variant
```

The sample size is calculated.

## The "test duration" pattern

For duration:
- **Min:** 1-2 weeks (capture weekly cycle)
- **Max:** 4 weeks (avoid novelty effect)
- **Stop early:** Only if p < 0.001 (Bonferroni)

```ts
const MIN_DURATION_DAYS = 7;
const MAX_DURATION_DAYS = 28;
```

The duration is bounded.

## The "multi-variant" pattern

For multi-variant (A/B/C/D):
```ts
function getVariant(user: User, variants: string[]): string {
  const hash = sha256(user.id);
  const index = parseInt(hash.slice(0, 8), 16) % variants.length;
  return variants[index];
}

const variant = getVariant(user, ['A', 'B', 'C']);
```

The multi-variant is supported.

## The "segment analysis" pattern

For segments:
```ts
async function trackBySegment(
  userId: string,
  variant: 'A' | 'B',
  segment: string,
  env: Env,
): Promise<void> {
  await env.ANALYTICS.writeDataPoint({
    blobs: ['ab_test', 'conversion', userId, variant, segment],
    doubles: [1],
    indexes: ['ab_test'],
  });
}
```

The segment is tracked.

## The "guardrail metric" pattern

For guardrails, track things that shouldn't get worse:
- **Latency:** p99 < 200ms
- **Error rate:** < 0.1%
- **Retention:** Day-7 > X%

```ts
const guardrails = {
  latencyP99: 200,
  errorRate: 0.001,
  retentionD7: 0.4,
};
```

The guardrails are tracked.

## The "stop the test" pattern

For stopping, predefined rules:
- **Significance:** p < 0.05 + min sample
- **Guardrail violated:** Stop
- **Max duration:** 4 weeks

```ts
function shouldStopTest(
  daysRunning: number,
  visitorsA: number,
  visitorsB: number,
  conversionsA: number,
  conversionsB: number,
  guardrails: { latencyP99: number; errorRate: number },
): { stop: boolean; reason: string } {
  if (daysRunning > MAX_DURATION_DAYS) return { stop: true, reason: 'max_duration' };
  if (guardrails.errorRate > 0.005) return { stop: true, reason: 'guardrail_violated' };

  const { significant } = isSignificant(conversionsA, visitorsA, conversionsB, visitorsB);
  if (significant && visitorsA > 1000 && visitorsB > 1000) {
    return { stop: true, reason: 'significant' };
  }

  return { stop: false, reason: 'continue' };
}
```

The test is stopped based on rules.

## The "A/B test observability" pattern

For observability:
- **Split ratio:** Should be 50/50
- **Sample size:** Total visitors
- **Conversion rate:** Per variant
- **Significance:** p-value

```ts
metrics.gauge('ab_test.visitors_total', visitors, { variant });
metrics.gauge('ab_test.conversion_rate', rate, { variant });
```

The A/B test is monitored.

## The "A/B test anti-pattern" anti-patterns

### 1. No hypothesis
- **Issue:** Testing random things
- **Fix:** Hypothesis first

### 2. Peeking at results
- **Issue:** False positive
- **Fix:** Pre-register the analysis

### 3. Too short
- **Issue:** Weekly cycle not captured
- **Fix:** Min 1-2 weeks

### 4. Too long
- **Issue:** Novelty effect
- **Fix:** Max 4 weeks

### 5. No guardrails
- **Issue:** Negative side effects
- **Fix:** Track guardrails

### 6. Stop on first significance
- **Issue:** False positive
- **Fix:** Bonferroni + min sample

## Verification
- **Test:** Split is correct
- **Test:** Metrics are tracked
- **Test:** Significance is correct
- **Live:** A/B test is monitored
- **Audit:** Quarterly review

## Gotchas
- **The "no hypothesis" anti-pattern.** Hypothesis
  first.
- **The "peeking" anti-pattern.** Pre-register.
- **The "too short" anti-pattern.** Min 1-2 weeks.

## Related
- `feature-cookbook-feature-flags.md`
- `feature-cookbook-experimentation.md`
- `feature-experimentation.md`
- `feature-flags.md`
- Optimizely: https://www.optimizely.com/
- Statsig: https://statsig.com/
- LaunchDarkly: https://launchdarkly.com/
