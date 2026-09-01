# Blameless Incident Analysis Template

## Scope

This article defines a working template for blameless incident analysis: the structure of the written document, the timeline discipline, the contributing-factors section, the action-item contract, and the facilitation rules that keep the analysis focused on systems rather than individuals. It applies to service outages, data incidents, failed deployments, and security events — any unplanned event with customer impact worth learning from. It does not cover real-time incident command, on-call paging design, or the mechanics of rolling back a bad deploy; those belong to the incident-commander role and the hotfix process.

## Workflow or implementation guidance

Blamelessness is a design constraint on the document and the meeting, not a tone of voice. The working definition: every sentence in the analysis must remain true if you replace each person's name with the role they were performing. "The on-call engineer restarted the worker" is a system fact; "the on-call engineer should have checked the dashboard first" is blame dressed as process. The template enforces the first and forbids the second.

The document has eight sections, in order.

**1. Summary.** Three sentences maximum: what failed, for whom, for how long, and the customer-visible impact in numbers. No causal claims here, because the summary is written last even though it appears first.

**2. Impact.** Duration, affected functionality, request or revenue impact, and the detection method. Record how the incident was discovered — by alerting, by a customer, or by accident. A high fraction of customer-detected incidents is itself a finding.

**3. Timeline.** UTC timestamps from first triggering event to full resolution, each line with one fact: what happened, who observed it, what action followed. Build this from system records — deploy logs, alert history, ticket updates — before the meeting, not from memory during it. Mark the gap between impact start and detection prominently; that gap is usually the cheapest thing to fix.

**4. Contributing factors.** At least three. Single-cause incidents are almost always under-analyzed. Organize by the layers that had to line up: the code change, the missing test, the alert that was too quiet, the runbook that was out of date, the deadline pressure that skipped the review. For each factor, state what made it possible rather than who touched it last.

**5. What went well.** Two to five items. This is not politeness; it identifies the recovery mechanisms worth preserving and gives the team a reason to keep writing these documents.

**6. What went poorly.** Failures of the system: detection, communication, tooling, process. If an item names a person's decision, rewrite it as the condition that made the decision reasonable at the time.

**7. Action items.** Each has an owner (a person, not a team), a due date, and a priority tier. Tier 1 items prevent recurrence of this exact incident and are due within two weeks. Tier 2 items reduce the class of incidents and are due within a quarter. Tier 3 items are improvements with no direct recurrence link and belong in normal planning. An action item without a named owner is a wish, and wishes do not close incidents.

**8. Lessons and open questions.** What the team now believes, and what remains uncertain. Explicitly recording uncertainty prevents the document from being cited later as proving more than it did.

Facilitation rules for the analysis meeting: hold it within five business days while recollection and logs are fresh; cap it at sixty minutes with the timeline pre-built; the facilitator is not the incident commander, so the person who ran the response can participate without also running the meeting; and any conversation that drifts toward "why did X do Y" gets redirected to "what information did X have at that moment." If the redirect fails twice, the facilitator ends the discussion of that thread and records it as an open question.

Publication matters. Publish internally by default, including the parts that are unflattering to the tooling. Restricted distributions get copied into slide decks, stripped of the useful detail, and learned from by nobody. The audience is the engineer six months from now debugging the same subsystem at two in the morning.

Review the action items at the two-week and one-quarter marks. An analysis whose Tier 1 items are not done after a quarter is a strong predictor that the next incident will rhyme with this one, and that pattern is worth naming in the next document's contributing factors.

## Controls

- The template is stored as a repository file so every analysis starts from the same structure.
- Timeline entries must cite a source record: a log line, an alert, a deploy event, or a timestamped message.
- A named human owner is mandatory on every action item; team-name owners are rejected in review.
- Action items are tracked in the team's normal issue tracker with due dates, not in the document alone.
- The blamelessness test — names replaced by roles — is applied by the reviewer before publication.
- Scheduled action-item checks at two weeks and one quarter, with overdue Tier 1 items escalated to the engineering manager.

## Validation evidence

A blameless analysis program is validated by its outputs over time, not by any single document. Check the following:

- For each published analysis, verify mechanically that every action item has an owner and a due date, and that Tier 1 items reference a specific contributing factor rather than a general aspiration.
- At the two-week checkpoint, confirm Tier 1 items are closed or re-scoped with a written reason. At the quarter checkpoint, compute the closure rate for all tiers.
- Re-read incidents from the prior two quarters and check whether any later incident repeats a documented contributing factor whose action item was left open. Repeat-cause incidents with unclosed items are the clearest evidence the process is decorative.
- Sample the timelines for evidence quality: a majority of entries sourced from machine records rather than memory indicates the pre-build step is actually happening.
- Watch participation: if the same one or two people write every document, the practice has concentrated instead of spread, and knowledge is not compounding across the team.

## Failure modes and correction

- **RCA theater.** The document is written, published, and never revisited; action items rot. Correction: the two-week checkpoint is non-optional, and overdue Tier 1 items appear on the engineering manager's weekly list.
- **Blame laundering.** Phrases like "human error" or "miscommunication" appear as contributing factors. Correction: rewrite each as the missing system affordance — no guardrail, no test, no alert, no runbook entry.
- **Single-cause narratives.** The analysis names one bug and stops. Correction: require at least three contributing factors before the document leaves draft, and treat the inability to find three as under-analysis.
- **Evergreen meetings.** The session runs long, memory fills the timeline, and recollections conflict. Correction: timeline pre-built from records, sixty-minute cap, open questions recorded instead of resolved in the room.
- **Vague actions.** "Improve monitoring" with a team owner. Correction: reject in review; require the specific alert, dashboard, or test with a person and a date.

## Limitations

Blamelessness works when leadership genuinely absorbs accountability; if the document is quietly used in performance evaluation even once, candor ends and no template fixes it. The template assumes the team has reasonably complete logs and alerting records to build the timeline — without them, the timeline becomes memory-driven and its accuracy ceiling drops sharply. The eight-section structure suits single-team incidents; multi-team or org-wide events need an additional coordination section this template does not provide. The tier deadlines are pragmatic defaults, not regulatory requirements, and teams under compliance regimes may need longer formal sign-off chains. Finally, this analysis is backward-looking by design; it explains what happened, it does not by itself predict the next failure class.

## Canonical sources

- DORA — Research on delivery performance and incident learning culture: https://dora.dev/research/
- DORA — The four keys metrics (including change failure rate and time to restore): https://dora.dev/guides/dora-metrics-four-keys/
- Git documentation — git-revert for safe change rollback referenced in timelines: https://git-scm.com/docs/git-revert
