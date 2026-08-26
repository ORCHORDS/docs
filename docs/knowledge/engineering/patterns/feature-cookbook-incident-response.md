# feature-cookbook-incident-response

**Issue:** Incident response — paging, comms, post-mortem
**Date:** 2026-08-09
**Status:** documented

## Symptom
The site is down. You don't know who's on call. You
scramble. You find the on-call after 30 min. You fix it
after 2 hours. You never write a post-mortem. The same
issue happens again next month.

## Root cause
**Without an incident response plan, every incident is
chaos.**

**Source:** PagerDuty incident response guide.

## The "on-call" pattern

For on-call:
- **Rotation:** Weekly rotation, handoff on Monday
- **Primary:** First responder
- **Secondary:** Backup if primary is unresponsive
- **Escalation:** Manager for major issues

A clear on-call rotation is the foundation.

## The "alert" pattern

For alerts, define them by SLO:
- **Latency:** Alert if p99 > 500ms for 5 min
- **Error rate:** Alert if errors > 1% for 5 min
- **Uptime:** Alert if 5xx rate > 0.5% for 5 min
- **DB health:** Alert if `SELECT 1` fails 3 times

```ts
async function checkHealth(env: Env): Promise<void> {
  try {
    const start = Date.now();
    await env.DB!.prepare('SELECT 1').first();
    const duration = Date.now() - start;

    if (duration > 1000) {
      logEvent('health.slow', 'warn', { durationMs: duration });
    }
  } catch (err) {
    logEvent('health.error', 'error', { error: String(err) });
    await pageOnCall({ severity: 'critical', message: 'DB is unreachable' });
  }
}
```

The alert is automatic.

## The "page" pattern

For paging, use PagerDuty / Opsgenie:
- **Critical:** Page immediately
- **Warning:** Slack / email
- **Info:** Dashboard

The severity determines the channel.

## The "incident declaration" pattern

For incident declaration:
1. **Symptom:** What is the user seeing?
2. **Severity:** Critical / Major / Minor
3. **Impact:** How many users are affected?
4. **Status:** Investigating / Identified / Mitigated / Resolved
5. **Owner:** Who is the incident commander?

A clear declaration is the start.

## The "comms" pattern

For comms, document in a single channel:
```markdown
# Incident #2026-08-09-01: Site down

**Severity:** Critical
**Impact:** All users
**Commander:** @alice
**Status:** Investigating

## Timeline
- 14:23 UTC: Site unreachable
- 14:25 UTC: Incident declared
- 14:30 UTC: Root cause identified (DB connection pool exhausted)
- 14:45 UTC: Mitigation in place
- 15:00 UTC: Resolved

## Root cause
The connection pool was exhausted by a runaway query.

## Mitigation
- Killed the runaway query
- Restarted the connection pool

## Action items
- [ ] Add a query timeout (P1, @alice, by 2026-08-12)
- [ ] Add connection pool monitoring (P2, @bob, by 2026-08-15)
```

The comms is a single source of truth.

## The "incident commander" pattern

For incident command:
- **One person:** The IC
- **Decides:** What to do, what to communicate
- **Delegates:** The hands-on work
- **Updates:** The status page

A clear IC reduces chaos.

## The "status page" pattern

For status, use a status page:
- **Operational:** Green
- **Degraded performance:** Yellow
- **Partial outage:** Orange
- **Major outage:** Red

Update the status page within 5 min of the incident.

## The "mitigation vs resolution" pattern

For incidents, separate mitigation from resolution:
- **Mitigation:** Stop the bleeding (e.g. revert the
  deploy)
- **Resolution:** Fix the root cause (e.g. add a
  missing index)

Mitigation is fast; resolution takes longer.

## The "post-mortem" pattern

For post-mortems, write one for every incident:
- **Blameless:** No "you should have"
- **Root cause:** What allowed this to happen?
- **Detection:** How was it detected?
- **Response:** How was it handled?
- **Lessons:** What did we learn?
- **Action items:** P1/P2 with owners + dates

```markdown
# Post-mortem: Incident #2026-08-09-01

## What happened
The DB connection pool was exhausted.

## Why
A runaway query held connections for 30+ min.

## Detection
DB health check failed; users reported errors.

## Response
- 14:23: Outage started
- 14:25: Incident declared
- 14:30: Root cause identified
- 14:45: Mitigation in place
- 15:00: Resolved

## What went well
- Health check caught it
- On-call responded in 5 min
- Mitigation in 22 min

## What went poorly
- The query didn't have a timeout
- The pool was at 100% during the issue

## Action items
- [ ] Add a 5s query timeout (P1, @alice, by 2026-08-12)
- [ ] Add pool size alert (P2, @bob, by 2026-08-15)
- [ ] Add runaway query detector (P3, @charlie, by 2026-08-20)
```

The post-mortem is blameless.

## The "blameless" pattern

For blameless post-mortems:
- **No "you should have"** — focus on the system
- **No "I told you so"** — focus on the fix
- **No "we already knew"** — focus on the action items
- **Yes "the system allowed this"** — the system is the
  fix target

Blameless culture improves response.

## The "5 whys" pattern

For root cause, ask 5 whys:
1. **Why was the site down?** The DB pool was exhausted.
2. **Why was the pool exhausted?** A query held all
   connections.
3. **Why did the query hold all connections?** It was
   missing a LIMIT.
4. **Why was LIMIT missing?** The dev assumed the table
   was small.
5. **Why was the table not small?** A growth event.

The 5th why is the real root cause.

## The "action item" pattern

For action items:
- **Specific:** Not "improve monitoring" but "add pool
  size alert"
- **Owned:** One person
- **Dated:** By when
- **Tracked:** In the issue tracker

Action items are followed up.

## The "incident anti-pattern" anti-patterns

### 1. No on-call
- **Issue:** No one responds; the issue lasts hours
- **Fix:** Define on-call rotation

### 2. No alerts
- **Issue:** The user is the alert
- **Fix:** Define SLO-based alerts

### 3. No comms
- **Issue:** The team doesn't know what's happening
- **Fix:** Single Slack channel + status page

### 4. No mitigation
- **Issue:** Trying to fix the root cause takes too
  long
- **Fix:** Mitigate first, fix second

### 5. No post-mortem
- **Issue:** The same incident happens again
- **Fix:** Write a post-mortem for every incident

### 6. Blame culture
- **Issue:** People hide problems
- **Fix:** Blameless post-mortems

## Verification
- **Test:** Alert fires on simulated failure
- **Test:** On-call rotation is clear
- **Test:** Comms channel is set up
- **Live:** Status page is updated
- **Audit:** Quarterly review of incidents

## Gotchas
- **The "no on-call" anti-pattern.** No one responds.
- **The "no comms" anti-pattern.** The team is in the
  dark.
- **The "no post-mortem" anti-pattern.** Lessons aren't
  captured.
- **The "blame culture" anti-pattern.** People hide
  problems.

## Related
- `incident-response.md`
- `safe-deploy-checklist.md`
- `error-budget-slo.md`
- `observability-three-pillars.md`
- `feature-cookbook-disaster-recovery.md`
- `feature-cookbook-monitoring.md`
- PagerDuty: https://www.pagerduty.com/
- Atlassian incident: https://www.atlassian.com/incident-management
