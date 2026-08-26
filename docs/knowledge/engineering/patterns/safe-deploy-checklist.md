# safe-deploy-checklist

**Issue:** Pre-deploy checklist for production changes
**Date:** 2026-08-09
**Status:** documented (checklist)

## Symptom
You push to main. The deploy goes out. A user reports a bug.
You look at the diff. "Oh, I forgot to test X." You wish you'd
had a checklist.

## Root cause
**Deploys have many moving parts.** A single missing step can
cause downtime. A checklist ensures nothing is forgotten.

**Source:** Various SRE / deployment guides:
https://sre.google/sre-book/release-engineering/

## The pre-deploy checklist

### Code
- [ ] **Code is reviewed** by at least 1 other person
- [ ] **Tests are added** for new behavior
- [ ] **Lint passes** (`npm run lint`)
- [ ] **Typecheck passes** (`npx tsc -b --noEmit`)
- [ ] **Tests pass** (`npx vitest run`)
- [ ] **Build succeeds** (`npm run build`)
- [ ] **No new dependencies** (or new deps are reviewed for
  security + size)

### Schema
- [ ] **Migrations are tested** locally
- [ ] **Migrations are backward-compatible** (additive, not
  destructive)
- [ ] **Migrations run in order** (no renumbering)
- [ ] **Schema docs are updated** (if applicable)

### Configuration
- [ ] **Env vars are set** in the target environment
- [ ] **Secrets are rotated** (if rotating)
- [ ] **Feature flags are set** (if using)
- [ ] **CDN / WAF rules are updated** (if applicable)
- [ ] **DNS records are set** (if adding a new domain)

### Testing
- [ ] **Deployed to staging** + smoke tested
- [ ] **E2E tests pass** on the staging URL
- [ ] **Load test passes** (if high-stakes)
- [ ] **Pen test passes** (if security-stakes)
- [ ] **Manual QA** (if UX-stakes)

### Observability
- [ ] **Dashboards are updated** (if adding a new service)
- [ ] **Alerts are set** (if adding a new failure mode)
- [ ] **Log destinations are set** (if adding a new service)
- [ ] **Tracing is set** (if adding a new service)

### Communication
- [ ] **Team is notified** in #deploys Slack channel
- [ ] **Status page is updated** (if user-facing)
- [ ] **Customer support is briefed** (if user-facing)
- [ ] **Stakeholders are notified** (if high-stakes)

### Rollback
- [ ] **Rollback procedure is documented**
- [ ] **Rollback tested** in staging (or last deploy)
- [ ] **Rollback can be done in < 5 min**
- [ ] **Rollback doesn't break data** (schema migrations
  forward-only)

## The "deploy day" routine

1. **Morning of deploy:** review the checklist with the team
2. **Pre-deploy:** verify env vars, run smoke tests
3. **Deploy:** push the button; monitor in real time
4. **Post-deploy (5 min):** verify health endpoints
5. **Post-deploy (30 min):** monitor metrics for anomalies
6. **Post-deploy (24h):** retrospective; rollback if any issues

## The "rollback decision" framework

Rollback if:
- **Error rate > 2x the baseline** for > 5 min
- **Latency p99 > 2x the baseline** for > 5 min
- **Critical functionality is broken** (login, payment, etc.)
- **Data corruption** is detected
- **Security vulnerability** is discovered

Don't rollback if:
- **Cosmetic issue** (a typo, a misplaced button)
- **Minor performance regression** (< 10%)
- **Non-critical functionality** is broken (and can be fixed
  forward)

For ambiguous cases, default to rollback. It's cheaper to
revert and try again than to fix forward with users affected.

## The "post-mortem" routine

After a rollback or significant incident:
1. **Within 24h:** write a post-mortem document
2. **Within 1 week:** present to the team
3. **Within 2 weeks:** add the fix to the backlog
4. **No blame:** focus on the system, not the person
5. **5 whys:** find the root cause, not just the symptom

## Verification
- **Audit:** Quarterly review of deploy frequency + rollback
  rate
- **Process:** The checklist is updated as new failure modes
  are discovered

## Gotchas
- **The checklist is not a substitute for thinking.** A
  mechanical "check all boxes" deploy still needs human
  judgment.
- **Checklist fatigue** is real. A 50-item checklist is too
  long; a 5-item checklist is too short. Find the right
  balance.
- **The checklist is a living document.** Update it when
  you find a new failure mode.
- **The rollback procedure must be tested.** A rollback
  procedure that has never been tested is a rollback
  procedure that won't work.
- **Some deploys are routine** (no need for the full
  checklist). Some are high-stakes (need the full checklist
  + extra review). Adjust per deploy.

## Related
- `zero-downtime-deploys.md`
- `feature-rollout-strategies.md`
- `preview-environments.md`
- `pr-template-and-issue-templates.md`
- SRE book: https://sre.google/sre-book/release-engineering/
- Etsy Debriefing Facilitation Guide: https://extfiles.etsy.com/DebriefingFacilitationGuide.pdf
