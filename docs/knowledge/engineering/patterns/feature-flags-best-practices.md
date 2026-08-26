# feature-flags-best-practices

**Issue:** Feature flags — types, lifecycle, cleanup
**Date:** 2026-08-09
**Status:** documented

## Symptom
You ship a flag. 6 months later, it's still there.
Code is full of `if (flag)`. Nobody knows what to
remove. You wish you had flag discipline.

## Root cause
**Without discipline, flag debt wins.** Type +
lifecycle.

**Source:** LaunchDarkly + Digital Applied 2026.

## The "4 flag types" pattern

For types (Fowler):
1. **Release:** Days to weeks
2. **Experiment:** Hours to weeks
3. **Ops:** Variable, some permanent
4. **Permission:** Long-term

The 4 are the types.

## The "release flag" pattern

For release:
- **Purpose:** Roll out feature
- **Lifespan:** Days to weeks
- **Remove:** At 100%
- **Use:** Incomplete code, progressive

The release is short.

## The "experiment flag" pattern

For experiment:
- **Purpose:** A/B test
- **Lifespan:** Hours to weeks
- **Collapse:** To winner
- **Use:** Testing, metrics

The experiment is statistical.

## The "ops flag" pattern

For ops:
- **Purpose:** Kill switch, circuit breaker
- **Lifespan:** Variable (often permanent)
- **Use:** Load shedding, dependency disable
- **Permanent:** Often yes

The ops is operational.

## The "permission flag" pattern

For permission:
- **Purpose:** Tier-based access
- **Lifespan:** Long-term
- **Use:** Premium features, beta
- **Often:** Permanent

The permission is identity.

## The "lifespan by type" pattern

For decision:
| Type | Lifespan | Tier |
|---|---|---|
| Release | Days-weeks | Server/Edge |
| Experiment | Hours-weeks | Edge |
| Ops | Variable | Server (fastest) |
| Permission | Long-term | Server (auth) |

The lifespan is per type.

## The "naming convention" pattern

For name:
- **Verbose:** `aTeam-chatbox-widget-temp-030619`
- **Format:** team-purpose-temp-date
- **Prefix:** Org or team
- **Suffix:** -temp (for short-term)
- **Why:** Search + clean

The name is descriptive.

## The "polarity" pattern

For On/Off:
- **Off = legacy:** Existing
- **On = new:** Future
- **Standard:** Across team
- **Why:** Consistent

The polarity is per team.

## The "minimize reach" pattern

For scope:
- **Smallest:** Unit of logic
- **Master flag:** If multi-part
- **Dependencies:** Between flags
- **Why:** Debug + clean

The reach is minimal.

## The "planning before code" pattern

For design:
- **Plan first:** Short or permanent?
- **Naming:** Then code
- **Removal:** Plan PR
- **Tracking:** From day 1

The plan is upfront.

## The "kill switch pattern" pattern

For ops:
- **Stabilization window:** 30 days
- **Active:** After deploy
- **Active:** Always (for risky)
- **Rollback:** Seconds

The switch is the safety.

## The "evaluation tier" pattern

For tier:
- **Server:** Most flags
- **Edge:** Fast read (ops, experiment)
- **Client:** Never (leakage)

The tier is per type.

## The "LaunchDarkly lifecycle" pattern

For stages:
- **Live:** Active
- **Ready for Code Removal:** At 100%
- **Ready to Archive:** Code removed
- **Archived:** No references
- **Deprecated:** Marked
- **Deleted:** Gone

The lifecycle is 6 stages.

## The "Unleash lifecycle" pattern

For stages:
- **Define:** Spec
- **Develop:** Build
- **Production:** Live
- **Cleanup:** Remove
- **Archived:** Done

The lifecycle is 5 stages.

## The "OpenFeature" pattern

For vendor-agnostic:
- **CNCF:** Incubating
- **API:** Standard
- **Providers:** Swappable
- **Use:** Avoid lock-in

The OpenFeature is the standard.

## The "Vercel Flags SDK" pattern

For Next.js:
- **Server-side only:** No client leakage
- **Flags as functions:** No call-site args
- **Context:** Via headers() + cookies()
- **No layout shift:** Stable

