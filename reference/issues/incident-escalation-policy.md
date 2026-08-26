# Incident Escalation Policy

## Symptom

A P1 incident drags on for 4 hours because the on-call engineer "almost has
it fixed" and never escalates. By the time management learns about it, the
outage has cost $200K in lost revenue and the customer trust team has no
warning before angry tweets start. Alternatively: the on-call engineer pages
their manager at 2 AM for a P3 bug that could wait until morning, burning out
the escalation chain and ensuring the next "escalation" is treated as
cry-wolf.

The two failure modes are symmetric and equally damaging:
- **Under-escalation**: the person who could help doesn't know they're needed,
  incidents drag on, stakeholders are blindsided.
- **Over-escalation**: the escalation chain is desensitized, and when a real
  "wake up the VP" moment arrives, nobody answers.

A team without a written, practiced escalation policy will oscillate between
these two failure modes with every incident, depending on the personality of
whoever happens to be on-call.

## Common Root Causes

- **No documented "when to escalate" criteria.** The on-call engineer relies
  on gut feel. A junior engineer escalates too late because they don't want
  to "bother" senior staff. A senior engineer escalates too late because
  they're confident they can fix it.
- **Escalation paths are implicit/tribal.** "Ask Sarah, she knows the payment
  service." Sarah goes on vacation, and now nobody knows the path. Or Sarah
  leaves the company, and the knowledge evaporates entirely.
- **Ambiguous severity-to-escalation mapping.** The severity matrix says
  "P0 = page everyone," but "everyone" is undefined. Does that include the
  VP of Engineering? Legal? The CEO? On-call engineers guess wrong in both
  directions.
- **No timed escalation.** An incident is declared P1, and 3 hours later
  it's still P1 with no escalation. There is no rule that says "P1 unresolved
  after 2 hours → escalate to tech lead."
- **Escalation and notification are conflated.** Escalation (get someone to
  take over or help) and notification (keep stakeholders informed) are
  different actions routed through the same channel. Stakeholders get paged
  for status updates; engineers get Slack-mentioned for war-room help. The
  signals blur.
- **Fear of escalation as weakness.** Cultural norm where asking for help is
  seen as incompetence. On-call engineers struggle alone rather than
  escalate, because escalating "means I couldn't handle it."

## Gotchas

- **"Escalate to the manager" is not an escalation path.** Managers
  typically cannot fix technical problems. Escalation should go to people
  with *decision authority or technical context*, not org-chart superiors.
  Escalating a database corruption issue to a non-technical manager wastes
  their time and adds zero resolution capability.
- **Time-based escalation must be automatic, not manual.** "Escalate if
  unresolved after 2 hours" relies on the already-stressed on-call engineer
  remembering to do it. Use the incident management tool's timer-based
  escalation rules (PagerDuty/OpsGenie both support this) so it happens
  without human intervention.
- **Escalation policies rot.** The escalation tree written 18 months ago
  names three engineers who have since left the company. Nobody updated it
  because "we haven't had a P0 since then." The first time you need it is
  the first time you discover it's broken. Review quarterly.
- **Over-notification during incidents.** Posting every update to a broad
  channel trains people to mute the channel. Reserve incident-specific
  channels for the incident; use a separate, low-traffic status channel for
  stakeholder comms. Muting is permanent damage to the comms pipeline.
- **"I'll just DM the person who wrote this code" bypasses the system.**
  Direct-messaging the original author feels faster than following the
  escalation policy, but it creates invisible dependencies (that person is
  now implicitly on-call forever), doesn't create an audit trail, and
  fails when they're unavailable. Always route through the documented
  escalation path even if it feels slower.
- **Escalation without context wastes the escalated-to person's time.**
  Paging the tech lead with "production is down, help" forces them to spend
  10 minutes asking "which service? since when? what's been tried?" Use a
  structured handoff: severity, impact, timeline, what's been attempted,
  current hypothesis.
- **Confusing escalation with blame.** "Escalating this to the team that
  deployed the bad commit" turns escalation into a political act. Escalation
  is about getting the incident resolved, full stop. Blame, if any, belongs
  in the postmortem — never in the escalation.

## Escalation Framework

1. **Define severity-to-escalation mapping.**
   - **P0**: Page IC (incident commander), on-call engineer, tech lead,
     on-call manager within 5 min. Timed re-escalation every 15 min until
     acknowledged.
   - **P1**: Page on-call engineer + tech lead within 15 min. Escalate to
     manager if unresolved after 2 hours.
   - **P2**: Page on-call engineer within 1 hour. Escalate to tech lead if
     unresolved after 8 hours (business hours).
   - **P3/P4**: No paging. Slack notification to owning team. No timed
     escalation.
2. **Define role-based escalation targets** (not name-based):
   - **Incident Commander**: coordinates the response, owns the timeline,
     decides when to declare/resolve.
   - **Tech Lead / SME**: brought in when the on-call engineer needs domain
     expertise on a specific system.
   - **On-call Manager**: brought in for resource decisions (spin up more
     people, approve a risky rollback, engage vendor support).
   - **Comms Lead**: owns stakeholder and customer communication, so the
     IC can focus on resolution.
3. **Implement timed auto-escalation.** Configure the paging tool to
   auto-escalate: if P0 not acknowledged in 5 min → page backup. If P1 not
   resolved in 2 hours → page tech lead. Do not rely on humans to remember
   timers during an incident.
4. **Use a structured escalation message.** The escalated-to person should
   receive: severity, affected service, user impact (how many, what
   broken), start time, what's been tried, current hypothesis, what help
   is needed. Template this so it takes 60 seconds to fill out.

## Prevention

- **Document the escalation policy in one place.** Not scattered across
  wikis, Slack pins, and on-call runbooks. One canonical doc, linked from
  the incident channel topic and the on-call scheduler.
- **Practice escalation during game days.** Run a simulated P0 and verify
  the escalation chain actually reaches the right people in the expected
  time. Drills expose broken paths before real incidents do.
- **Track escalation metrics.** Mean time to escalate (MTTE), escalation
  rate per incident, and "escalations that should have happened but didn't"
  (identified in postmortems). If MTTE is high, the policy is failing.
- **Decouple escalation from blame culturally.** Make it explicit: "It is
  always correct to escalate if you are uncertain. There is no penalty for
  escalating too early; there is a penalty for escalating too late." Repeat
  this until it's internalized.
- **Review the escalation tree quarterly.** Verify every named role/rotation
  still maps to a current employee with current contact info. Remove the
  departed, add the hired, and test that paging actually reaches them.
