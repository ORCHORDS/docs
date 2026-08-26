# feature-experimentation

**Issue:** A/B testing — design, statistics, decision
**Date:** 2026-08-09
**Status:** documented

## Symptom
You ship a new button color. The conversion goes up 5%. You
declare victory. Two weeks later, the conversion is the same
as before. The "win" was random noise. You shipped a change
that didn't actually help.

## Root cause
**Random noise is huge.** With 1000 users, a 5% difference
could be random. You need statistical significance to know
if the change is real.

**Source:** Optimizely — A/B testing statistics:
https://www.optimizely.com/insights/blog/

> "A/B testing is a randomized experiment ... that compares
> two versions of a variable to determine which performs
> better."

## The "hypothesis" pattern

Every A/B test starts with a hypothesis:
```markdown
## Hypothesis

**If** we change the button color from blue to green,
**then** the click-through rate will increase by 10%,
**because** green is more attention-grabbing.

**Success criteria:** CTR increases by 10% with 95%
confidence.
```

A test without a hypothesis is a test without a goal.

## The "primary metric" choice

For each test, one primary metric:
- **Conversion:** % of users who do the target action
- **Revenue:** $ per user
- **Engagement:** time on page, actions per session
- **Retention:** % of users who come back

Pick one. The test's success depends on it.

## The "secondary metrics" choice

Secondary metrics are diagnostic:
- **Click-through rate:** Did the button get more clicks?
- **Time on page:** Did users engage more?
- **Bounce rate:** Did fewer users leave?

Secondary metrics explain WHY the primary metric changed.

## The "guardrail metrics" choice

Guardrail metrics are "must not regress":
- **Error rate:** The new version must not break things
- **Latency:** The new version must not be slower
- **Revenue per user:** The new version must not lose money

If a guardrail regresses, the test is a fail even if the
primary metric improves.

## The "sample size" pattern

For 95% confidence + 80% power:
- **Baseline conversion:** 5%
- **Minimum detectable effect:** 10% relative (5% → 5.5%)
- **Sample size needed:** ~150,000 per variant

Use a calculator:
- Optimizely: https://www.optimizely.com/sample-size-calculator/
- Evan Miller: https://www.evanmiller.org/ab-testing/sample-size.html

Don't run a test that won't reach significance.

## The "duration" pattern

For a test that needs 300,000 users at 1000/day, run for
300 days. That's a long time.

**Solutions:**
- **Run during high-traffic periods** (e.g. weekdays)
- **Increase traffic** (focus the rollout)
- **Lower the effect size** (if you can detect 20%, you
  need fewer users)
- **Use a sequential test** (analyze as you go)

## The "sequential testing" pattern

For faster decisions, sequential testing:
```ts
// After each user, compute the probability that B > A
function sequentialTest(aConversions: number, aTotal: number, bConversions: number, bTotal: number): number {
  // mSPRT or other sequential test
  // Returns p-value at each step
}

// Run the test
while (true) {
  const pValue = sequentialTest(aConv, aTotal, bConv, bTotal);
  if (pValue < 0.05) break;  // Significant
  if (totalUsers > MAX) break;  // Stop for futility
  await sleep(60_000);  // Wait 1 min
}
```

Sequential tests can stop earlier than fixed-horizon tests.

## The "A/B/n test" pattern

For multiple variants (more than 2):
```ts
const variants = ['control', 'red', 'green', 'blue'];
const assignments: Record<string, number> = {};

// Randomly assign
for (const userId of users) {
  const hash = sha256(userId);
  const bucket = parseInt(hash.slice(0, 8), 16) % variants.length;
  assignments[userId] = bucket;
}
```

With 4 variants, you need 4x the sample size of an A/B
test.

## The "A/B test mistakes"

### 1. Peeking
- **Symptom:** You check the results daily and "declare
  victory" when p < 0.05
- **Why it's wrong:** Peeking inflates the false positive
  rate
- **Fix:** Pre-register the duration; don't peek

### 2. Stopping early
- **Symptom:** You stop the test when one variant is ahead
- **Why it's wrong:** Could be a random spike
- **Fix:** Run for the pre-registered duration

### 3. Multiple comparisons
- **Symptom:** You have 20 metrics; one is p < 0.05 by
  chance
- **Why it's wrong:** Multiple comparisons inflate the
  false positive rate
- **Fix:** Bonferroni correction; or pre-register 1-2
  metrics

### 4. Segmenting after the fact
- **Symptom:** "The test didn't work for everyone, but
  it worked for users in country X"
- **Why it's wrong:** Subgroup analysis inflates the
  false positive rate
- **Fix:** Pre-register segments; or accept the
  hypothesis isn't supported

## The "test duration" decision

For a test that needs N users, the duration is:
- **N / daily_users** days

Example: 100k users needed, 10k daily users = 10 days.

But:
- **Don't run over weekends** (different traffic patterns)
- **Don't run over holidays** (different traffic patterns)
- **Don't run too short** (random noise dominates)
- **Don't run too long** (novelty effect; user behavior
  changes)

A 2-4 week test is typical.

## The "feature flag + A/B test" pattern

Combine feature flags with A/B tests:
```ts
// 1. Enable the feature for 50%
if (await isFeatureEnabled('new-checkout', ctx)) {
  // ... new flow
} else {
  // ... old flow
}

// 2. Track the metric per variant
metrics.increment('checkout.completed_total', { variant: 'new' });
```

The feature flag is the rollout; the A/B test is the
measurement.

## The "decision framework"

After the test, decide:
- **Primary metric improved + significant + no guardrail
  regression:** Ship the new variant
- **Primary metric unchanged:** Stick with the control
  (the new variant is not worth the complexity)
- **Primary metric regressed:** Roll back

The decision is binary: ship or don't. The data tells you
which.

## The "novelty effect"

When a new feature launches, users engage more (out of
curiosity). Over time, engagement drops. The test may show
a "win" that disappears after launch.

**Fix:**
- **Run the test for at least 2 weeks**
- **Check the trend over time** (is the difference
  shrinking?)

## The "documentation" pattern

For every test, document:
- **Hypothesis**
- **Primary + secondary + guardrail metrics**
- **Sample size + duration**
- **Results** (with p-values)
- **Decision + reason**

The doc is the audit trail. Future tests build on past
tests.

## Verification
- **Test:** A/B test framework has unit tests
- **Live:** A/B tests are running; results are recorded
- **Audit:** Annual review of test results

## Gotchas
- **The "test forever" anti-pattern.** A test that runs
  forever is not a test. Pre-register the duration.
- **The "test too small" anti-pattern.** A test with 100
  users can't detect a 5% effect. Wait for the sample
  size.
- **The "test without hypothesis" anti-pattern.** A test
  without a hypothesis is just exploration. Use one.
- **The "ship on a single test" anti-pattern.** A single
  test can be wrong. Re-test for important decisions.
- **The "ignore the guardrail" anti-pattern.** A
  conversion win with a 50% error rate increase is a loss.

## Related
- `feature-flags.md`
- `feature-observability-pattern.md`
- `safe-deploy-checklist.md`
- `feature-flags-implementations.md`
- Optimizely: https://www.optimizely.com/
- Evan Miller: https://www.evanmiller.org/
- A/B testing: https://en.wikipedia.org/wiki/A/B_testing
