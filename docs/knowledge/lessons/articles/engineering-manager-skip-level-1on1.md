# Engineering Manager Skip-Levels and 1-on-1s

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A senior engineer leaves and in the exit interview says "I never
felt my manager understood what I wanted to grow into." 1-on-1s
have devolved into status updates that duplicate standup. Action
items are verbal-only and never followed up. The VP of Engineering
has no signal on team health because skip-level meetings are not
happening — problems only surface when someone quits. An
engineering director is surprised to learn that two teams have
been aware of a critical technical risk for six weeks but assumed
it was being handled at the top.

## Context

1-on-1 meetings are the primary tool for engineering managers to
build trust, surface blockers, give and receive feedback, and
support career growth. The meeting belongs to the report, not
the manager — the direct report drives the agenda. Weekly cadence
is standard for most direct reports. Skip-level meetings (a
manager's manager meeting individually with ICs) serve a distinct
purpose: listening, gauging team and manager health, and building
trust across organizational layers. They surface signal that a
direct manager's presence naturally filters. Both formats require
consistent cadence, psychological safety, and explicit follow-
through to generate value.

## 1-on-1 structure and cadence

```
Recommended cadence:
  → Weekly, 30 minutes (most direct reports)
  → Bi-weekly, 45 minutes (senior / highly autonomous)
  → Never less than bi-weekly

Agenda template (report drives it):
  1. Check-in: how are you doing? any blockers?
  2. Career/growth thread (ongoing across meetings)
  3. Feedback exchange — both directions
  4. Prior action items — explicit review
  5. Open floor — anything on your mind?

Key principle: the engineer owns the agenda. The manager
listens, coaches, and follows through. If the manager
talks more than 40% of the time, the format is inverted.
```

## Action item tracking

```
Use a persistent shared document (Notion, Google Docs,
15Five):
  → Log every action item with owner and due date
  → Review explicitly at the START of the next 1-on-1
  → Never leave action items as verbal-only

Template:
  [ ] Action: [specific commitment]
      Owner:  [manager or report]
      By:     [date]
      Status: [open / done / blocked]

This is the single highest-impact fix for aimless 1-on-1s.
Missing follow-through on committed items teaches the
report that 1-on-1 commitments are performative.
```

## Skip-level meetings

```
Purpose:
  → Listen and gauge team and manager health
  → Detect systemic issues before they become attrition
  → Collect signal the direct manager's presence filters
  → NOT to assign work or redirect priorities

Format:
  → 20–30 minutes, informal (not a performance review)
  → Monthly or bi-monthly per person
  → Tell the direct manager BEFORE reaching out to their
    reports — surprise skip-levels signal distrust

Good opening questions (open-ended, non-leading):
  "What's the most frustrating part of working here?"
  "If you could change one thing about how we work?"
  "Do you feel like you're growing in your role?"
  "What context do you wish you had that you don't?"

What to avoid:
  "Is your manager good?" — creates loyalty conflicts
  and puts the IC in an unfair position.
```

## Psychological safety in skip-levels

```
Why skip-levels surface different signal:
  → ICs may not raise concerns to their direct manager
    for fear of seeming difficult or disloyal.
  → Systemic issues are rarely raised to the person
    who could be seen as part of the system.

Building safety:
  → Explain the purpose before the first meeting:
    "I want to listen. This is not an evaluation."
  → Never share specific IC feedback with their manager
    without first agreeing on confidentiality.
  → Act on systemic patterns — inaction after hearing
    real concerns destroys credibility permanently.

Pattern analysis (not anecdotes):
  Single IC concern    → note it, do not overreact
  Three ICs same theme → systemic issue, act on it
  "Everything is fine" → reserve judgment; takes 2–3
                         meetings before people open up
```

## Career growth conversations

```
Structure (ongoing thread, not one-off):
  "What kind of work energizes you?"
  "Where do you want to be in the next year?"
  "What are you working on outside your comfort zone?"

  Revisit the thread every 4–6 weeks. Connect current
  project work to stated goals explicitly.

Levels framework:
  Map conversations to your engineering ladder. Name the
  gap between current and next level:
  "For Staff Engineer, the ladder asks for cross-team
  influence. Your current project is mostly intra-team.
  Let's find a way to change that."
```

## Anti-patterns

- **Status updates as 1-on-1s** — "what are you working
  on?" is a standup question. It wastes the most valuable
  regular touchpoint a manager has with each report.
- **Frequent cancellation** — signals the meeting is low
  priority; erodes trust faster than almost anything else.
  Reschedule; never cancel without rescheduling.
- **Manager monopolizing the agenda** — the report should
  speak 60%+ of the time. The manager's role is to listen,
  ask questions, and coach.
- **Skip-level as escalation channel** — assigning work
  or redirecting priorities during skip-levels undermines
  the direct manager and confuses the IC.

## Gotchas

- **"Everything is fine" in early skip-levels** — new
  relationships take two to three meetings before people
  open up. Do not conclude health is good from round one.
- **Feedback timing** — SBI feedback delivered weeks after
  the event loses specificity and impact. Aim for same-day
  or same-week delivery.
- **Confidentiality mismatch** — one instance of routing
  sensitive IC feedback to their manager without consent
  prevents honesty in all future skip-levels with that
  person and with others who hear about it.

## Verification

- 1-on-1s held at committed cadence; cancellations result
  in same-week rescheduling.
- Persistent shared document used for agenda and action
  items; action items reviewed at the start of each 1-on-1.
- Skip-level meetings scheduled monthly; direct managers
  notified before skip-level outreach begins.
- Career development thread revisited every 4–6 weeks,
  not annually at review time.
- Systemic patterns from skip-levels actioned within one
  quarter of first identification.

## Related

- `documentation/docs/policies/lessons/engineering-manager-1on1-skip-level-meetings.md`
- `documentation/docs/policies/lessons/blameless-postmortem-incident-review.md`
- `documentation/docs/policies/lessons/on-call-rotation-best-practices.md`
- `documentation/docs/policies/lessons/incident-communication-stakeholder-updates.md`
- `documentation/docs/policies/lessons/focus-time-over-velocity.md`

## Source URLs (verified 2026-08-17)

- Effective Skip-Level Meetings — https://www.em-tools.io/managing-teams/skip-level-meetings
- 1-on-1 Guide for Engineering Managers — https://jellyfish.co/blog/5-ways-engineering-leaders-can-hold-impactful-one-on-one-meetings/
- SBI Feedback Framework — https://www.ccl.org/articles/leading-effectively-articles/closing-the-gap-between-intent-and-impact/
- Sponsorship vs Mentorship in Engineering — https://larahogan.me/blog/what-sponsorship-looks-like/
- Lara Hogan on First 1-on-1s — https://larahogan.me/blog/first-one-on-ones/
