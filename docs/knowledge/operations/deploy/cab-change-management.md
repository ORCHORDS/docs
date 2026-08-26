# cab-change-management

**Issue:** Change Advisory Board — ITIL 4 in 2026
**Date:** 2026-08-09
**Status:** documented

## Symptom
Anyone can deploy to prod. Friday 5pm release breaks
things. The on-call is paged. The CEO is asking
questions. You wish you had change governance.

## Root cause
**Without change control, chaos wins.** Use
risk-based CAB.

**Source:** ITIL 4 + ServiceNow CAB guide.

## The "CAB" concept

Change Advisory Board:
- **Reviews:** Significant changes
- **Approves:** Risk-based
- **Coordinates:** Cross-team
- **Audit:** Post-implementation

The CAB is governance.

## The "change types" pattern (ITIL 4)

For change types:
- **Standard:** Pre-approved, low-risk, repeatable
- **Normal:** Requires assessment + approval
  - **Minor:** Change manager alone
  - **Significant:** Change manager + stakeholders
  - **Major:** CAB review
- **Emergency:** Fast-tracked, post-facto review

The type is per change.

## The "CAB" anti-pattern

For over-using CAB:
- **Issue:** Every commit needs approval
- **Result:** Velocity dies
- **Fix:** Risk-based routing

The CAB is targeted.

## The "risk-based routing" pattern

For routing:
- **Low risk:** Peer reviewer / team lead (async)
- **Medium risk:** Change authority
- **High risk:** CAB
- **Emergency:** ECAB (on-call, 1h SLA)

The routing is per risk.

## The "risk score" pattern

For scoring:
- **Risk level:** Low/Med/High
- **Factors:** Impact, urgency, CMDB deps
- **Compute:** Policy engine
- **Triage:** Human or auto

The score is per change.

## The "standard change catalog" pattern

For catalog:
- **40-60% target:** Standard changes
- **Below 20%:** CAB does busy work
- **Re-evaluate:** When approved 3+ times in 90 days
- **Document:** Procedure + rollback

The catalog grows.

## The "CAB composition" pattern

For members:
- **3-5 voting:** Core
- **Cross-functional:** Eng, SRE, security, ops, product
- **Per-item experts:** Invited
- **Standing:** Or per-meeting

The CAB is small + effective.

## The "CAB meeting agenda" pattern

For 45-60 min:
1. **Roll call + quorum** (1 min)
2. **Failed/backed-out changes** (5 min)
3. **Emergency changes** (5 min)
4. **New significant/major** (25 min)
5. **Deferred/rejected** (5 min)
6. **Collisions + freezes** (5 min)
7. **Process/metrics** (5 min)
8. **AOB** (5 min)

The agenda is structured.

## The "change request template" pattern

For template:
- **What:** Summary
- **Why:** Justification
- **When:** Schedule
- **Affected:** Services
- **Risk:** Level + analysis
- **Rollback:** Plan
- **Monitoring:** SLIs
- **Test evidence:** Links

The template is required.

## The "rollback plan" pattern

For rollback:
- **Steps:** Revert procedure
- **Tested:** Before approval
- **Rollforward:** Alternative
- **Time:** Expected
- **Trigger:** Auto-rollback criteria

The rollback is required.

## The "canary + CAB" pattern

For canary:
- **CAB approves:** With canary plan
- **SLIs:** Defined
- **Auto-promote:** Within budget
- **Auto-rollback:** If SLO violated

The canary is automated.

## The "feature flag + CAB" pattern

For flags:
- **Safe rollback:** Toggle off
- **Gradual:** % rollout
- **Debt:** Track + cleanup
- **Document:** Per flag

The flag enables safety.

## The "DORA + change" pattern

For DORA:
- **Change failure rate:** % deploys cause incident
- **Lead time:** Commit to prod
- **Deploy freq:** Per day/week
- **MTTR:** Recovery time

The DORA measures change.

## The "5 KPIs" pattern

For change KPIs:
- **Change failure rate:** % causing incident
- **Lead time for change:** Commit to prod
- **Emergency change ratio:** %
- **Unauthorized change count:** Per period
- **Standard change adoption:** %

The KPIs are tracked.

## The "emergency change" pattern

For emergency:
- **Trigger:** Incident or imminent risk
- **Approval:** ECAB (on-call, 1h SLA)
- **Documentation:** Required
- **PIR:** Mandatory at next CAB
- **Limit:** Use sparingly

