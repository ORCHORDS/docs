# feature-cookbook-code-review

**Issue:** Code review — process, checklist, etiquette
**Date:** 2026-08-09
**Status:** documented

## Symptom
You open a PR. Three days pass. No review. You ping.
The reviewer says "I'll get to it." Another day passes.
The PR is stale. You wish you had a process.

## Root cause
**Without a code review process, PRs rot.** Use a
structured process.

**Source:** Google — Code Review Developer Guide:
https://google.github.io/eng-practices/review/

## The "PR template" pattern

For a PR template:
```markdown
## What
<One-line summary>

## Why
<Why is this change needed?>

## How
<How is it implemented?>

## Testing
- [ ] Unit tests
- [ ] Integration tests
- [ ] Manual test

## Risk
<What could break?>

## Rollout
<How is it rolled out?>

## References
- Related issue: #
- Design doc: <link>
```

The template is consistent.

## The "PR size" pattern

For PR size:
- **Small:** < 200 lines
- **Medium:** 200-500 lines
- **Large:** 500+ lines
- **Avoid:** 1000+ lines

Small PRs are reviewed faster and more thoroughly.

## The "review SLA" pattern

For SLAs:
- **First response:** 4 hours during work hours
- **Review complete:** 1 business day
- **Critical PRs:** Same day

The SLA is documented.

## The "reviewer count" pattern

For reviewers:
- **1 reviewer:** Standard
- **2 reviewers:** High-risk change
- **3+ reviewers:** Rare, contentious

For most PRs, **1 reviewer + author** is enough.

## The "code review checklist" pattern

For a checklist:
- [ ] **Correct:** Does it do what it should?
- [ ] **Tests:** Are there tests?
- [ ] **Style:** Does it follow the style guide?
- [ ] **Naming:** Are names clear?
- [ ] **Error handling:** Are errors handled?
- [ ] **Performance:** Is it fast?
- [ ] **Security:** Is it secure?
- [ ] **Documentation:** Is it documented?
- [ ] **Backwards compat:** Is it compatible?
- [ ] **Migration:** Is migration needed?

The checklist is comprehensive.

## The "blocking vs non-blocking" pattern

For comments:
- **Blocking:** Must address before merge
- **Non-blocking:** Nice to address; not required
- **Question:** Need clarification
- **Praise:** Looks good

```ts
// ❌ Vague
// This is wrong

// ✅ Blocking, specific
// This call to `getUser` should be paginated. Right now
// it returns all users, which is O(n) memory + transfer.
// Add `limit` + `offset`.

// ✅ Non-blocking
// nit: consider extracting this to a helper for reuse
```

The comment type is clear.

## The "review tone" pattern

For tone:
- **Kind:** "Could we..." not "You should..."
- **Specific:** Point to the line
- **Helpful:** Suggest a fix
- **Open:** "What do you think?"

```markdown
// ❌ Harsh
// This is bad. Fix it.

// ✅ Kind, specific
// I wonder if we could use a Map here instead of an object?
// That way `users.has(id)` is O(1) instead of `users[id]`
// which is also O(1) but cleaner. What do you think?
```

The tone is kind + constructive.

## The "LGTM" pattern

For LGTM (Looks Good To Me):
- **LGTM:** Approve + ready to merge
- **LGTM with comments:** Approve + minor fixes
- **Request changes:** Needs work before merge
- **Comment only:** Discussion, not approval

The status is clear.

## The "auto-merge" pattern

For auto-merge on CI:
```yaml
# GitHub
- branch-protection:
    required_status_checks: { ci: "success" }
    required_approving_review_count: 1
```

The PR is auto-merged when CI is green + 1 approval.

## The "review on own time" pattern

For async review:
- **Block 1-2 hours:** For code review
- **Review queue:** Triage
- **PRs oldest first:** Or by priority

The review time is protected.

## The "review of own code" pattern

For self-review:
1. **Read your own PR:** Like a reviewer would
2. **Run the tests:** Locally
3. **Test manually:** Click through
4. **Check the diff:** Anything missing?
5. **Add comments:** For complex parts

Self-review catches issues before review.

## The "code review anti-pattern" anti-patterns

### 1. No review
- **Issue:** Bugs ship
- **Fix:** Always review

### 2. Rubber-stamp
- **Issue:** No real review
- **Fix:** Genuine engagement

### 3. Bikeshedding
- **Issue:** Discussion on style instead of correctness
- **Fix:** Focus on correctness first

### 4. Big PR
- **Issue:** Too much to review
- **Fix:** Small PRs (< 500 lines)

### 5. Slow review
- **Issue:** PRs rot
- **Fix:** Same-day review

### 6. Harsh tone
- **Issue:** People stop asking for review
- **Fix:** Be kind

### 7. No checklist
- **Issue:** Inconsistent review
- **Fix:** Use a checklist

## The "approval" pattern

For approvals:
- **Approval:** LGTM, ready to merge
- **Conditional:** LGTM if X is fixed
- **Request changes:** Needs work
- **Comment:** Discussion, not approval

The approval is documented.

## The "PR description" pattern

For a good PR description:
```markdown
# Add user preferences

## What
Allow users to set their preferences (theme, language,
notifications).

## Why
Users have asked for this; it's the #1 feature request
in the last 30 days.

## How
- Add a `preferences` column to the users table
- Add a `GET /api/path/to/preferences` endpoint
- Add a `PUT /api/path/to/preferences` endpoint
- Add a UI in the settings page

## Testing
- Unit tests for the preferences helpers
- Integration tests for the endpoints
- Manual test: change preferences, refresh, verify

## Risk
Low. New feature, doesn't change existing behavior.

## Rollout
- 1% canary for 1 day
- 10% for 1 day
- 100% if no issues

## References
- Issue #<number>
- Design doc: <link>
```

The description is complete.

## Verification
- **Test:** PRs are reviewed
- **Test:** Review SLA is met
- **Live:** Review time is monitored
- **Audit:** Quarterly review process review

## Gotchas
- **The "no review" anti-pattern.** Always review.
- **The "rubber-stamp" anti-pattern.** Genuine
  engagement.
- **The "big PR" anti-pattern.** Small PRs.
- **The "harsh tone" anti-pattern.** Be kind.

## Related
- `feature-cookbook-rfc-process.md`
- `feature-cookbook-testing-strategies.md`
- `feature-cookbook-changelog.md`
- `pr-template-and-issue-templates.md`
- Google eng-practices: https://google.github.io/eng-practices/review/
