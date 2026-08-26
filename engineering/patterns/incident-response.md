# incident-response

**Issue:** Incident response process — when things break
**Date:** 2026-08-09
**Status:** documented (runbook)

## Symptom
Your service is down. Users are tweeting. You have 5 people
on the team. You don't know who's in charge. You spend 30
minutes deciding "should we roll back?" instead of rolling
back. The outage lasts 4 hours.

## Root cause
**Incidents need a process.** Without one, the response is
chaos. With one, the response is fast + effective.

**Source:** Google SRE — Incident response:
https://sre.google/sre-book/managing-incidents/

> "An incident is an event that causes, or may cause, a
> service to deviate from its SLO. ... The goal of incident
> response is to restore service as quickly as possible."

## The roles

### Incident Commander (IC)
- **Who:** The person in charge of the response
- **What:** Decides actions; coordinates; communicates
- **What NOT:** Does not debug; does not write code; does
  not make any other decisions

### Communications Lead
- **Who:** Usually a manager or PM
- **What:** Updates stakeholders (status page, customers,
  leadership)
- **What NOT:** Does not decide actions; only communicates

### Operations Lead
- **Who:** The person(s) debugging + fixing
- **What:** Investigates; deploys; rolls back; writes
  patches

### Scribe
- **Who:** Anyone (rotates)
- **What:** Documents every action + decision in a shared
  doc/timeline

## The 5 phases

### Phase 1: Detection (0-5 min)
- **What:** Alert fires; user reports; monitoring detects
- **Action:** Acknowledge the alert; open an incident
  channel; assign an IC
- **Tool:** PagerDuty, Opsgenie, on-call rotation

### Phase 2: Triage (5-15 min)
- **What:** Determine the scope; assess severity
- **Action:** The IC declares severity; the Ops Lead starts
  investigating; the Comms Lead starts updating
- **Severity matrix:**

| Severity | Impact | Response |
|---|---|---|
| SEV-1 | Total outage; data loss; security breach | Page everyone; war room |
| SEV-2 | Major feature broken; many users affected | Page on-call; IC in #incidents |
| SEV-3 | Minor issue; some users affected | Slack thread; investigate during business hours |
| SEV-4 | Cosmetic; no user impact | File a bug; fix later |

### Phase 3: Mitigation (15-60 min)
- **What:** Stop the bleeding (rollback, disable feature,
  scale up)
- **Action:** Roll back; disable the feature flag; revert
  the deploy
- **Goal:** Get users out of the bad state, even if the root
  cause isn't fixed

### Phase 4: Resolution (1-24h)
- **What:** Find and fix the root cause
- **Action:** Investigate; patch; deploy the fix
- **Goal:** Don't roll back the mitigation until the fix
  is deployed

### Phase 5: Post-mortem (within 1 week)
- **What:** Document what happened; what worked; what
  didn't; what to fix
- **Action:** Write a blameless post-mortem; present to the
  team; add the fixes to the backlog
- **Goal:** Learn from the incident; prevent recurrence

## The "IC handover" pattern

For long incidents, the IC rotates every 4 hours:
1. The current IC briefs the new IC
2. The new IC takes over
3. The old IC stays for 1 hour as support
4. The old IC goes to rest

Preventing IC fatigue is critical. A tired IC makes bad
decisions.

## The "war room" pattern

For SEV-1, gather in a war room (physical or virtual):
- **Video call:** Always on, no waiting
- **Shared doc:** Real-time timeline of actions
- **Screen sharing:** The Ops Lead shares their screen
- **No side conversations:** Everything in the main channel

The war room prevents "I didn't know X was happening" and
ensures everyone is aligned.

## The "first 10 minutes" checklist

When you get paged:
1. **Acknowledge** the page (so others know you're on it)
2. **Open** an incident channel (#inc-2026-08-09-db-down)
3. **Assign an IC** (could be you, or someone more senior)
4. **Check the dashboards** (CF Analytics, error tracking)
5. **Read the recent deploys** (was there a deploy in the
   last hour?)
6. **Check the status of dependencies** (DB, vendors)
7. **Post an initial status** (severity, scope, ETA)
8. **Start the timeline** (every action goes in a shared doc)

## The "rollback" decision tree

Should I roll back?
- **Was there a deploy in the last hour?** → Try rollback
- **Is the error rate 2x baseline?** → Try rollback
- **Is the latency 2x baseline?** → Try rollback
- **None of the above?** → Investigate

The default is to roll back. A bad deploy is the most common
cause of incidents. A rollback is fast (1-2 min) and safe
(can be rolled forward again).

## The "post-mortem" template

```markdown
# Post-mortem: <title>

**Date:** YYYY-MM-DD
**Severity:** SEV-X
**Duration:** X hours
**IC:** @name
**Status:** Resolved

## Summary
<1-2 sentences: what happened, what was the impact>

## Timeline
- HH:MM - Detection
- HH:MM - IC assigned
- HH:MM - Mitigation
- HH:MM - Resolution
- HH:MM - Post-mortem started

## Impact
- Users affected: N
- Error rate: X%
- Latency increase: Xms
- Data loss: N records

## Root cause
<What caused the incident, in 1-2 paragraphs>

## What worked
- <Good things that happened during the response>

## What didn't work
- <Things that should have gone better>

## Action items
- [ ] <Action 1> (owner: @name, due: YYYY-MM-DD)
- [ ] <Action 2> (owner: @name, due: YYYY-MM-DD)
```

## Verification
- **Process:** The team has a documented incident response
  process
- **Drill:** Quarterly incident drill (test the process)
- **Audit:** Annual review of incident trends

## Gotchas
- **The IC is not the debugger.** A common mistake is making
  the most senior engineer the IC, who then tries to debug
  too. Separate the roles.
- **The "blameless" part is hard.** People naturally look
  for who to blame. The post-mortem must be blameless; the
  focus is on the system.
- **Status updates are mandatory.** Every 30 min, the Comms
  Lead posts an update. Silence is scary.
- **The war room shouldn't be a megaphone.** One IC, one
  voice. Side conversations go to side channels.
- **The post-mortem must be actionable.** "Improve
  monitoring" is not actionable. "Add an alert for D1
  write errors > 100/min" is actionable.
- **The action items have owners and due dates.** Without
  these, the post-mortem is theater.
- **The IC is exhausted after 4 hours.** Rotate.

## Related
- `safe-deploy-checklist.md`
- `error-budget-slo.md`
- `health-check-endpoint.md`
- SRE book: https://sre.google/sre-book/managing-incidents/
- Atlassian incident handbook: https://www.atlassian.com/incident-management/handbook
- PagerDuty: https://www.pagerduty.com/
