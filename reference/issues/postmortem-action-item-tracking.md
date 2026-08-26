# Postmortem Action Item Tracking

## Symptom

A P0 incident happens. The team writes a thorough blameless postmortem,
identifies root causes, and creates 8 action items with owners and
deadlines. Three months later, a near-identical incident happens again.
Investigation reveals: 2 of the 8 action items were completed, 3 were
"started" (a PR was opened and stalled), and 3 were never touched. The
postmortem document is pristine; the follow-through is nonexistent.

This is the most common failure mode of postmortem programs: the team
invests heavily in the analysis ceremony and treats the action items as an
afterthought. The postmortem becomes a tombstone — a well-written record of
a failure that was destined to repeat because nobody owned the remediation.

The symptom manifests as "we keep having the same incidents." When you audit
a year of postmortems and find that action items from incident #3 would have
prevented incident #47, you have an action item tracking failure, not an
incident analysis failure.

## Common Root Causes

- **Action items have no owner, only an assignee.** "Assigned to the
  platform team" means nobody owns it. The platform team is 6 engineers with
  a backlog; the action item enters a queue and dies. Action items need a
  single named human owner, not a team.
- **Action items have no deadline, or unrealistic deadlines.** "Fix this
  eventually" = never. "Fix this by Friday" when the fix is a 3-week project
  = missed deadline, loss of accountability. Deadlines must be real and
  achievable, or they train the team that deadlines are suggestions.
- **Action items are tracked in the postmortem doc, not in a work tracker.**
  A bullet list in a Confluence/Notion page is invisible to the team's
  actual workflow. Nobody opens the postmortem doc to check "what do I owe
  from Q1." Action items must live in Jira/Linear/GitHub Issues — wherever
  the team already works.
- **No regular review of open action items.** Action items are created in
  the postmortem meeting and never reviewed again until the next incident
  reveals they weren't done. Without a recurring review cadence (weekly or
  biweekly), stale items accumulate silently.
- **Action items are too vague to be actionable.** "Improve database
  resilience" is an aspiration, not an action item. "Add automated failover
  testing to the staging CI pipeline by [date], owned by [person]" is an
  action item. Vague items cannot be completed because completion is
  undefined.
- **No consequence for non-completion.** If an action item deadline passes
  with no action and no discussion, the message is "action items are
  optional." The team learns this within one cycle and stops treating them
  seriously.
- **Postmortem is treated as complete when the doc is written.** The
  postmortem meeting ends, the doc is merged, the incident is "closed." But
  the postmortem's purpose — preventing recurrence — is only achieved when
  the action items are done. Closing the incident before remediation is a
  process error.

## Gotchas

- **"We'll track them in the postmortem doc" is the #1 failure pattern.**
  The doc is a record, not a tracker. It is not in the team's daily workflow.
  Action items in a doc are invisible within 2 weeks. Always sync action
  items to the issue tracker at the moment of creation, with the postmortem
  doc linking to them.
- **Too many action items means none get done.** A postmortem that generates
  20 action items is aspirational, not practical. The team will complete
  the easy ones and defer the hard ones forever. Ruthlessly prioritize: what
  are the 2-3 items that would actually prevent recurrence? Do those first.
  Track the rest as "future work," not as action items with deadlines.
- **"Preventative" action items are untestable and get deprioritized.**
  "Add monitoring so this doesn't happen again" feels done when the dashboard
  ships, but was the dashboard actually wired to page someone? Define action
  items with a verifiable outcome: "alert X fires and pages on-call when
  condition Y occurs" (testable) vs "improve monitoring" (untestable).
- **Action items that require cross-team coordination stall forever.**
  "The frontend team needs to add retry logic" depends on a team that didn't
  attend the postmortem and doesn't share your priority. Cross-team action
  items need an explicit owner on *your* side who is accountable for driving
  the cross-team coordination, not just "assigned to frontend."
- **"We'll do it in the next quarter" is a quiet death.** Reprioritizing
  action items into the next sprint, then the next, then the next, until
  they're a year old and the incident has been forgotten. If an action item
  can't be completed in the current quarter, be honest: either cut it, or
  escalate it as a risk ("we are choosing to accept the risk of this
  recurring because the fix is not prioritized").
- **Reopening "closed" incidents.** When an action item is finally completed
  months later, nobody updates the postmortem or marks the risk as mitigated.
  The postmortem doc still lists the item as "open," creating confusion about
  what's actually been addressed. Close the loop: update the postmortem when
  action items complete.
- **Gamifying "action items completed" leads to gaming.** If you measure
  success by "action items closed," engineers will create trivial action
  items ("update the postmortem template") and close them to hit targets.
  Measure recurrence rate instead: are we having the same incidents less
  often?

## Tracking Workflow

1. **Create action items in the issue tracker during the postmortem.** Not
   after. Each item gets: a single human owner, a deadline, a link to the
   postmortem doc, and a clear acceptance criterion ("done when X is true").
2. **Tag action items with the incident ID and severity.** This enables
   reporting: "show me all open P0 action items," "show me action items
   older than 90 days," "show me action items from the payment service."
3. **Review open action items in a recurring meeting.** Biweekly minimum.
   Walk the list: what's blocked, what's overdue, what needs re-scoping.
   This meeting exists because without it, action items rot.
4. **Escalate overdue P0/P1 action items to leadership.** If a remediation
   for a P0 incident is overdue, that is a risk acceptance decision — and
   risk acceptance is a leadership decision, not an engineer's default.
5. **Audit recurrence quarterly.** Pull the last 4 quarters of incidents.
   For each, check: were the action items from the *previous* similar
   incident completed? If not, the tracking system is failing, not the
   analysis.

## Prevention

- **Set a maximum of 5 action items per postmortem.** Force prioritization.
  If you have 10 ideas, pick the 5 with the highest impact-to-effort ratio.
  Track the other 5 in a "future improvements" backlog without deadlines.
- **Enforce the SMART criteria for action items.** Specific, Measurable,
  Achievable, Relevant, Time-bound. "Improve observability" fails all five.
  "Add a dashboard for checkout error rate, wired to page on-call when
  error rate exceeds 0.5% for 5 min, owned by Jane, due Oct 15" passes.
- **Make action item completion a team metric, not an individual one.**
  Individual action item metrics create perverse incentives (close easy
  items, avoid hard ones). Team-level "open P0 action items older than 60
  days" is a healthier signal.
- **Treat the postmortem as open until critical action items are done.**
  The incident is "resolved" when the immediate failure is fixed. The
  postmortem is "closed" only when the preventative action items are
  completed (or explicitly risk-accepted with leadership sign-off). Don't
  conflate the two.
- **Link action items to the service catalog.** When a service undergoes
  changes, check whether it has open postmortem action items. This prevents
  the "we rewrote this service but didn't apply the lessons from last
  year's incident" failure.
