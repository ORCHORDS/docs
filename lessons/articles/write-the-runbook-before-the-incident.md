# write-the-runbook-before-the-incident

**Issue:** Incident response without a runbook degrades into improvised, inconsistent actions that extend downtime
**Date:** 2026-08-11
**Status:** documented

## What happened
A database failover was triggered during an incident. The on-call engineer had never performed a manual failover. They spent 25 minutes searching Slack for past instructions, found three contradictory threads, and attempted a procedure from a post that predated a major infrastructure change. The wrong procedure was executed, causing additional data inconsistency that extended the incident by two hours.

## The lesson
Write the runbook before the incident. For every system that can fail, document: what failure looks like (symptoms, alerts), step-by-step remediation procedures, commands with expected output, and escalation contacts. The runbook must be reviewed and tested by someone other than its author before it is needed.

## Why it matters
Under incident stress, cognitive load is high and time is short. A runbook removes the need to reason from first principles about a system you may only partially understand. It also creates consistency across on-call rotations and reduces the skill dependency of any single engineer.

## How to apply
- [ ] For every critical system, create a runbook before that system goes to production.
- [ ] Include: symptom description, affected alert name, step-by-step procedure, expected outputs, rollback steps, and escalation contacts.
- [ ] Have a second engineer execute the runbook in staging as validation before it is published.
- [ ] Link runbooks directly from alert notifications so the on-call engineer finds it in one click.
- [ ] Review and update runbooks every six months or after any incident that reveals a gap.

## Related
- `on-call-rotation-needs-sustainable-load.md`
- `blameless-culture-produces-better-postmortems.md`
- `always-test-rollback-before-deploying.md`
