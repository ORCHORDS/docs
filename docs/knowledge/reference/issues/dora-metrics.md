# dora-metrics

**Issue:** DORA metrics — DevOps performance
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your team ships monthly. Incidents take hours. The
CTO asks "are we elite?" You don't know. You wish
you had DORA.

## Root cause
**Without metrics, you can't improve.** Use DORA.

**Source:** DORA State of DevOps 2026.

## The "DORA metrics" concept

DORA (DevOps Research and Assessment):
- **4 metrics:** Deployment freq, lead time, MTTR,
  change fail rate
- **4 levels:** Elite, High, Medium, Low
- **Source:** Google research
- **Goal:** Predict org performance

The DORA is the standard.

## The "4 metrics" pattern

For DORA:
1. **Deployment Frequency:** How often
2. **Lead Time for Changes:** Commit to prod
3. **Mean Time to Recovery (MTTR):** Time to fix
4. **Change Failure Rate:** % of deploys cause failure

The 4 are the metrics.

## The "elite performers" pattern

For elite (2026):
- **Deploy freq:** Multiple per day
- **Lead time:** < 1 hour
- **MTTR:** < 1 hour
- **Change fail rate:** 0-15%

The elite is the bar.

## The "performance levels" pattern

For levels:
| Level | Deploy Freq | Lead Time | MTTR | Change Fail |
|---|---|---|---|---|
| Elite | Multiple/day | < 1h | < 1h | 0-15% |
| High | Daily-weekly | 1 day-1 wk | < 1 day | 16-30% |
| Medium | Weekly-monthly | 1 wk-1 mo | < 1 wk | 31-45% |
| Low | Monthly+ | > 1 month | > 1 month | 46-60%+ |

The levels are the bench.

## The "deployment frequency" pattern

For DF:
- **Source:** CI/CD events
- **Measure:** Count per day
- **Track:** Per service
- **Goal:** Increase (smaller batches)

The DF is per deploy.

## The "lead time" pattern

For LT:
- **Source:** First commit → prod
- **Measure:** Median + p95
- **Track:** Per PR
- **Goal:** < 1 day

The LT is the speed.

## The "MTTR" pattern

For MTTR:
- **Source:** Incident open → close
- **Measure:** Median
- **Track:** Per severity
- **Goal:** < 1 hour for SEV1

The MTTR is the recovery.

## The "change fail rate" pattern

For CFR:
- **Source:** Deploys causing rollback
- **Measure:** % per deploy
- **Track:** Per release
- **Goal:** < 15%

The CFR is the quality.

## The "DORA tracking" pattern

For tracking:
- **CI/CD:** Extract deploy events
- **Git:** Extract first commit
- **Incident:** Track MTTR
- **Rollback:** Link to deploy

The tracking is automated.

## The "DORA tools" pattern

For tools:
- **GitLab:** Built-in DORA
- **GitHub Actions:** Custom queries
- **LinearB:** Commercial
- **Sleuth:** Commercial
- **Jellyfish:** Commercial
- **DIY:** BigQuery + dbt + Looker

The tool is per choice.

## The "DORA + SPACE" pattern

For combined:
- **DORA:** System performance
- **SPACE:** Dev experience
  - Satisfaction
  - Performance
  - Activity
  - Communication
  - Efficiency
- **Together:** Both views

The combo is richer.

## The "DORA anti-pattern" anti-patterns

### 1. Wrong metric
- **Issue:** "Deploy freq" without "change fail rate"
- **Fix:** Track all 4

### 2. No baseline
- **Issue:** Don't know if improving
- **Fix:** Quarterly snapshot

### 3. Blame game
- **Issue:** "MTTR is your fault"
- **Fix:** System, not people

### 4. Optimization wrong
- **Issue:** Increase deploy freq → more failures
- **Fix:** CFR is the counterweight

### 5. Vanity
- **Issue:** "We deploy 1000x/day"
- **Reality:** Most are config, not features

