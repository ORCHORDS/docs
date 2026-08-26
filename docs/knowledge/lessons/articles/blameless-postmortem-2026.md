# blameless-postmortem-2026

**Issue:** Incident postmortem — blameless template
**Date:** 2026-08-09
**Status:** documented

## Symptom
Production down for 4 hours. Team writes
postmortem. Three months later, same incident
recurs. You realize the postmortem was theater.

## Root cause
**Blameless + systemic + action items.** Three.

**Source:** novaaiops + Atlassian + oneuptime 2026.

## The "blameless" concept

Blameless:
- **Focus:** System, not person
- **Question:** What allowed this?
- **Not:** Who did this?
- **Result:** Real fixes

The postmortem is blameless.

## The "trigger" pattern

For automatic:
- **Threshold:** SEV1 or SEV2
- **Auto:** No judgment call
- **Also:** SLO breach, error budget burn
- **Also:** Repeat incident

The trigger is automatic.

## The "24-48h" pattern

For timing:
- **24h:** Too soon
- **48h:** Too late
- **Sweet spot:** 24-48 hours
- **Schedule:** Before scatter

The time is bounded.

## The "8 sections" pattern

For shape:
1. **Summary:** 2-3 sentences
2. **Impact:** Quantified
3. **Timeline:** Onset to recovery
4. **Root cause:** Systemic
5. **Contributing factors:** Chain
6. **What went well:** Balanced
7. **Action items:** Owned + dated
8. **Lessons learned:** Transferable

The 8 are the shape.

## The "summary" pattern

For summary:
- **What broke:** Plain language
- **For how long:** Duration
- **What fixed it:** Mitigation
- **Length:** 2-3 sentences
- **Read:** By exec in 30 sec

The summary is short.

## The "impact" pattern

For impact:
- **Users:** Number affected
- **Revenue:** Lost
- **Error budget:** Burned
- **Duration:** Mins/hours
- **SLOs:** Breached

The impact is quantified.

## The "timeline" pattern

For timeline:
- **Format:** Timestamped table
- **Columns:** Time, event, info, source
- **Sources:** Logs, alerts, deploys
- **TZ:** Normalized (UTC)
- **Originals:** Preserved

The timeline is factual.

## The "root cause" pattern

For cause:
- **Five whys:** Until systemic
- **Not:** One-liner
- **Not:** Person
- **The chain:** Latent condition

The cause is systemic.

## The "contributing factors" pattern

For factors:
- **Technical:** Architecture
- **Change:** Deployment
- **Observability:** Detection
- **Process:** Documentation
- **Ownership:** Org
- **External:** Environment

The factors are layered.

## The "what went well" pattern

For what worked:
- **Detection:** Found quickly
- **Response:** Effective
- **Tooling:** Useful
- **Decisions:** Sound
- **Lucky:** Spare capacity

The wins are listed.

## The "what didn't" pattern

For what hurt:
- **Detection:** Slow
- **Diagnosis:** Hard
- **Mitigation:** Late
- **Coordination:** Confused
- **Communication:** Gaps

The pains are honest.

## The "action items" pattern

For items:
- **Owner:** One person (not team)
- **Due date:** Concrete
- **Priority:** P0/P1/P2
- **Tracking:** Real backlog
- **Effectiveness:** Checked

The item is owned.

## The "single owner" pattern

For items:
- **Person:** One name
- **Not:** "Backend team"
- **Not:** "TBD"
- **Why:** Accountability
- **Fix:** Named person

The owner is named.

## The "in real backlog" pattern

For tracking:
- **Jira:** Not doc
- **Linear:** Not doc
- **GitHub:** Not doc
- **Cadence:** Reviewed weekly
- **Why:** Not parked

The item is prioritized.

## The "5 whys" pattern

For root:
- **Why 1:** Service failed
- **Why 2:** Bad code path
- **Why 3:** No test
- **Why 4:** No review
- **Why 5:** No checklist

The why is iterative.

## The "validations" pattern

For template:
- [ ] Trigger automatic
- [ ] 24-48h
- [ ] Tone set
- [ ] Timeline factual
- [ ] Language systemic
- [ ] Root + factors
- [ ] What went well
- [ ] Single owner
- [ ] In real backlog
- [ ] Shared openly

The 10 are the validations.

## The "tone set" pattern

For meeting:
- **Open:** "Goal is system"
- **Open:** "No one in trouble"
- **Redirect:** "What info did we have?"
- **Not:** "Why did you do that?"

The tone is set.

## The "language" pattern

For language:
- **Ask:** "What allowed this?"
- **Ask:** "How did system behave?"
- **Not:** "Who did this?"
- **When name surfaces:** Redirect

The language is systemic.

## The "evidence-backed" pattern

For evidence:
- **Timestamp:** From log, not memory
- **Source:** Linked
- **Hindsight:** Labeled separately
- **Confidence:** Stated

The evidence is real.

