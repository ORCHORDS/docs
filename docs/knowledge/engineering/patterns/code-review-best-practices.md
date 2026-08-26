# code-review-best-practices

**Issue:** Effective code review — what to look for, how to give feedback
**Date:** 2026-08-09
**Status:** documented

## Symptom
A PR is opened. The reviewer skims. The PR is approved in
5 minutes. The code ships. It has bugs. The team discovers
the bugs in production.

## Root cause
**A bad review is worse than no review.** It gives the
illusion of safety. The bugs are still there.

**Source:** Google Engineering Practices:
https://google.github.io/eng-practices/review/

> "Code review is the process of examining code changes to
> ensure they meet standards of quality, correctness, and
> maintainability."

## The 5 review goals

A code review should check:
1. **Correctness** — does the code do what it claims?
2. **Design** — is this the right approach?
3. **Readability** — can a new dev understand it?
4. **Security** — are there security issues?
5. **Tests** — are the tests adequate?

## The 5 anti-patterns of code review

### 1. "LGTM" with no comments
- **Symptom:** Reviewer approves in 30 seconds with no
  feedback
- **Cause:** Time pressure, social pressure, laziness
- **Fix:** Require reviewers to leave ≥1 comment

### 2. Nitpicking
- **Symptom:** Reviewer comments on style ("rename this
  variable"), formatting, indentation
- **Cause:** Easier than reviewing the logic
- **Fix:** Use a linter; reserve human review for logic +
  design

### 3. Bikeshedding
- **Symptom:** Reviewer debates naming for 30 minutes
- **Cause:** Subjective; no right answer
- **Fix:** Time-box the review; default to the author's
  choice

### 4. Approval theater
- **Symptom:** PR is approved, then bugs are found in
  production
- **Cause:** Reviewer didn't actually read the code
- **Fix:** Require reviewers to add specific comments

### 5. Reviewer block
- **Symptom:** Reviewer doesn't respond for days
- **Cause:** Workload, lack of prioritization
- **Fix:** Set SLAs (1 business day for first response)

## The 5 review principles

### 1. Review small PRs
- **Why:** A 200-line PR is reviewable; a 2000-line PR is not
- **Goal:** < 400 lines per PR
- **How:** Split large changes into multiple PRs

### 2. Review the design first
- **Why:** Design issues are expensive to fix after
  implementation
- **How:** Open a design doc PR before the code PR; get
  approval; then implement

### 3. Review the test coverage
- **Why:** Tests are the safety net; missing tests = bugs
  in production
- **How:** Require tests for new features; require
  tests for bug fixes

### 4. Review for security
- **Why:** Security bugs are catastrophic
- **How:** Check for OWASP Top 10 (injection, XSS, etc.);
  check for secrets; check for authn/authz

### 5. Be kind + specific
- **Why:** Reviewers are humans; tone matters
- **How:** "What do you think about X?" vs "X is wrong."
  Suggest, don't dictate.

## The review checklist

For every PR, the reviewer should check:

### Correctness
- [ ] Does the code do what the PR description says?
- [ ] Are there edge cases not handled?
- [ ] Are errors handled correctly?
- [ ] Are the types correct?

### Design
- [ ] Is this the right approach?
- [ ] Could it be simpler?
- [ ] Is it consistent with the rest of the codebase?
- [ ] Is the abstraction right?

### Readability
- [ ] Are variable names clear?
- [ ] Are functions small (< 50 lines)?
- [ ] Is the control flow obvious?
- [ ] Are there comments where the intent isn't clear?

### Security
- [ ] Are user inputs validated?
- [ ] Is the data authenticated/authorized?
- [ ] Are there any SQL injection, XSS, or other OWASP issues?
- [ ] Are secrets handled correctly?

### Tests
- [ ] Are new features tested?
- [ ] Are edge cases tested?
- [ ] Are the tests fast (< 1s each)?
- [ ] Are the tests reliable (no flakes)?

### Performance
- [ ] Is the data structure right?
- [ ] Are queries indexed?
- [ ] Are there N+1 queries?
- [ ] Is caching used where appropriate?

## The "good comment" pattern

Comments should be:
- **Specific:** "This handles the empty array case" (not
  "fix this")
- **Constructive:** "What about X?" (not "X is wrong")
- **Question-driven:** "Could we use Y instead?" (not "Use
  Y")
- **Necessary:** Only comment when the code can't speak for
  itself

```ts
// ❌ Bad comment
// This is bad.

// ✅ Good comment
// Cast to unknown first to satisfy TS; the JSON shape is
// guaranteed by the schema in `validate()`.
const user = data as unknown as User;
```

## The "ask vs tell" pattern

The reviewer should ask, not dictate:
```ts
// ❌ Tell
"Use a Map here."
"Add a try-catch."
"This is wrong."

// ✅ Ask
"What do you think about using a Map here?"
"Should we handle the case where this throws?"
"Could you explain the logic here?"
```

The author is the owner; the reviewer is the second pair of
eyes.

## The "approval" criteria

Approve when:
- The code is correct
- The design is sound
- The tests are adequate
- There are no security issues
- The author has addressed the comments

Request changes when:
- There's a critical issue (security, correctness)
- The design is wrong (not just different)
- The tests are missing

Comment without blocking when:
- The code is correct but could be better
- The change is subjective
- A future improvement is suggested

## The "second reviewer" pattern

For high-stakes changes (auth, payments, security), require
a second reviewer:
- The first reviewer is the domain expert
- The second reviewer is a fresh pair of eyes
- Both must approve

For most changes, one reviewer is enough.

## The "automated checks" pattern

Use automation for the mechanical parts:
- **Linter** — style, formatting
- **Typecheck** — type correctness
- **Tests** — correctness
- **Security scan** — known vulnerabilities
- **Coverage** — test coverage

The human reviewer focuses on design, intent, edge cases.

## The "review SLA" pattern

Set a service-level agreement for reviews:
- **First response:** 1 business day
- **Full review:** 2 business days
- **Re-review:** 0.5 business days

A PR that has been waiting for 5 days is a PR that will be
merged without proper review.

## The "review rotation" pattern

For fairness and breadth, rotate reviewers:
- A pool of 5-10 reviewers
- The system assigns a reviewer (or the author picks)
- Track review count per person; balance

A team where 1 person does all reviews is a team with a
single point of failure.

## Verification
- **Live:** Review SLAs are monitored
- **Audit:** Quarterly review of PR cycle time
- **Process:** Annual review of review checklist

## Gotchas
- **The "LGTM" review is dangerous.** It looks like approval
  but is no review at all. Require specific comments.
- **The "perfect is the enemy of good" anti-pattern.** A PR
  that could be 90% better should not block the ship.
  Approve, file a follow-up.
- **The "design by committee" anti-pattern.** The reviewer
  suggests 5 different approaches. The author is confused.
  Suggest one; let the author decide.
- **The "private feedback" anti-pattern.** "Let me Slack the
  author about this." The feedback is lost. Comment on the
  PR; it's the audit trail.
- **The "blame the author" anti-pattern.** "You didn't think
  about X." Focus on the code, not the person.
- **The "approve because of pressure" anti-pattern.** "We
  need this shipped." Approve only when the code is ready.

## Related
- `pr-template-and-issue-templates.md`
- `safe-deploy-checklist.md`
- `lazy-fail-evidence-discipline.md`
- Google: https://google.github.io/eng-practices/review/
- Microsoft: https://learn.microsoft.com/en-us/azure/devops/repos/git/pull-request-guidelines
