# Incident Command and War Room Management

## Symptom

A P0 incident starts. Within 10 minutes, there are 40 people in a Slack
channel, 3 people are typing "what's happening," 2 people are running
different debug commands on the same database, someone is drafting a customer
email, someone else has already sent a different customer email, and the
on-call engineer who first detected the issue is now answering questions
instead of investigating. Two hours later, the incident is still ongoing, no
one person knows the full picture, and the postmortem will reveal that the
resolution was delayed by 45 minutes because three engineers independently
restarted the same service and kept undoing each other's work.

The failure mode is lack of coordination. During a major incident, the
technical problem and the coordination problem are equally hard, and most
teams are only staffed to solve one of them. Without an explicit incident
commander role and a structured war room, the coordination problem eats the
on-call engineer's attention and the technical resolution stalls.

## Common Root Causes

- **No designated incident commander.** Everyone assumes someone else is
  coordinating. The result is emergent, unstructured chaos: the loudest
  voice sets direction, the quietest expert goes unheard, and nobody owns
  the timeline or the comms.
- **The on-call engineer is expected to both fix and coordinate.** These are
  two full-time jobs during a P0. An engineer deep in a database corruption
  investigation cannot also be tracking "who's working on what," deciding
  when to update stakeholders, and managing the flow of volunteers offering
  to help.
- **War room is a free-for-all.** Anyone who sees "P0 in #incidents" jumps
  in. Helpful intent, destructive impact: 40 people typing "what can I do
  to help?" generates noise, not signal. The IC ends up triaging helpers
  instead of triaging the incident.
- **No separation between investigation and comms.** Stakeholder updates,
  customer comms, and engineering discussion all happen in one channel. The
  VP asks for a status update; an engineer posts a stack trace; the comms
  lead drafts a tweet. Each message buries the others. Signal collapses.
- **No shared timeline.** Nobody is recording "at T+15 min, we identified
  the bad deploy; at T+30 min, we began rollback." When the incident is
  over, the postmortem author has to reconstruct the timeline from memory
  and scattered Slack messages — which is lossy and error-prone.
- **Incident command is ad-hoc, not practiced.** The team has never run an
  incident command drill. The first time someone tries to be IC is during a
  real P0, when they're also stressed and uncertain. The role fails because
  it was never rehearsed.

## Gotchas

- **"The most senior engineer should be IC" is wrong.** Incident command is
  a coordination role, not a technical authority role. The best IC is often
  not the deepest expert — it's the person best at structured
  communication, timeline-keeping, and delegating. The deepest expert should
  be investigating, not herding.
- **Voice/Video war rooms without structure degrade fast.** A Zoom call with
  25 people on mute devolves into a text chat with background noise. If you
  use voice, enforce: IC speaks, everyone else is muted unless asked. Or
  skip voice entirely for distributed teams — structured Slack with clear
  threading often works better than chaotic video.
- **"Too many cooks" on the technical fix.** Three engineers independently
  investigate the same hypothesis because nobody is tracking who's doing
  what. The IC must maintain a visible "who is working on what" list and
  actively redirect duplicate efforts. Without this, effort is wasted and
  fixes collide.
- **Comms and investigation must be separated.** The IC or a designated
  comms lead handles all stakeholder/customer communication. Engineers in
  the war room focus only on the technical fix. When an engineer is asked
  "can you update the VP," that's an IC task — the IC either answers or
  delegates to comms, never distracts the investigator.
- **The war room never formally closes.** The incident is "resolved," but
  the channel stays open, people drift away, and the postmortem is never
  scheduled. Or the channel is reused for the next incident, mixing
  timelines. Every incident gets its own channel/room, formally opened and
  formally closed, with the timeline archived.
- **Helpers without context are a net negative.** An engineer from another
  team volunteers, but they don't know the system, the deploy process, or
  the runbook. The IC spends 20 minutes onboarding them. During a P0,
  context ramp-up costs more than the help is worth. Politely decline or
  assign well-scoped tasks ("can you monitor the error rate dashboard and
  report every 5 min") that require no system context.
- **IC burnout is real and invisible.** Being IC for a 6-hour P0 is
  cognitively exhausting. The IC is making decisions, tracking state, and
  managing humans continuously. Without IC rotation for long incidents, the
  IC degrades and starts making bad calls. Hand off the IC role for
  incidents lasting more than 2-4 hours.

## War Room Framework

1. **Declare an IC immediately on P0/P1.** The first person to acknowledge
   the incident is the initial IC. Their first action: announce "I am IC for
   this incident." This can be handed off, but at no point is the IC role
   vacant.
2. **Establish channel structure.**
   - **#incident-XXX**: the war room. Engineers working the fix. Strictly
     technical discussion. IC posts coordination updates here.
   - **#incident-XXX-comms** (or a thread): stakeholder and customer comms.
     Only the IC and comms lead post here. Stakeholders watch this channel.
   - **Timeline doc**: a shared doc (HackMD, Google Doc, Notion) where the
     IC or scribe records every significant event with a timestamp.
3. **IC responsibilities (the role, not the person).**
   - Maintain the "who is doing what" list.
   - Make go/no-go decisions on proposed fixes ("should we roll back?").
   - Approve all external comms before they're sent.
   - Track the timeline.
   - Decide when to escalate and when to declare resolved.
4. **Scribe role for significant incidents.** For P0s, assign a dedicated
   scribe whose only job is to record the timeline. The IC cannot reliably
   both command and document. The scribe produces the raw material for the
   postmortem.
5. **Formal close.** The IC declares "incident resolved," confirms monitoring
  is green for a defined period (e.g., 30 min), schedules the postmortem,
  and archives the channel. The war room is not left open-ended.

## Prevention

- **Pre-assign IC roles.** Maintain a rotation of trained ICs, just like the
  on-call rotation. Not every on-call engineer is suited to be IC — that's
  fine, but someone trained in IC must be reachable for every P0/P1.
- **Practice incident command during game days.** The IC role must be
  rehearsed outside of real incidents. Game days are the venue: assign an
  IC, run the scenario, and debrief specifically on command quality (not
  just technical resolution).
- **Templatize the war room setup.** A bot command (e.g., `/incident open`)
  should create the channels, pin the timeline doc, page the IC, and
  broadcast "incident declared" — in one step. Friction in setup leads to
  ad-hoc alternatives.
- **Train everyone on war room etiquette.** New engineers should know before
  their first incident: IC speaks, others wait to be tasked, comms go
  through the IC, the timeline is sacred. This is onboarding curriculum, not
  implicit knowledge.
- **Debrief the command, not just the incident.** Every postmortem should
  include a section on "how did coordination go": was the IC effective, did
  the channel structure work, was the timeline accurate, did comms flow
  correctly. Incident command is a skill that improves only with feedback.
