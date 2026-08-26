# take-home-assignment-design

**Issue:** Take-home coding assignments are either too long, too vague, or unfair to candidates with less free time
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A take-home "should take 2 hours" but realistically takes 6–8. Candidates without free time (caregivers, second-job holders) can't compete with those who spend a weekend. Evaluation criteria are unclear and reviewers score inconsistently.

## Pattern / Solution
Design take-homes with explicit time limits, clear evaluation criteria published in advance, and a fair review process.

**Design principles:**
1. **Time-box at 3 hours maximum.** State this clearly and honor it — reviewers should not penalize for incomplete work within the stated limit.
2. **Use realistic, relevant problems.** Avoid toy puzzles; use a simplified version of actual work the team does.
3. **Publish the rubric upfront.** Candidates should know exactly how they'll be evaluated before they start.
4. **Pay for significant time investment.** Anything > 4 hours should include compensation.

**Assignment template:**
```markdown
## Take-Home Assignment: [Role]

**Time limit:** 3 hours (we mean it — stop at 3 hours)
**Submission:** GitHub repo or zip file

### Task
[Clear, scoped problem statement]

### Requirements
- Functional: the program must do X
- Non-functional: consider Y but no need to implement it fully

### What we'll evaluate
- [ ] Correctness: does it do what was asked?
- [ ] Code clarity: is it readable and maintainable?
- [ ] Error handling: are edge cases considered?
- [ ] Testing: are there tests? Do they cover meaningful scenarios?
- [ ] Trade-off communication: what did you cut and why?

### What we won't penalize for
- Incomplete stretch goals
- UI polish (if this is a backend role)
- Unpolished README prose
```

**Review process:**
- Blind review (remove candidate name before sharing with reviewers)
- Two independent reviewers use the rubric before discussing
- Debrief: agree on pass/fail before revealing who reviewed what

## Gotchas
- "We'll send it to a few candidates and pick the best" is a misuse — the bar is absolute, not relative
- Work samples from current employer are not acceptable — require greenfield work
- Offer to conduct the assignment in a live session as an alternative for candidates who prefer it

## Related
- `technical-interview-process.md`
- `career-ladder-engineering.md`