## The "facts vs inferences" pattern

For separation:
- **Fact:** Timestamp from immutable log
- **Inference:** "Probably X"
- **Unknown:** Labeled
- **Why:** Hindsight bias avoided

The separation is clear.

## The "no single root cause" pattern

For chain:
- **Trigger:** Event
- **Vulnerable condition:** Code
- **Propagation:** How spread
- **Defense missing:** What failed
- **Response:** How handled

The chain is multi-link.

## The "testable action" pattern

For action:
- **Owner:** Person
- **Priority:** P0/P1/P2
- **Due:** Date
- **Done when:** Completion criteria
- **Effective when:** Verification

The action is testable.

## The "privacy" pattern

For privacy:
- **Classify:** Public/Internal/Restricted
- **Redact:** Customer IDs
- **Link:** Restricted evidence
- **Google SRE:** No end-user PII
- **Why:** Legal + trust

The privacy is required.

## The "publish openly" pattern

For share:
- **Repo:** Searchable
- **Audience:** All engineering
- **Format:** Markdown
- **Why:** Cross-team learning

The share is open.

## The "monthly review" pattern

For cadence:
- **Review:** Monthly / biweekly
- **Notable:** Discussed
- **Cross-team:** Open
- **Why:** Pattern recognition

The review is recurring.

## The "no template" anti-pattern

For ad-hoc:
- **Issue:** Different each time
- **Fix:** Single template

The template is shared.

## The "blame culture" anti-pattern

For blame:
- **Issue:** People hide facts
- **Fix:** "What info did we have?"

The culture is blameless.

## The "no action items" anti-pattern

For no items:
- **Issue:** Same incident recurs
- **Fix:** Owned action items

The items are owned.

## The "team-owned action" anti-pattern

For team:
- **Issue:** No accountability
- **Fix:** Named person

The owner is named.

## The "postmortem in doc only" anti-pattern

For doc-only:
- **Issue:** Not prioritized
- **Fix:** Real backlog

The backlog is real.

## The "delayed postmortem" anti-pattern

For delayed:
- **Issue:** Memory fades
- **Fix:** 24-48 hours

The time is bounded.

## The "no trigger" anti-pattern

For judgment:
- **Issue:** Inconsistent
- **Fix:** Automatic threshold

The trigger is set.

## The "no what went well" anti-pattern

For no wins:
- **Issue:** Unbalanced
- **Fix:** List wins

The wins are listed.

## The "C-suite buy-in" pattern

For org:
- **Buy-in:** Leadership
- **Why:** Culture change
- **Risk:** Without it, reverts

The buy-in is required.

## The "postmortem template" pattern

For template:
```markdown
# [Title]
Incident ID:
Date:
Severity:
Status: Draft | In Review | Reviewed | Closed
Owner:
Facilitator:
Commander:

## Executive Summary
[2-3 sentences]

## Impact
- Duration:
- Users affected:
- Error budget:
- SLOs breached:

## Timeline
| Time | Event | Source | Confidence |

## Root Cause
[Systemic, via 5 whys]

## Contributing Factors
- [Tech, change, observability, process, org, external]

## What Went Well

## Action Items
| Action | Owner | Due | Priority |
|--------|-------|-----|----------|

## Lessons Learned
```

The template is fixed.

## The "action item format" pattern

For format:
```
[Action] [Owner] [Due] [Priority]
e.g. "Add retry logic @alice 2026-09-01 P0"
```

The format is structured.

## The "recurrence" pattern

For repeat:
- **Pattern:** Same incident 3+ times
- **Fix:** Architecture, not patches
- **Why:** Patches = symptom

The fix is architectural.

## The "checklist" pattern

For checklist:
- [ ] Trigger automatic
- [ ] 24-48h
- [ ] Tone set
- [ ] Timeline factual
- [ ] Language systemic
- [ ] Root + factors
- [ ] What went well
- [ ] Single owner
- [ ] Real backlog
- [ ] Shared openly
- [ ] Privacy respected
- [ ] Recurrence tracked

The checklist is 12.

## Verification
- **Test:** 24-48h
- **Test:** Blameless language
- **Test:** Action items tracked
- **Test:** No recurrence
- **Audit:** Monthly

## Gotchas
- **The "blame" anti-pattern.** System.
- **The "no owner" anti-pattern.** Named.
- **The "no trigger" anti-pattern.** Auto.

## Related
- `lessons/incident-response-runbook.md`
- `lessons/automated-incident-handling.md`
- `lessons/lazy-fail-discoveries.md`
- `lessons/tech-debt-management-2026.md`
- `patterns/error-budget-slo.md`
- `patterns/incident-response.md`
- novaaiops: https://novaaiops.com/blameless-postmortem
- Atlassian: https://www.atlassian.com/incident-management/postmortem/blameless
- oneuptime: https://oneuptime.com/blog/post/2026-07-30-blameless-postmortem-template/view
