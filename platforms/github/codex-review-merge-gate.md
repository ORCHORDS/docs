# codex-review-merge-gate

**Issue:** Using GitHub Codex as a PR review gate — minimum comments, conversation resolution
**Date:** 2026-08-11
**Status:** documented

## Symptom

PRs are being merged before AI review completes. Codex comments are left unresolved.
The review loop provides no value if PRs merge before feedback is addressed.

## The gate policy

### Minimum comment threshold

Do not merge a PR until Codex has posted a minimum number of review comments.
Rationale: a low comment count often means Codex skipped the review (queue delay, auth error).

| PR size | Minimum Codex comments |
|---------|------------------------|
| Small (1-5 files, < 200 lines) | 3-5 |
| Medium (6-20 files) | 8-12 |
| Large (20+ files, multi-feature) | 15+ |

### Conversation resolution

Every Codex conversation thread must be resolved before merging:
1. **Reply first**: Post a substantive reply to each comment (accepted / won't fix + reason / already fixed in commit X)
2. **Resolve**: Mark the conversation resolved after replying
3. **Don't just resolve**: A resolve without a reply is ignored — Codex tracks reply-then-resolve

### Workflow

```
Push branch
  ↓
Open PR (draft OK)
  ↓
Wait for Codex to complete review
  ↓
Read each Codex comment
  ↓
For each comment:
  - If valid: fix in new commit, reply "Fixed in <commit>"
  - If won't fix: reply with reason, then resolve
  - If already covered: reply pointing to existing code/commit
  ↓
Resolve all conversations
  ↓
Verify CI passes
  ↓
Merge
```

## Common mistakes

### Merging before Codex finishes

Codex review is asynchronous. After opening a PR, wait for the bot to complete (usually < 5 min).
If no comments appear after 10 min, check the Codex app status or re-request review.

### Resolving without replying

GitHub lets you resolve conversations without replying. Don't do this on Codex reviews —
the unacknowledged comment is treated as an accepted issue by the audit trail.

### Ignoring architectural comments

Codex often posts comments on:
- Missing error handling
- Auth bypass potential
- Tenant isolation gaps in SQL queries
- Incorrect type casts (`as any`)

These are higher priority than style comments. Address them or explicitly defer with a filed issue.

### Re-requesting review on force-push

If you force-push after Codex reviews, request a fresh review. The old comments may refer to
stale line numbers.

## Integration pattern (GitHub Actions)

If you want to enforce Codex review as a branch protection requirement, add a status check:

```yaml
# .github/workflows/codex-gate.yml
name: Codex gate
on:
  pull_request_review:
    types: [submitted]

jobs:
  check-codex:
    runs-on: ubuntu-latest
    steps:
      - name: Check Codex review submitted
        if: github.event.review.user.login == 'github-codex[bot]'
        run: echo "Codex review received"
```

Add `"Codex gate"` to required status checks in branch protection.

## Gotchas

- **Codex vs GitHub Copilot**: Codex (github.com/apps/github-codex) is the AI code review bot; Copilot is the inline suggestion tool. They're separate. This entry is about the code review bot.
- **Queue delays**: On busy repos, Codex may take 5-15 min. Don't merge within that window.
- **Codex vs human review**: Codex review supplements, doesn't replace, human CODEOWNERS review.
- **Batch PRs**: On a large feature branch with many PRs, request Codex review for each individually — it doesn't cascade across PR chains automatically.

## Related

- `branch-protection-codeowners-2026.md`
- `code-review-best-practices.md`
- `pr-review-process-2026.md`
- `codex-connector-integration.md`