The Vercel is Next.js native.

## The "polarity convention" pattern

For On/Off:
- **Off:** Legacy
- **On:** New
- **Consistent:** Across all flags
- **Why:** Predictable

The convention is per team.

## The "cleanup discipline" pattern

For cleanup:
- **Treat as inventory:** Carrying cost
- **Active count:** < 50 per team
- **Archive release:** Within 90 days
- **Naming:** Enforce at create
- **Done:** When flag is gone

The discipline is the rule.

## The "archive quarterly" pattern

For cadence:
- **Review:** Every quarter
- **Archive:** 90-120 days
- **Per project:** 1+ archived
- **Per team:** Track

The archive is quarterly.

## The "no removal process" anti-pattern

For no process:
- **Issue:** Flags accumulate
- **Fix:** Removal PR at create

The process is upfront.

## The "long release flag" anti-pattern

For long:
- **Issue:** Tech debt
- **Fix:** Remove at 100%

The release is short.

## The "naming inconsistency" anti-pattern

For inconsistent:
- **Issue:** Can't find
- **Fix:** Convention + enforce

The name is standard.

## The "master flag sprawl" anti-pattern

For master:
- **Issue:** One flag does too much
- **Fix:** Split, master + deps

The flag is minimal.

## The "no tier" anti-pattern

For no tier:
- **Issue:** All evaluated same
- **Fix:** Per type

The tier is set.

## The "client-side flag" anti-pattern

For client:
- **Issue:** Layout shift, leakage
- **Fix:** Server-side

The flag is server.

## The "no review" anti-pattern

For no review:
- **Issue:** Stale flags
- **Fix:** Quarterly review

The review is required.

## The "no telemetry" anti-pattern

For no telemetry:
- **Issue:** Who uses what
- **Fix:** Track per flag

The telemetry is per flag.

## The "flag as permanent" anti-pattern

For permanent:
- **Issue:** Wrong type
- **Fix:** Use ops or permission

The type is correct.

## The "polarity inconsistent" anti-pattern

For mixed:
- **Issue:** Confusing
- **Fix:** Convention

The polarity is fixed.

## The "Vercel + OpenFeature" pattern

For Next.js:
- **Vercel Flags SDK:** Server
- **OpenFeature:** Standard API
- **Edge Config:** Fast reads
- **Provider:** Swappable

The Vercel is the start.

## The "experiment decision" pattern

For choice:
- **Sample size:** Stat sig
- **Duration:** Hours
- **Metric:** Primary
- **Decision:** A or B
- **Collapse:** To winner

The experiment is rigorous.

## The "permission flag" pattern

For permission:
- **Tier-based:** Premium
- **Auth-based:** Role
- **Beta:** Cohort
- **Implementation:** Near auth

The permission is auth-adjacent.

## The "flag checklist" pattern

For checklist:
- [ ] Type decided
- [ ] Naming convention
- [ ] Polarity convention
- [ ] Tier set
- [ ] Removal PR created
- [ ] Telemetry on
- [ ] Review quarterly
- [ ] Archive < 90 days
- [ ] Done = flag gone
- [ ] < 50 per team

The checklist is 10.

## Verification
- **Test:** Polarity consistent
- **Test:** Removal PR exists
- [ ] Active count tracked
- [ ] Review quarterly
- [ ] Audit per team

## Gotchas
- **The "long release" anti-pattern.** Days.
- **The "naming inconsistency" anti-pattern.** Convention.
- **The "no removal" anti-pattern.** Process.

## Related
- `patterns/feature-flags.md`
- `patterns/feature-gating-implementation.md`
- `deploy/canary-deployments.md`
- `deploy/trunk-based-development.md`
- `worktree/conventional-commits.md`
- `patterns/incident-response.md`
- LaunchDarkly: https://launchdarkly.com/blog/best-practices-short-term-permanent-flags/
- Digital Applied: https://www.digitalapplied.com/blog/feature-flag-rollout-strategies-2026-engineering-playbook
- LaunchDarkly release: https://launchdarkly.com/blog/release-management-flags-best-practices/
