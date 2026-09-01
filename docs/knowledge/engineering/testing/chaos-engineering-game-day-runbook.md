# Chaos Engineering Game Day Runbook

A chaos experiment only contributes to resilience if the team learns from it. Game days are
the structured rehearsal that turns a chaos tool from a thing the team runs into a thing the
team trusts: a scheduled event where the system is subjected to a planned fault, the on-call
rotation responds, and the gaps between the system's actual behaviour and the documented
behaviour are written down and acted on. Without game days the chaos tool exercises code paths
in production while the humans who own the system remain spectators. With game days the
humans rehearse the response, the runbook gets corrected against observed reality, and the
system's resilience becomes a thing the team can talk about, not a property the tool claims.

## Scope

Covers the structure and operation of a chaos game day: experiment selection, scope and
aborts, the runbook that on-call uses during the event, the observation and post-mortem
workflow, and the follow-through that converts findings into changes. Applies to organisations
running any form of chaos practice — fault injection at the network, process, or dependency
level — whether the underlying tool follows the Principles of Chaos methodology or a lighter
in-house variant. Does not cover the tool implementation or the design of individual fault
scenarios.

## Workflow or implementation guidance

1. **Treat game day as a scheduled event with an agenda and an owner.** A game day without an
   owner dissolves into ad-hoc exploration. The owner pre-selects the experiment, sets the
   scope, invites participants, prepares the runbook, runs the debrief, and follows through
   on findings. Game days run on a cadence — typically monthly — and the calendar invite is
   the social contract.
2. **Pick the experiment from real risk, not from the tool's menu.** A useful experiment
   targets a failure mode that the team already worries about but has never validated:
   a region-isolated dependency failure, a slow downstream, a partial cache outage, an
   authentication provider returning errors. The Principles of Chaos framing is to start with
   a steady state, hypothesise the response, and design the experiment to test the hypothesis
   rather than to "do chaos".
3. **Define the steady state explicitly.** Without a steady-state hypothesis, every observed
   behaviour is interpreted post hoc. The hypothesis names the metric the team expects to
   remain within bounds (for example, *successful checkout rate remains above 99%*, or
   *p99 latency on `POST /orders` remains below 800ms*) and the population the steady state
   applies to (which tenants, which regions, which percentage of traffic).
4. **Scope the blast radius before injecting the fault.** The experiment should affect only
   the smallest defensible surface: a canary tenant, a single region, a single request class.
   The abort criteria — explicit conditions under which the fault is removed regardless of
   findings — are written down, agreed by the owner, and known to every participant.
5. **Bring a runbook the on-call would actually use.** The runbook names the experiment, the
   hypothesis, the steady-state metric, the abort criteria, the command sequence to inject the
   fault, the dashboards to watch, and the command sequence to remove it. The runbook is
   printed or pinned on screen during the event. A runbook that the on-call has never read
   before the event is a finding in itself.
6. **Run the experiment with a human in the loop.** The chaos tool injects the fault; the
   on-call observes the system; the on-call decides to abort or continue. The point is to
   rehearse the judgement, not to demonstrate the tool. If the on-call is replaced by a fully
   autonomous response, the game day is an exercise in tooling rather than in human response.
7. **Observe before, during, and after.** Capture the steady state before the fault, the
   transition when the fault is applied, the new steady state under the fault, and the
   recovery when the fault is removed. The four-phase record is what makes the post-mortem
   specific rather than anecdotal.
8. **Run a same-day debrief with findings recorded as actionable items.** The debrief
   produces a list of findings, each tagged with severity and an owner. Findings that are not
   owned are re-classified as observations, not actions, and tracked separately.
9. **Follow through before the next game day.** Each finding has a deadline before the next
   event; if the deadline slips, the finding is escalated at the next debrief. Game days that
   produce findings which are never actioned erode the team's trust in the practice.

A representative game day for a checkout service:

- Hypothesis: when the payment gateway returns 5xx for 30 seconds, the checkout service
  retries with exponential backoff and the user-visible error rate increases by no more than
  2 percentage points.
- Steady state: synthetic traffic holds checkout success above 99%.
- Scope: 10% of production traffic to the checkout service, in one region, for five minutes.
- Aborts: any error budget burn exceeding 5% in any minute; any customer-visible message
  that violates the support team's guidelines; any fault that the team cannot remove inside
  sixty seconds.
- Runbook: dashboard link, fault injection command, removal command, escalation contacts.

## Controls

- A game day calendar entry with an owner and an agenda, archived with each debrief.
- An experiment hypothesis and abort criteria committed before the event and referenced during
  it.
- A runbook that is reviewed by the on-call before the event, not during it.
- A findings list with owners and deadlines, tracked until closure.
- A change-management gate that ensures game day traffic scope and tenant scope do not exceed
  what the runbook claims.

## Validation evidence

- A deliberately injected fault that should trigger the documented abort criterion does so
  during a rehearsal, proving the abort is wired and known.
- Findings from prior game days are tracked in the issue tracker; the count of unowned
  findings trends toward zero.
- The on-call's response time during the event is recorded; successive game days show the
  response becoming faster and more confident, not slower.
- A regression introduced between game days is caught at the next event because the
  steady-state hypothesis is specific enough to detect it.

## Failure modes and correction

- *Game day becomes a tool demo.* The team runs a fault, watches the dashboard, and never
  exercises the response. Rebalance: half the time on injection and observation, half on the
  on-call's response and the runbook.
- *Findings accumulate with no owner.* The owner role is missing. Assign one per finding and
  review at each debrief.
- *Blast radius creeps.* The experiment that started on 1% of traffic runs on 10% because
  someone thought "more is better". Scope is set in advance and reduced when in doubt.
- *Abort criteria not rehearsed.* When the abort fires, the team scrambles. Rehearse the
  abort path explicitly during the runbook review.
- *Runbook drifts from reality.* After the event, the runbook is updated with what was
  actually observed, not what was assumed.
- *Steady-state hypothesis too vague.* "The system stays up" is not testable. Refine the
  metric, the population, and the bounds before the event.
- *Chaos tool becomes the goal.* A working chaos tool with no game days is theatre. Calendar
  the next event before the current one ends.

## Limitations

- Game days validate the response to a *single* fault class per event. Real incidents combine
  faults; multi-fault scenarios deserve their own dedicated events.
- A clean game day result is not proof of resilience; it is a single sample. Conclusions about
  resilience require multiple events across traffic shapes and regions.
- Game days exercise the on-call's response under a known fault. The unfamiliar combination
  is harder; pair game days with regular chaos drills where the fault is unknown until the
  event starts.
- Game days cannot validate business decisions: which faults are tolerable, which are not, is
  a product conversation, not a chaos conversation. The findings feed the conversation, the
  game day does not conclude it.
- Game days consume engineering time. Cadence should match the release cadence and the
  resilience-criticality of the system, not a marketing-driven frequency.

## Canonical sources

- Principles of Chaos Engineering, *Principles of Chaos* (steady-state hypothesis, blast
  radius, continuous experimentation): https://principlesofchaos.org/
- Google SRE, *Release Engineering* chapter of the SRE book (game days as part of the release
  process): https://sre.google/sre-book/release-engineering/
- Cloudflare, *Versions and deployments* (configuration surface where canary-style faults
  are scoped during game days on Cloudflare Workers):
  https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