The DORA is honest.

## The "deploy freq without CFR" anti-pattern

For no CFR:
- **Issue:** Deploy often = break often
- **Fix:** Track CFR together

The CFR is the counter.

## The "DORA improvement" pattern

For improving:
- **Trunk-based dev:** Increase DF
- **Smaller PRs:** Decrease LT
- **Feature flags:** Decrease risk
- **Canary:** Decrease CFR
- **Runbooks:** Decrease MTTR

The improvement is process.

## The "trunk-based" pattern

For TBD:
- **Branches:** < 24h lifetime
- **Merges:** Daily
- **Result:** Higher DF, lower CFR

The TBD is the path.

## The "feature flag" pattern

For FF:
- **Decouple:** Deploy from release
- **Result:** Lower CFR, higher DF
- **Cost:** Flag debt

The FF is the lever.

## The "canary" pattern

For canary:
- **5-10%:** Initial
- **50%:** If green
- **100%:** If still green
- **Result:** Lower CFR, faster detection

The canary is the gate.

## The "incident" pattern

For MTTR:
- **Detect:** < 5 min (alerting)
- **Triage:** < 10 min
- **Mitigate:** < 1 hour
- **Resolve:** < 24 hours

The MTTR is per phase.

## The "error budget" pattern

For budget:
- **SLO:** 99.9% = 0.1% budget
- **Use:** 30 days of failures
- **Result:** Balance reliability + velocity

The budget is the lever.

## The "DORA weekly review" pattern

For review:
- **DF:** Per service
- **LT:** P50, P95
- **MTTR:** Per severity
- **CFR:** Trend
- **Action:** If regression

The review is weekly.

## The "DORA quarterly" pattern

For quarterly:
- **Trend:** All 4
- **Per team:** Comparison
- **Improvement:** Action items
- **Report:** To leadership

The review is quarterly.

## The "DORA + SLO" pattern

For combined:
- **DORA:** Velocity + recovery
- **SLO:** Reliability
- **Together:** Balance
- **Decision:** Feature freeze if budget

The SLO is the bound.

## The "DORA + business" pattern

For business:
- **DF:** "Time to market"
- **LT:** "Idea to customer"
- **MTTR:** "Customer trust"
- **CFR:** "Engineering quality"

The business maps.

## The "no DORA" anti-pattern

For no DORA:
- **Issue:** No signal
- **Fix:** Track all 4

The DORA is required.

## The "wrong DORA" anti-pattern

For wrong:
- **Issue:** Optimizing for wrong metric
- **Fix:** All 4, balanced

The DORA is balanced.

## The "no CFR" anti-pattern

For no CFR:
- **Issue:** Speed without quality
- **Fix:** CFR is mandatory

The CFR is required.

## The "blame" anti-pattern

For blame:
- **Issue:** "MTTR is your fault"
- **Fix:** System, not people

The blame is gone.

## The "DORA checklist" pattern

For checklist:
- [ ] All 4 metrics tracked
- [ ] Per service
- [ ] Per team
- [ ] Weekly review
- [ ] Quarterly trend
- [ ] Action items
- [ ] Reported to leadership
- [ ] Combined with SLO
- [ ] No blame

The checklist is 9.

## Verification
- **Test:** Metrics auto-collected
- **Test:** Quarterly review happens
- **Test:** Trends are improving
- **Test:** Action items tracked
- **Audit:** Annual

## Gotchas
- **The "no CFR" anti-pattern.** Track all 4.
- **The "blame" anti-pattern.** System, not people.
- **The "wrong DORA" anti-pattern.** Balance.

## Related
- `lessons/scope-discipline.md`
- `lessons/lazy-fail-discoveries.md`
- `deploy/cab-change-management.md`
- `patterns/slo-error-budget-deep-dive.md`
- `patterns/chaos-engineering-deep-dive.md`
- DORA: https://dora.dev/
- Google Cloud: https://cloud.google.com/devops
