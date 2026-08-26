# automated-incident-handling

**Issue:** Automated incident handling — 5 playbooks
**Date:** 2026-08-09
**Status:** documented

## Symptom
Incidents are 2am. Manual triage. The same playbook
every time. 30 min to detect. You wish you had
automation.

## Root cause
**Manual incident response is slow.** Automate.

**Source:** PagerDuty 2026.

## The "5 automation playbooks" pattern

For automation:
1. **Intelligent alert triage:** Reduce noise
2. **Automated diagnostics:** Run on creation
3. **Remediation + self-healing:** Auto-fix
4. **Stakeholder communication:** Auto-notify
5. **Post-incident learning:** Auto-summary

The 5 are the ladder.

## The "crawl-walk-run" pattern

For rollout:
- **Crawl:** Single read-only (diagnostics, log query)
- **Walk:** Chained actions (restart + health check)
- **Run:** Self-healing (auto-fix common)

The crawl is first.

## The "alert triage" pattern

For triage:
- **Grouping:** Related → single incident
- **Severity rules:** Tied to service
- **Routing:** To right team
- **Dedup:** Same alert, not 10

The triage is automated.

## The "automated diagnostics" pattern

For diagnostics:
- **Log queries:** Auto on incident create
- **Metric snapshots:** Health check
- **Change correlation:** Recent deploy?
- **Attach data:** To incident

The diagnostics are automated.

## The "remediation + self-healing" pattern

For auto-fix:
- **Top 10 incidents:** Documented, frequent
- **Convert:** To automated jobs
- **RBAC:** Per action
- **Approval gates:** For high-risk
- **Circuit breakers:** For runaway
- **Test:** In staging

The remediation is gated.

## The "stakeholder communication" pattern

For comms:
- **Auto channel:** Create on SEV1/2
- **Templated updates:** On cadence
- **ITSM sync:** Auto ticket
- **Status page:** Auto publish
- **Internal channel:** Status updates

The comms is automated.

## The "post-incident learning" pattern

For PIR:
- **Auto timeline:** All actions captured
- **AI summary:** Draft review
- **Action items:** With owners, dates
- **Recurring causes:** Feed back

The learning is automated.

## The "metrics" pattern

For success:
- **MTTR:** Headline
- **Alert noise:** % reduced
- **Auto-resolution rate:** % without human
- **Pages per shift:** Lower = better
- **MTTA:** Acknowledge time
- **MTTD:** Detect time

The metrics are tracked.

## The "start small" pattern

For starting:
- **Pick:** Top frequent incident
- **Document:** Resolution steps
- **Convert:** To runbook
- **Test:** Staging first
- **Enable:** Production

The start is small.

## The "self-healing" pattern

For self-healing:
- **Trigger:** Event
- **Diagnostic:** Auto-run
- **Fix:** Auto-apply
- **Verify:** Auto-check
- **Escalate:** If fix fails

The healing is auto.

## The "approval gate" pattern

For high-risk:
- **Trigger:** Action requires approval
- **Who:** Per RBAC
- **Why:** Prevent runaway automation
- **Audit:** Per action

The gate is required.

## The "no automation" anti-pattern

For no auto:
- **Issue:** 2am manual toil
- **Fix:** Crawl-walk-run

The automation is required.

## The "too much too soon" anti-pattern

For too soon:
- **Issue:** Production damage
- **Fix:** Crawl first, then walk

The pace is gradual.

## The "no approval" anti-pattern

For no approval:
- **Issue:** Runaway automation
- **Fix:** Approval gates for high-risk

The approval is required.

## The "no metrics" anti-pattern

For no metrics:
- **Issue:** Don't know if working
- **Fix:** Track MTTR, noise, auto-rate

The metrics are required.

## The "incident checklist" pattern

For checklist:
- [ ] Alert triage automated
- [ ] Diagnostics on create
- [ ] Top 10 incidents automated
- [ ] Comms auto
- [ ] PIR auto
- [ ] Metrics tracked
- [ ] Approval gates
- [ ] Tested in staging

The checklist is 8.

## Verification
- **Test:** MTTR down
- **Test:** Noise down
- **Test:** Auto-rate up
- **Test:** Pages down
- **Audit:** Quarterly

## Gotchas
- **The "too much too soon" anti-pattern.** Crawl first.
- **The "no approval" anti-pattern.** Gates.
- **The "no metrics" anti-pattern.** Track.

## Related
- `lessons/incident-response-runbook.md`
- `patterns/slo-error-budget-deep-dive.md`
- `patterns/chaos-engineering-deep-dive.md`
- `deploy/cab-change-management.md`
- PagerDuty: https://www.pagerduty.com/resources/automation/learn/best-practices-automated-incident-handling/
- incident.io: https://incident.io/blog/incident-management-best-practices-2026
- DevToCash: https://devtocash.com/blog/incident-management-runbook-template-2026
