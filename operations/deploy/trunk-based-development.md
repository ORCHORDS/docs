# trunk-based-development

**Issue:** Trunk-based development + feature flags
**Date:** 2026-08-09
**Status:** documented

## Symptom
Feature branches live 2 weeks. Merge conflicts daily.
Releases are Friday 5pm. The DORA score is "low".
You wish you had trunk-based dev.

## Root cause
**Long branches = merge hell.** Use TBD + flags.

**Source:** Unleash + Harness 2026.

## The "trunk-based development" concept

TBD:
- **Source of truth:** Main (trunk)
- **Branches:** Short (hours, not weeks)
- **Commits:** Daily
- **Incomplete:** Behind feature flags
- **Main:** Always deployable
- **DORA:** Gold standard

The TBD is the elite model.

## The "branch lifetime" pattern

For lifetime:
- **Hours to 1-2 days:** Max
- **Never weeks**
- **Daily:** Merge cadence
- **Predictor:** Lifetime = merge conflict rate

The lifetime is short.

## The "team size" pattern

For TBD:
- **2-50 developers:** Ideal
- **< 3:** Overkill
- **50+:** Hard (need maturity)
- **Requirement:** Strong CI + flags

The team is mid-size.

## The "feature flag" concept

Feature flag:
- **Decouples:** Deploy from release
- **Hides:** Incomplete code
- **Enables:** Progressive rollout
- **Allows:** Instant rollback

The flag is the lever.

## The "release flag" pattern

For release:
- **Starts:** Off in prod
- **On:** In dev/staging
- **Progressive:** 1% → 10% → 50% → 100%
- **Lifecycle:** Short (remove after roll-out)
- **Tech debt:** Watch for stale

The flag is short-lived.

## The "flag types" pattern

For types:
- **Release:** Tied to deploy
- **Experiment:** A/B test
- **Ops:** Toggle (kill switch)
- **Permission:** Per user/role

The type is per use.

## The "naming convention" pattern

For names:
- **Prefix:** `ff_`, `feat_`
- **Feature:** What
- **Segment:** Who
- **Example:** `ff_new_checkout`, `feat_mobile_premium`

The name is structured.

## The "TBD + FF workflow" pattern

For workflow:
1. Open feature branch
2. Code behind flag (off in prod)
3. PR + review
4. Merge to main
5. CI tests
6. Deploy (flag still off)
7. Enable in staging
8. Test
9. Progressive rollout
10. 100% on
11. Remove flag
12. Code stays

The flow is 12 steps.

## The "main deployable" pattern

For main:
- **Always:** Builds
- **Always:** Tests pass
- **Always:** Deployable
- **Why:** DORA = elite

The main is sacred.

## The "short branch commands" pattern

For commands:
```bash
# Morning sync
git checkout main
git pull --rebase origin main

# Short branch
git switch -c fix/rate-limiter

# Small changes
git commit -m "fix: rate limiter timeout"

# Rebase
git fetch origin
git rebase origin/main

# Push + PR
git push origin fix/rate-limiter

# Merge immediately
git checkout main
git merge --no-ff fix/rate-limiter
git push origin main

# Delete
git branch -d fix/rate-limiter
git push origin --delete fix/rate-limiter
```

The commands are daily.

## The "feature flag rollback" pattern

For rollback:
1. Open flag UI
2. Find flag
3. Toggle off
4. **Instantly:** Feature disabled
5. No deploy
6. No downtime

The rollback is instant.

## The "incomplete code in main" pattern

For incomplete:
- **Allowed:** Yes, behind flag
- **Hidden:** In production
- **Tested:** With flag on
- **Merged:** Daily

The code is hidden.

## The "branch protection + TBD" pattern

For protection:
- **Required:** CI status
- **Required:** 1+ review
- **No force push**
- **Branch delete:** Auto after merge

The protection is required.

## The "merge frequency" pattern

For merges:
- **Per day:** Min 1
- **Per dev:** 1-3
- **Batch:** Never
- **Conflict:** Reduced by short branches

The merge is daily.

## The "long branch anti-pattern" anti-pattern

For long:
- **Issue:** Conflicts, drift
- **Fix:** Short branches (hours)

The branch is short.

## The "no flag" anti-pattern

For no flag:
- **Issue:** Incomplete code in prod
- **Fix:** Feature flag

The flag is required.

## The "no short branches" anti-pattern

For week+:
- **Issue:** Merge hell
- **Fix:** Daily merge

The merge is daily.

## The "stale flag" anti-pattern

For stale:
- **Issue:** Tech debt
- **Fix:** Auto-archive after 30-60d

The flag is archived.

## The "no FF naming" anti-pattern

For random:
- **Issue:** Can't find
- **Fix:** Convention (ff_, feat_)

The name is standard.

## The "TBD + GitFlow" pattern

For choice:
- **GitFlow:** Long branches, versioned
- **TBD:** Short, daily, flag
- **Pick:** TBD for SaaS, GitFlow for versioned product

The choice is per release model.

## The "DORA impact" pattern

For metrics:
- **DF:** Multiple/day (vs weekly)
- **LT:** < 1 day (vs weeks)
- **MTTR:** < 1 hour
- **CFR:** < 15% (with flags)

The TBD = elite.

## The "GitFlow vs TBD" pattern

For comparison:
| Dim | TBD | GitFlow |
|---|---|---|
| Branch life | Hours | Weeks |
| Merge freq | Daily | At release |
| Main | Always green | Protected |
| Flags | Required | Optional |
| Best for | SaaS | Versioned |

The TBD is for continuous.

## The "TBD + monorepo" pattern

For monorepo:
- **Trunk:** Single main
- **Short branches:** Per package
- **Affected:** Build only changed
- **Flags:** Per feature

The TBD works in monorepo.

## The "no test" anti-pattern

For no test:
- **Issue:** Frequent merges break main
- **Fix:** Strong CI + tests

The test is required.

## The "TBD checklist" pattern

For checklist:
- [ ] Short branches (< 2 days)
- [ ] Daily merges
- [ ] Main always deployable
- [ ] Feature flags for incomplete
- [ ] Branch protection enabled
- [ ] CI runs per PR
- [ ] Auto-archive stale flags
- [ ] DORA tracked
- [ ] Team trained

The checklist is 9.

## Verification
- **Test:** Branches < 2 days
- **Test:** Main always green
- **Test:** Flag rollback works
- **Test:** DORA elite
- **Audit:** Quarterly

## Gotchas
- **The "long branch" anti-pattern.** Short.
- **The "no flag" anti-pattern.** Required.
- **The "stale flag" anti-pattern.** Archive.

## Related
- `worktree/conventional-commits.md`
- `worktree/rebase-vs-merge-detail.md`
- `patterns/feature-flags.md`
- `patterns/feature-flags-best-practices.md`
- `deploy/canary-deployments.md`
- `issues/dora-metrics.md`
- Unleash: https://docs.getunleash.io/guides/trunk-based-development
- Harness: https://developer.harness.io/docs/feature-flags/get-started/trunk-based-development
- SesameDisk: https://sesamedisk.com/git-workflows-2026-update/
