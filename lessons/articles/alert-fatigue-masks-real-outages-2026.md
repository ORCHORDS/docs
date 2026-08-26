# alert-fatigue-masks-real-outages-2026

> Pageable on-call noise is no longer a vibe problem. In 2025-2026 it became a
> direct root cause of multi-hour customer-visible outages.

## Symptom

A regional payment API goes down for 4 hours on a Tuesday afternoon. The
paging system fired the first critical alert at 14:07. The on-call engineer
acknowledged it at 14:09 — then **silenced it**, because the same alert had
fired 38 times in the previous 72 hours and every previous occurrence was a
false positive caused by a flaky NAT gateway. The actual outage wasn't fully
scoped until 16:40, when a second team noticed their checkout success rate
had collapsed and raised a manual incident.

The postmortem's root cause was not the NAT gateway and not the payment bug.
It was: **"the signal that would have caught this was buried under 38 pages
that trained the on-call to ignore it."** Three separate reviewers wrote
"alert fatigue" in the timeline before anyone admitted it was load-bearing.

This is the 2026 shape of the problem. Alert noise is no longer just a
quality-of-life complaint — it is a fault path. When the real alert arrives,
it inherits the credibility of the 38 false ones before it.

## Gotchas

- **"We'll tune alerts later" never happens.** Every team that hits this
  pattern had a Jira ticket to deduplicate the noisy alert. It was 9 months
  old and unprioritized. Treat alert noise as a Sev-2 in its own right —
  schedule the cleanup the same week the noise starts, not after the outage.

- **Alerts that auto-resolve train humans to ignore them.** A flapping check
  that pages, clears, pages, clears teaches the on-call that "it'll probably
  clear." Real degradations that don't self-heal then get the same 10-minute
  wait. If an alert has a >40% auto-resolve rate, it is mis-scoped — fix the
  signal or stop paging on it.

- **Multi-channel fan-out makes it worse, not better.** Routing the same
  alert to PagerDuty + Slack + email + SMS feels safer. It is the opposite:
  the on-call learns to swipe-dismiss all four, and the real one gets lost
  in the same gesture. Pick one paging channel. Use the others for context,
  not for alerting.

- **Severity inflation hides the real Sev-1.** When everything is Sev-1,
  nothing is. We saw a service with 14 active Sev-1 alert rules, of which
  zero had paged in the last month. The one genuinely critical condition
  (checkout success rate < 95%) was filed as Sev-2 because "it's a derived
  metric." Re-baseline severities quarterly against actual impact, not
  against whoever last touched the rule.

- **Synthetic checks and real-user checks must agree before either pages.**
  The classic trap: synthetic monitor from a single region says the service
  is up, RUM says 30% of users are failing. Two contradictory pages fire,
  on-call trusts the synthetic (it's "objective"), ignores the RUM.
  Require that synthetic and RUM share an alert key so a disagreement
  escalates rather than cancels.

- **AI-summarized alert grouping can swallow the real incident.** 2026
  tooling that LLM-summarizes "47 related alerts in the last hour" is great
  until it groups the one real outage under a benign summary header. Always
  surface the raw underlying alerts beneath any AI grouping — never let the
  summary be the only thing the on-call sees.

- **On-call acknowledgement metrics don't measure what you think.** "MTTA
  was 2 minutes" is meaningless if the on-call acknowledged-and-muted
  without reading. Track time-to-*action* (first diagnostic step taken),
  not time-to-ack. We logged a 90-second MTTA on the incident above; the
  real time-to-investigation was 2.5 hours.

- **Quiet periods are a control, not a reward.** If a service has gone 30
  days without a page, that is a signal to audit whether it's genuinely
  healthy or whether monitoring has decayed. Several 2025 outages traced
  back to services whose dashboards had quietly stopped ingesting weeks
  earlier.

## What to do instead

1. Cap paging volume per on-call per shift. If an engineer pages more than
   ~5 times in a 12-hour shift, the alert rules are wrong, not the engineer.
2. Run a monthly "alert death row": every alert that hasn't correlated to a
   real incident in 90 days gets a hearing. Silence, fix, or delete.
3. Make every page carry a runbook link and an expected-first-action. A page
   with no runbook is a notification, not an alert — route it to chat, not
   to the phone.
4. Measure signal-to-noise as a first-class SLO: "percentage of pages that
   led to a real human action." Below 50% means the system is crying wolf.
