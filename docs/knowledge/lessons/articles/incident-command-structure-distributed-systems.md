# Incident Command Structure for Distributed Systems

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A P1 fires. Slack fills with engineers. Everyone is talking over each other,
duplicate work is happening, no one owns the customer communication, and the
incident commander is also the person debugging the database. Forty-five minutes
later someone asks "who's the IC?" — nobody knows. The outage itself is resolved
but the coordination failure extended MTTR by 2x and produced a status page that
went dark for 30 minutes.

You need a repeatable command structure that scales from a two-person on-call
to a 20-person war room without rewiring the org chart every time.

## Context

The Incident Command System (ICS) originated in wildfire management in the 1970s
and was standardized into NIMS (National Incident Management System) by FEMA.
Google's SRE book adapted the core ideas for distributed systems in 2016.
PagerDuty, Atlassian, and Netflix all publish their own variants. The common
thread: **one person holds authority, every other role is explicit, and
communication flows through the command structure rather than around it.**

For distributed systems the key adaptation is that the "incident" is
simultaneously a technical problem (services are broken), a communication
problem (customers need updates), and a coordination problem (multiple teams
own different blast-radius components). The command structure solves all three
without requiring everyone to be a generalist.

Roles are assigned to *positions*, not people. A senior engineer who normally
leads debugging can be subordinated to a junior IC who is a stronger coordinator.
That's correct and expected.

---

## The Four Core Roles

### Incident Commander (IC)

The IC owns the incident end-to-end. They do **not** debug. Their job is:

- Declare incident severity and open the incident channel
- Assign the other roles explicitly, by name, in the channel
- Time-box each hypothesis cycle (typically 10–15 minutes)
- Call the all-clear or escalate to the next severity level
- Hand off cleanly across timezone boundaries

The IC produces a running timeline in the incident doc. At no point should the
IC be the one running queries or reading logs. If the IC is the only available
engineer, that is a staffing problem, not a reason to blend roles.

```
IC check-in cadence (recommended):
  t+0:   Open channel, assign roles, state current hypothesis
  t+15:  Checkpoint — share new info, confirm or discard hypothesis
  t+30:  Stakeholder update (even if no new info: "still investigating X")
  t+45:  Escalate or re-assign if no progress
  t+60:  Mandatory IC check: am I the bottleneck?
```

### Operations Lead (Ops)

The Ops lead coordinates the technical responders. They own the "war room"
view: who is looking at what, what has been ruled out, what is being tried now.
They prevent duplicate investigation and communicate findings back to the IC.

In a small incident the IC and Ops Lead can be the same person. For SEV-1
they must be separate.

### Communications Lead (Comms)

Comms owns every external-facing message: status page updates, customer email,
internal Slack #incidents-public, and stakeholder briefings to the VP/CTO.

The Comms lead does not need to understand the technical root cause in detail.
They need one sentence from Ops/IC every 15–30 minutes and a confidence level:
"we know what it is and we're fixing it" vs "we're still isolating."

Comms never speculates publicly. The script is:

```
Status page template:
  INVESTIGATING (no cause known):
    "We are aware of [symptom] affecting [scope]. Our team is investigating.
     Next update: [time]."

  IDENTIFIED (cause known, fix in progress):
    "We have identified [vague cause class, e.g. 'a configuration issue']
     affecting [scope]. A fix is being applied. Next update: [time]."

  MONITORING (fix deployed):
    "We have deployed a fix and are monitoring recovery. We will confirm
     resolution by [time]."

  RESOLVED:
    "The incident is resolved. [Scope] is operating normally.
     A post-mortem will be published by [date]."
```

### Scribe

The Scribe keeps the incident timeline document updated in near-real-time. Every
hypothesis, every action, every command run, every conclusion goes in. This is
the primary artifact for the post-mortem and for IC handoffs.

```markdown
## Incident Timeline — [YYYY-MM-DD HH:MM UTC]

| Time (UTC) | Who        | Action / Finding                                      |
|------------|------------|-------------------------------------------------------|
| 14:03      | alert-bot  | PagerDuty: p99 latency > 5s on api.example.com       |
| 14:05      | alice (IC) | Incident opened. SEV-1. Roles: IC=alice ops=bob       |
|            |            | comms=carol scribe=dave                               |
| 14:07      | bob (ops)  | Hypothesis: DB connection pool saturation             |
| 14:11      | bob (ops)  | DB connections normal. Ruling out DB. Next: CDN.      |
| 14:18      | carol      | Status page updated: INVESTIGATING                    |
| 14:22      | bob (ops)  | CDN cache hit rate dropped to 12% at 13:58 UTC        |
| 14:25      | alice (IC) | Hypothesis confirmed: origin flood from cache miss.   |
|            |            | Action: increase cache TTL + purge stale rules        |
| 14:38      | bob (ops)  | TTL updated. Cache hit rate recovering: 67% → 89%     |
| 14:45      | alice (IC) | Metrics stable. Entering MONITORING phase.            |
| 15:00      | alice (IC) | RESOLVED. All clear. Post-mortem due 2026-08-25.      |
```

---

## Severity Levels and Role Activation

Not every incident needs four roles. Define activation thresholds in your runbook
so teams activate the right structure without a meeting.

