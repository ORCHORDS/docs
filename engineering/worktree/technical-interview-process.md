# technical-interview-process

**Issue:** Interviews are inconsistent across interviewers, creating unfair outcomes and poor signal on candidates
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Two interviewers submit opposite verdicts on the same candidate. One asks whiteboard sorting algorithms; another asks about their favorite design pattern. Hiring decisions are driven by gut feeling. Strong candidates are rejected because one interviewer had a bad day.

## Pattern / Solution
A structured interview process with defined competencies, consistent questions, and a scoring rubric.

**Interview loop structure (example for L2–L3 backend role):**
| Round | Format | Duration | Competency |
|-------|--------|----------|-----------|
| 1 | Recruiter screen | 30 min | Motivation, logistics |
| 2 | Technical screen | 45 min | Coding fundamentals |
| 3 | System design | 60 min | Architecture, trade-offs |
| 4 | Code review / debugging | 45 min | Code quality, communication |
| 5 | Values / collaboration | 45 min | Teamwork, feedback culture |
| 6 | Hiring manager | 30 min | Goals, expectations |

**Scoring rubric (per competency):**
```
4 — Exceptional: Exceeded expectations; would be rare in our hiring pool
3 — Strong hire: Clear signal; would succeed in this role
2 — Mixed: Some positives but notable gaps; risky hire at this level
1 — No hire: Did not meet minimum bar for this competency
```

**Interview question bank:**
- Maintain a shared, leveled question bank (not shared externally)
- Questions tagged by competency and difficulty
- Rotate questions every 6 months to prevent leak risk
- Each interviewer uses the same question(s) for all candidates at the same level

**Debrief process:**
1. Each interviewer submits a written scorecard before the debrief call
2. Interviewers read scorecards; then discuss divergent assessments
3. Hiring manager makes the final call; does not vote in the debrief

## Gotchas
- Calibration sessions (mock interviews among interviewers) reduce scoring variance dramatically
- "Culture fit" is a bias vector — replace it with "values alignment" with specific examples
- Candidates with non-traditional backgrounds may need different question formats, not lower standards

## Related
- `take-home-assignment-design.md`
- `career-ladder-engineering.md`
- `feedback-giving-sbi-model.md`
