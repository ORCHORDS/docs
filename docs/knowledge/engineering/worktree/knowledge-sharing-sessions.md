# knowledge-sharing-sessions

**Issue:** Expertise is siloed in individuals; when they leave, knowledge leaves with them
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Only one engineer understands the payment service. Another is the sole expert on the data pipeline. When either is on vacation, work stops. When they leave, the team spends months reverse-engineering their work.

## Pattern / Solution
Regular, lightweight knowledge-sharing sessions spread expertise and reduce bus-factor risk.

**Session formats:**

**Lightning talk (15 min)**
- One engineer presents something they built, learned, or researched
- No slides required; live demo or code walkthrough is fine
- Weekly or biweekly cadence
- Recorded and shared in a knowledge wiki

**Deep dive (45–60 min)**
- Scheduled monthly; covers a complex system or concept in depth
- Q&A session follows
- Owner writes a summary doc afterward

**Architecture walkthrough**
- New engineers shadow a senior for a 2-hour walk through a critical service
- Recorded once and reused for future hires

**Lunch & Learn**
- Informal, voluntary, 30–45 min
- External topics welcome (new technologies, conference takeaways, book summaries)

**Running a session checklist:**
- [ ] Topic announced 5 days in advance with a 2-sentence description
- [ ] Recording enabled (for async viewers)
- [ ] Shared notes doc open during the session for live Q&A capture
- [ ] Session link added to team wiki within 24 hours

**Incentives:**
- Presenting counts toward "leadership" criteria on the career ladder
- Monthly "best session" recognition in team all-hands
- Sessions are protected time — no meetings scheduled during the recurring slot

## Gotchas
- Sessions die without a dedicated owner/scheduler — assign one person to the calendar series
- Voluntary attendance leads to low turnout; make the recurring slot a team norm, not optional
- Record every session; async viewers are often the majority in distributed teams

## Related
- `internal-tech-talks.md`
- `documentation-ownership-model.md`
- `engineering-onboarding-template.md`
