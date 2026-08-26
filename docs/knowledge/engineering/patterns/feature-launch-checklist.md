# feature-launch-checklist

**Issue:** Pre-launch checklist for a new feature
**Date:** 2026-08-09
**Status:** documented (checklist)

## Symptom
You ship a new feature. A user reports a bug. You look at
the launch. "Did we test X?" "No." "Did we document Y?"
"No." "Did we have a rollback plan?" "No." You scramble
to fix things in production.

## Root cause
**Launches have many moving parts.** A single missing
step can cause problems.

**Source:** Various product launch guides.

## The "pre-launch" checklist

### Code
- [ ] **Code is reviewed** by at least 1 other person
- [ ] **Tests are added** (unit + integration + E2E)
- [ ] **Lint passes**
- [ ] **Typecheck passes**
- [ ] **All tests pass**
- [ ] **No new dependencies** (or new deps are reviewed)

### Feature flags
- [ ] **Kill switch** is in place
- [ ] **Default state** is "off" or "limited"
- [ ] **Rollout plan** is documented
- [ ] **Owner** is assigned

### Documentation
- [ ] **User docs** are written
- [ ] **Internal docs** (runbook) are written
- [ ] **API docs** (OpenAPI) are updated
- [ ] **Release notes** are drafted

### UX
- [ ] **Accessibility** is checked (WCAG AA)
- [ ] **i18n** is verified for all 20 locales
- [ ] **Mobile** is tested (iOS + Android)
- [ ] **Cross-browser** is tested (Chrome, Firefox, Safari)

### Performance
- [ ] **Latency** is measured (p50, p95, p99)
- [ ] **Load test** is passed
- [ ] **No N+1 queries** in the hot path
- [ ] **Cache is in place** for expensive operations

### Security
- [ ] **Auth** is enforced
- [ ] **Authz** is checked for the resource
- [ ] **Input validation** is in place (Zod or similar)
- [ ] **Rate limiting** is applied
- [ ] **No secrets in code** (gitleaks)
- [ ] **CSP / security headers** are present
- [ ] **PII is handled correctly**

### Observability
- [ ] **Metrics** are emitted
- [ ] **Logs** are structured
- [ ] **Traces** are sampled
- [ ] **Dashboard** is updated
- [ ] **Alerts** are set

### Compliance
- [ ] **GDPR** is checked (PII handling, erasure)
- [ ] **CCPA** is checked (opt-out, data access)
- [ ] **Industry-specific** (HIPAA, PCI, etc.)
- [ ] **Audit log** captures the action

### Operations
- [ ] **Staging** deployment is verified
- [ ] **Smoke test** is run
- [ ] **Rollback procedure** is documented + tested
- [ ] **On-call** is aware
- [ ] **Status page** is updated (if user-facing)

### Communication
- [ ] **Team** is notified (in Slack)
- [ ] **Stakeholders** are notified (PM, support, etc.)
- [ ] **Marketing** is aligned (if user-facing)
- [ ] **Customer support** is briefed
- [ ] **Customers** are informed (if major)

### Post-launch
- [ ] **Monitor** for 24h
- [ ] **Review** metrics at 1h, 24h, 7d
- [ ] **Decide** on rollout (% to next)
- [ ] **Document** the launch (post-mortem if issues)

## The "rollout plan" template

```markdown
## Feature: [Name]
**Owner:** @user
**Target date:** YYYY-MM-DD

## Rollout plan
- **Day 0:** 1% in production (beta cohort)
- **Day 1:** 5% if no issues
- **Day 3:** 25% if no issues
- **Day 7:** 50% if no issues
- **Day 14:** 100% if no issues
- **Day 90:** Remove the feature flag

## Kill criteria
- Error rate > 5% for 10 min
- p99 latency > 2s for 10 min
- Conversion drops > 30%
- 3+ P0 bugs in 1 week

## Success criteria
- Primary metric improves by X%
- No guardrail regressions
- < 1% rollback rate
```

## The "smoke test" template

After deploy, run:
- [ ] **Login** works
- [ ] **Signup** works
- [ ] **The new feature** is reachable
- [ ] **Critical user paths** are unbroken
- [ ] **External services** are reachable (Stripe, etc.)
- [ ] **Logs are flowing** (no errors in the dashboard)
- [ ] **Metrics are flowing** (data in the dashboard)

A 5-minute smoke test catches 80% of deploy issues.

## The "rollback decision" tree

Should I roll back?
- **The feature is broken:** Roll back
- **The error rate spiked:** Roll back
- **The latency spiked:** Roll back
- **A guardrail metric regressed:** Roll back
- **The primary metric dropped (but no errors):** Investigate
  first
- **A user reports a bug (one user):** Investigate first

The default is to roll back. A bad deploy is the most
common cause of incidents.

## The "post-launch review" template

```markdown
## Feature: [Name]
**Launched:** YYYY-MM-DD
**Owner:** @user

### What went well
- [List the things that went well]

### What didn't go well
- [List the things that didn't go well]

### Metrics (7d post-launch)
- **Primary metric:** [X% change]
- **Secondary metrics:** [List]
- **Error rate:** [X%]
- **Latency p99:** [Xms]
- **Adoption:** [X%]

### User feedback
- [Quotes from users]

### Action items
- [ ] [Item 1]
- [ ] [Item 2]
```

## The "feature retrospective" pattern

A week after launch, the team meets:
1. **What went well?** (Celebrate the wins)
2. **What didn't go well?** (Learn from the issues)
3. **What will we do differently next time?** (Improve the
   process)

The retro is blameless; the goal is to improve, not to
blame.

## The "dead feature" cleanup

For features that don't get adopted:
- **Month 1:** No adoption; investigate
- **Month 3:** Still no adoption; consider sunsetting
- **Month 6:** Definitely sunset

A feature that nobody uses is a maintenance burden. Remove
it.

## Verification
- **Process:** The checklist is followed for every launch
- **Live:** Launches are tracked in the dashboard
- **Audit:** Quarterly review of launches

## Gotchas
- **The "checklist theater" anti-pattern.** Checking boxes
  without doing the work. The checklist is a reminder, not
  a substitute for thinking.
- **The "skip the checklist for a small change" anti-
  pattern.** Small changes can have big impacts. Use the
  checklist.
- **The "rollout plan is a wish" anti-pattern.** The plan
  must be realistic; the kill criteria must be clear.
- **The "no post-launch review" anti-pattern.** Every
  launch is an opportunity to learn.
- **The "feature lives forever" anti-pattern.** Every
  feature has a lifecycle; sunset when appropriate.

## Related
- `safe-deploy-checklist.md`
- `feature-flags.md`
- `feature-flags-best-practices.md`
- `feature-flags-implementations.md`
- `feature-observability-pattern.md`
- `incident-response.md`
