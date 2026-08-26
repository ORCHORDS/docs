# post-incident-review-template

**Issue:** Conducting blameless post-incident reviews (PIRs) to extract systemic improvements
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Without structured post-incident reviews, teams repeat the same failures. Blameless PIRs identify systemic gaps and produce actionable improvements rather than scapegoating individuals.

## Pattern / Solution
PIR document template:
```markdown
# Post-Incident Review: [Brief Title]
**Date of Incident:** YYYY-MM-DD
**Incident ID:** INC-####
**Severity:** P1 / P2
**PIR Author:** [Name]
**PIR Date:** YYYY-MM-DD (within 5 business days of incident)
**Participants:** [list names and roles]

## Incident Summary
[2-3 sentences: what happened, what was the user impact, how long it lasted]

**Impact:**
- Duration: X hours Y minutes
- Users affected: ~N (or % of traffic)
- Revenue impact: $XX (if known)
- SLA breach: Yes / No

## Timeline (UTC)
| Time | Event |
|------|-------|
| HH:MM | Alert fired / First detection |
| HH:MM | On-call paged |
| HH:MM | Incident bridge opened |
| HH:MM | Root cause identified |
| HH:MM | Mitigation applied |
| HH:MM | Service restored |
| HH:MM | Incident closed |

## Root Cause Analysis
[Use 5-Whys or fishbone diagram]

**Immediate cause:** [What directly caused the failure]
**Contributing factors:**
1. [Factor 1]
2. [Factor 2]

## What Went Well
- [Detection was fast due to existing alerting]
- [Rollback procedure worked as expected]

## What Could Be Improved
- [Alert threshold was too high — missed early signal]
- [Runbook was outdated]

## Action Items
| Action | Owner | Due Date | Priority |
|--------|-------|----------|----------|
| Lower alert threshold to 1% error rate | @alice | 2026-08-18 | High |
| Update runbook for DB failover | @bob | 2026-08-25 | Medium |
| Add integration test for edge case | @carol | 2026-09-01 | Medium |

## Blameless Principle
This document focuses on systems and processes, not individuals. All participants acted with the information available to them at the time.
```

PIR process:
```markdown
1. Open draft within 24h of incident resolution
2. Gather timeline data from: PagerDuty, Slack, Datadog, git log
3. Schedule 60-minute meeting within 5 business days
4. Facilitate with explicit no-blame framing
5. Publish PIR to shared wiki within 24h of meeting
6. Track action items in JIRA/Linear with owners and due dates
7. Review action item closure at next sprint retrospective
```

## Gotchas
- "Blameless" does not mean "consequence-free" — systemic accountability is still required
- PIRs for P3/P4 incidents can be written async without a meeting to reduce overhead
- Action items without owners and due dates are never completed; assign explicitly
- Publish PIRs to the whole engineering org — transparency builds trust and spreads learning
- Follow up on action items 30 days later — most are abandoned without follow-up

## Related
- `incident-runbook-template.md`
- `mean-time-to-recovery.md`
- `on-call-escalation-policy.md`
- `rollback-runbook.md`
