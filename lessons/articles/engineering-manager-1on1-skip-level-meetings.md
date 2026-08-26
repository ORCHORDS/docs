# Engineering Manager 1:1 and Skip-Level Meetings

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your engineering team's 1:1 meetings have devolved into status updates
that duplicate standup. Engineers say they don't get career development
conversations. Action items from 1:1s are verbal-only and never
followed up. A senior engineer leaves and in the exit interview says
"I never felt my manager understood what I wanted to grow into."
Meanwhile, the VP of Engineering has no signal on team health because
skip-level meetings aren't happening — problems only surface when
someone quits.

## Context

One-on-one meetings are the primary tool for engineering managers to
build trust, give and receive feedback, unblock career growth, and
detect team health issues early. The meeting belongs to the engineer,
not the manager — the report drives the agenda. Weekly cadence is
standard for most direct reports; bi-weekly can work for very senior,
highly autonomous engineers. Skip-level meetings (a manager's manager
meeting with individual contributors) serve a different purpose:
listening, gauging team and manager health, and building trust across
organizational layers. Effective 1:1s require persistent shared
documents for agenda and action items, explicit feedback frameworks,
and consistent follow-through.

## 1:1 meeting structure

```
Recommended cadence:
  → Weekly, 30 minutes (most reports)
  → Bi-weekly, 45 minutes (senior/autonomous engineers)
  → Never less than bi-weekly

Manager prep (5 minutes before):
  1. Review shared notes from last 1:1
  2. Check committed follow-ups / action items
  3. Reflect on recent work, PRs, incidents
  4. Note any feedback to deliver
```

```
Agenda template (report-driven):

  1. How are you doing? (personal check-in, blockers)
  2. Career / growth topic (ongoing thread)
  3. Feedback exchange (both directions)
  4. Review prior action items (accountability)
  5. Anything else on your mind (open floor)

  Key principle: the engineer owns the agenda.
  The manager's job is to listen, coach, and follow up.
```

```
Action item tracking:

  → Use a shared, persistent doc (Notion, Google Docs, 15Five)
  → Log action items with owner and due date
  → Revisit explicitly at the START of the next 1:1
  → This is the single most-cited fix for aimless 1:1s

  Anti-pattern: verbal-only action items that are forgotten
  by the next meeting. Written persistence is non-negotiable.
```

## Feedback frameworks

```
SBI — Situation, Behavior, Impact
  (Center for Creative Leadership)

  Structure:
    "In [situation], when you [behavior], it [impact]."

  Example:
    "In yesterday's design review, when you interrupted
    the junior engineer twice, it made them hesitant to
    share ideas for the rest of the meeting."

  Best for: quick, in-the-moment corrective or reinforcing
  feedback. Neutral and factual to reduce defensiveness.
```

```
COIN — Context, Observation, Impact, Next steps

  Structure:
    Context:     Set the scene
    Observation: Describe specific behavior observed
    Impact:      Explain the effect
    Next steps:  Agree on what changes going forward

  Example:
    Context:     "Over the last three sprints..."
    Observation: "I've noticed PRs sitting unreviewed for 2+ days"
    Impact:      "The team's velocity dropped and two features
                  missed their release window"
    Next steps:  "Let's set a 24-hour review SLA and track it"

  Best for: recurring or complex behavioral issues where
  a forward-looking action plan is needed. Adds the "what
  next" step that SBI lacks.
```

## Skip-level meetings

```
Purpose:
  → Listen and gauge team/manager health
  → Build trust and access to senior leadership
  → Detect systemic issues before they become attrition
  → NOT for solving problems or giving direction

Format:
  → 20-30 minutes, informal (not a review)
  → Monthly or bi-monthly per person
  → Tell the direct manager BEFORE reaching out
    (surprise skip-levels erode manager trust)

Good questions (open-ended):
  "What's the most frustrating part of working on your team?"
  "What one thing would you change about how we work?"
  "Do you feel like you're growing here?"
  "What context do you wish you had that you don't?"

  Avoid: "Is your manager good?" framing — it creates
  loyalty conflicts and puts the IC in an unfair position.
```

```
Skip-level signals to watch for:

  Pattern across multiple ICs    → Systemic issue, act on it
  Single IC complaint            → Note it, don't overreact
  "Everything is fine" from all  → Either great or nobody trusts
                                   the format yet
  Consistent "I don't know       → Information flow problem
  why we're doing X"               between layers
```

## Remote and hybrid considerations

```
Remote 1:1 adjustments:
  → Camera-on by default (builds connection)
  → Written action items even more critical
    (no hallway follow-ups to compensate)
  → Explicit check-in on isolation / burnout
  → Async pre-fill of agenda before the meeting
  → Consistency matters more than medium —
    don't cancel remote 1:1s more readily than in-person
```

## Anti-patterns

- **Turning 1:1s into status updates** — status belongs in
  standups and async tools. 1:1s that are just "what are you
  working on?" waste the most valuable manager-report touchpoint.
- **Frequent cancellation** — signals the meeting is low priority
  and erodes trust faster than almost anything else. Reschedule,
  don't cancel.
- **Manager monopolizing the agenda** — the manager talks 80% of
  the time, delivering directives. The report should talk 70%+.
  Manager's role is to listen, ask questions, and coach.
- **Never following up on action items** — committing to help
  with something and then not doing it teaches the report that
  1:1 commitments are performative.
- **Skip-level as escalation channel** — using skip-levels to
  bypass the direct manager's authority, assign work, or redirect
  priorities undermines the management chain.
- **Blindly forwarding skip-level feedback** — sharing sensitive
  IC feedback with their manager without discussing
  confidentiality first breaks trust permanently.

## Gotchas

- **"Everything is fine" syndrome** — new skip-level relationships
  take 2-3 meetings before people open up. Don't conclude health
  is good from the first round of meetings.
- **Career conversations need continuity** — a one-off "where do
  you want to be in 5 years" question without follow-up is worse
  than not asking. Maintain a running career development thread
  across 1:1s.
- **Feedback timing matters** — SBI feedback delivered weeks after
  the incident loses specificity and impact. Aim for same-day or
  same-week delivery.
- **Skip-level patterns vs anecdotes** — act on patterns raised
  by multiple ICs, not single data points. One person's complaint
  about a process is an anecdote; three people saying the same
  thing is a signal.

## Verification

- 1:1s scheduled weekly with all direct reports.
- Shared persistent doc used for agenda and action items.
- Action items reviewed at the start of each 1:1.
- Feedback delivered using SBI or COIN framework.
- Skip-level meetings scheduled monthly with skip reports.
- Direct managers informed before skip-level outreach.
- Career development thread maintained across 1:1s.

## Related

- `documentation/categories/lessons/blameless-postmortems-learning-reviews.md`
- `documentation/categories/lessons/on-call-handoff-rotation-practices.md`
- `documentation/categories/lessons/incident-communication-stakeholder-updates.md`

## Source URLs (verified 2026-08-16)

- Effective One-on-Ones for Engineering Managers — https://www.em-tools.io/managing-teams/one-on-one-meetings
- Skip-Level Meetings: How to Run Them Effectively — https://www.em-tools.io/managing-teams/skip-level-meetings
- SBI vs COIN vs STAR: Feedback Frameworks for Managers — https://rahulgoyal.co/justdraft/feedback-frameworks-sbi-coin-star-methods/
- Impactful One-on-One Meetings for Engineering Leaders — https://jellyfish.co/blog/5-ways-engineering-leaders-can-hold-impactful-one-on-one-meetings/