The emergency is fast.

## The "PIR" pattern (post-implementation review)

For PIR:
- **Required for:** Emergency, P1/P2, tier-1, 10-15% sample
- **Content:** Outcome, lessons, action items
- **Timing:** Within 1 week
- **Blameless:** Required

The PIR learns.

## The "change freeze" pattern

For freezes:
- **Holiday:** End-of-year, Black Friday
- **Launch:** Major product release
- **Audit:** Compliance period
- **Override:** ECAB only

The freeze is explicit.

## The "audit trail" pattern

For audit:
- **What changed:** Service + version
- **Who approved:** Named
- **When:** Timestamp
- **Evidence:** Tests, scans, plan
- **Outcome:** Success or rollback

The trail is immutable.

## The "automate approval" pattern

For automation:
- **Standard changes:** Fully automated
- **Low risk:** Async in ticketing system
- **Evidence collection:** Auto from CI
- **Risk scoring:** Policy engine
- **Auto-routing:** Per type

The automation is targeted.

## The "don't automate" pattern

For human judgment:
- **High risk:** Always human
- **Cross-team:** Human
- **Data schema:** Human
- **IAM changes:** Human + security

The human is for judgment.

## The "CAB setup" pattern

For setup (5-7 days):
- **Day 1:** Scope + stakeholders + template
- **Day 2:** CI/CD events + metrics
- **Day 3:** Dashboards
- **Day 4:** Rollback + monitoring required
- **Day 5-7:** Tabletop + 1 canary

The setup is staged.

## The "CAB continuous improvement" pattern

For improvement:
- **Weekly:** Pending high-risk + SLA
- **Monthly:** Audit decisions
- **Quarterly:** Reassess scoring + tools
- **Annually:** Process review

The improvement is continuous.

## The "pre-meeting" pattern

For 48-72h pre-read:
- **Materials sent:** In advance
- **Reviews done:** Before meeting
- **No cold reading:** In the room
- **Decisions ready:** Approve / modify / reject

The pre-read is mandatory.

## The "CAB + incident" pattern

For incidents:
- **Recent changes:** Linked in incident
- **Searchable:** < 1 min
- **Auto-surface:** On P1/P2
- **PIR required:** If change-related

The change-incident is linked.

## The "CMDB" pattern

For CMDB:
- **CI mapping:** What does this change touch?
- **Auto-impact:** On PR
- **Dependency:** Upstream/downstream
- **CIs:** Configuration items

The CMDB is the source.

## The "evidence store" pattern

For evidence:
- **Centralized:** Single workspace
- **Immutable:** Log-style
- **Test results:** Linked
- **Migration plans:** Stored
- **Audit-ready:** Always

The store is central.

## The "no CAB" anti-pattern

For no CAB:
- **Issue:** Free-for-all deploys
- **Risk:** Untracked changes
- **Fix:** Risk-based governance

The CAB is required.

## The "over-CAB" anti-pattern

For over-CAB:
- **Issue:** Every commit approved
- **Result:** Slow, no value
- **Fix:** Risk-based routing

The CAB is targeted.

## The "no metrics" anti-pattern

For no metrics:
- **Issue:** Can't measure
- **Fix:** DORA + 5 KPIs

The metrics are required.

## Verification
- **Test:** Standard catalog covers 40-60%
- **Test:** Risk scoring routes correctly
- **Test:** KPIs are tracked
- **Test:** PIR runs after incidents
- **Audit:** Quarterly

## Gotchas
- **The "over-CAB" anti-pattern.** Risk-based.
- **The "no metrics" anti-pattern.** Track.
- **The "no standard catalog" anti-pattern.** Build it.

## Related
- `deploy/gitops.md`
- `deploy/canary-deployments.md`
- `deploy/database-blue-green-migration.md`
- `patterns/safe-deploy-checklist.md`
- `patterns/incident-response.md`
- `patterns/slo-error-budget-deep-dive.md`
- `lessons/incident-response-runbook.md`
- CloudOps Now: https://www.cloudopsnow.in/cab-change-advisory-board/
- Motadata: https://www.motadata.com/blog/itil-change-management-best-practices
- Change Risk Intel: https://changeriskintel.com/posts/how-to-run-a-cab-meeting-in-2026/