```yaml
# incident-severity.yaml
severity_levels:
  sev3:
    definition: "Single customer impact, no data loss, degraded but not down"
    roles_required: [ic]
    roles_optional: [scribe]
    status_page: false
    mttr_target_minutes: 120

  sev2:
    definition: "Multi-customer impact OR single customer data risk"
    roles_required: [ic, ops_lead]
    roles_optional: [scribe, comms]
    status_page: true
    mttr_target_minutes: 60

  sev1:
    definition: "Wide customer impact, SLA breach likely, or data loss"
    roles_required: [ic, ops_lead, comms, scribe]
    status_page: true
    mttr_target_minutes: 30
    escalation: vp_engineering_paged

  sev0:
    definition: "Total outage, customer data loss confirmed, regulatory breach"
    roles_required: [ic, ops_lead, comms, scribe, executive_sponsor]
    status_page: true
    mttr_target_minutes: 15
    escalation: [cto_paged, legal_notified, comms_external_pr]
```

---

## IC Handoff Protocol Across Timezones

Long incidents crossing timezone boundaries fail silently without an explicit
handoff. The outgoing IC must:

1. Freeze all active investigation for 5 minutes.
2. Write a handoff summary in the incident doc (use the template below).
3. Read it aloud in the incident call with the incoming IC present.
4. The incoming IC explicitly accepts by name: "I am now IC. Alice is off."

```markdown
## IC Handoff — [TIME UTC] — [outgoing] → [incoming]

**Current status**: [one sentence]
**What we know**: [bullet list of confirmed findings]
**What we ruled out**: [bullet list]
**Active hypothesis**: [current best theory]
**In progress**: [actions underway and who owns them]
**Next checkpoint**: [time]
**Stakeholders who have been briefed**: [names/roles]
**Landmines**: [things that could go wrong in the next 2h]
```

Skipping this and saying "it's in Slack" is an anti-pattern. Slack is not a
timeline; it's a firehose.

---

## Anti-patterns

- **IC debugging** — The IC is in the terminal running queries. Nobody is
  coordinating. Divergent work happens. Fix: explicitly hand the terminal to
  the Ops lead and step back.

- **Role-less war room** — Fifteen engineers in the call, anyone can say
  anything, no one has authority to call a decision. This is a committee, not
  incident response. Fix: the first person to open the channel assigns roles
  within 2 minutes.

- **Silent status page** — Status page goes 45+ minutes without an update
  because Comms is waiting for the technical answer. Customers assume you're
  ignoring them. Fix: update on schedule even if the update is "still
  investigating, no new information."

- **Merged Ops and Scribe** — The person debugging is also keeping the
  timeline. The timeline stops being updated when things get complicated.
  Fix: scribe is a dedicated role, ideally someone who can type faster than
  they debug.

- **Severity inflation** — Every error alert is a SEV-1. IC burn-out follows.
  Fix: written severity criteria, annually reviewed. Alerts fire at SEV-3 by
  default; humans promote.

- **No explicit all-clear** — The channel just goes quiet. Monitoring stops.
  Three engineers are still watching dashboards a day later. Fix: IC must say
  the words "this incident is resolved" and close the channel.

---

## Gotchas

- **IC authority must be announced** — If the IC is not stated explicitly at
  the start, engineers will argue about decisions. "Alice is IC" in the channel
  header eliminates this.

- **PagerDuty/incident tools create roles automatically** — This is useful but
  can give a false sense that the structure is working. Check that the *humans*
  behind the roles are actually filling them, not just acknowledged the page.

- **The Comms lead needs pre-approved language** — Novel situations under
  pressure produce novel language that legal hasn't reviewed. Maintain a
  comms playbook with 10–15 pre-approved templates for common failure modes
  (outage, data breach, degraded performance, third-party dependency).

- **Distributed teams cause ghost roles** — An engineer in a different timezone
  accepts the Ops Lead role and then goes offline 2 hours later without a
  handoff. Track role holders in the incident doc with their shift end times.

- **Do not rotate ICs mid-incident unnecessarily** — Every handoff costs 10–15
  minutes and risks losing context. Limit handoffs to timezone boundaries or
  when the IC is clearly impaired.

---

## Verification

After your next incident, score it on these criteria:

```
Incident Command Scorecard
--------------------------
[ ] IC was assigned by name within 5 minutes of incident open
[ ] All four roles were filled (or explicitly waived) within 10 minutes
[ ] Status page had at least one update per 30 minutes
[ ] Scribe timeline has no gap longer than 20 minutes
[ ] IC did not run any diagnostic commands during the incident
[ ] IC handoffs (if any) used the written handoff template
[ ] Explicit all-clear was called by the IC
[ ] Post-mortem was scheduled before the channel was closed
```

Score below 6/8 → run a tabletop drill within 30 days. Score below 4/8 →
run one immediately.

---

## Related

- `blameless-postmortem-incident-review.md`
- `incident-handoff-cross-timezone.md`
- `incident-communication-stakeholder-updates.md`
- `on-call-rotation-design-runbooks.md`
- `write-the-runbook-before-the-incident.md`
- `incident-timeline-capture-must-be-automatic-2026.md`

## Sources

- Dekker, S. *The Field Guide to Understanding Human Error* (3rd ed., 2014)
- Google SRE Book, Ch. 14 "Managing Incidents" — sre.google/sre-book/managing-incidents/
- PagerDuty Incident Response Guide — response.pagerduty.com
- NIMS ICS Overview — training.fema.gov/emiweb/is/icsresource/
- Atlassian Incident Management Handbook — atlassian.com/incident-management
- Lorin Hochstein, *Incidents as We Imagine Them versus How They Actually Are* (2019)
