# draft-pr-readiness-gated-review-2026

**Issue:** Developers open PRs before they're ready, reviewers waste time on unfinished work, and the team can't tell which PRs actually want attention. Meanwhile, the merge queue blocks on a PR that's still a draft. The team has draft PRs, review requests, and merge queues but no shared convention for how they fit together.
**Date:** 2026-08-13
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

The PR board is chaos: 30 open PRs, half are drafts, half are "ready" but have failing CI, and three have requested review from the one senior engineer who is on vacation. Nobody knows which PRs are actually blocked on the author vs. blocked on a reviewer. Merge queues stall because they picked up a draft. The team wastes hours triaging PR state instead of reviewing code.

## The PR lifecycle states

A PR is not binary (open/merged). It has a lifecycle, and each state implies a different action:

```
[Draft] → [Ready for CI] → [Ready for Review] → [Reviewed] → [Merge Queue] → [Merged]
   ↑           |__________________|                 |
   |___ author loops back here if changes requested __|
```

Map each state to tooling:

| State | Tool signal | Who acts next |
|---|---|---|
| **Draft** | GitHub "draft" toggle | Author |
| **Ready for CI** | Draft off, CI runs | CI system |
| **Ready for review** | CI green + "ready for review" label or review requested | Reviewer |
| **Changes requested** | Reviewer's "request changes" | Author |
| **Approved + queued** | Approvals met, added to merge queue | Merge queue / CI |
| **Merged** | Auto or manual merge | — |

If your team conflates these states, reviewers can't tell what to do.

## The readiness contract (what to enforce)

A PR is "ready for review" when ALL of these are true:
1. **Not a draft** (obvious, but often violated).
2. **CI is green** on the latest commit. Reviewing red CI is a waste — the author likely knows it's broken.
3. **Self-reviewed** — the author has read their own diff and fixed the obvious issues. Add a "self-reviewed" checkbox to the PR template.
4. **Description is filled in** — what changed, why, how to test, screenshots for UI. A PR with "wip" in the description is not ready.
5. **Linked to a ticket** — traceability for the reviewer.

Enforce this with a PR template that makes these explicit checkboxes, and a culture where requesting review before these are met is a faux pas, not a shortcut.

## Draft PRs: when and how

**Use draft PRs for:**
- Early design feedback ("is this the right approach?" — reviewers comment on direction, not nitpicks).
- Sharing work-in-progress across a team without triggering review obligations.
- CI dry-runs where you want to see if tests pass before polishing.

**Do NOT use draft PRs as:**
- A dumping ground for abandoned work. A 6-month-old draft is dead code waiting to confuse someone. Close it.
- A substitute for a design doc. If you need feedback on approach, write a doc or RFC — a draft PR forces reviewers into code-level thinking too early.

**Draft + merge queue:** draft PRs cannot enter a merge queue. If your team uses merge queues (GitHub Merge Queue, bors, Mergify), drafts are invisible to the queue. Convert to "ready for review" only when you actually want it queued.

## Review-request etiquette

- **Request from the minimum number of reviewers** needed (usually 1-2). Spamming the whole team diffuses responsibility and nobody reviews (bystander effect).
- **Use CODEOWNERS for automatic requests** — the right team is pinged by path, not by the author guessing.
- **Don't re-request review from someone who already reviewed** unless you've addressed their comments. Re-requesting with no changes is noise and trains reviewers to ignore pings.
- **Set expectations on response time**: e.g., "ready-for-review PRs get a first pass within 4 working hours." Without an SLA, "review please" has no urgency.

## Merge queue integration (the 2026 pattern)

GitHub Merge Queue (and equivalents) serializes merges to keep `main` green:

1. PR is approved and all checks pass.
2. Author clicks "Add to merge queue" (or it's auto-added on approval).
3. The queue rebases/merges the PR onto the latest `main`, re-runs CI on the integrated result, and merges if green.
4. If CI fails on the integrated branch, the PR is kicked out and the author fixes it.

**Readiness gate for the queue:**
- PR must be non-draft.
- PR must have required approvals.
- All required status checks must pass on the PR head (the queue will re-run them on the integrated branch too).
- PR must not have pending "request changes" reviews.

Configure the queue to auto-remove PRs that fail integration CI, so a broken PR doesn't block the rest of the queue.

## Gotchas

- **Draft PRs trigger CI by default on some setups**: this burns CI minutes on work that isn't ready. Configure CI to skip drafts (`if: github.event.pull_request.draft == false`) unless you specifically want draft feedback.
- **"Ready for review" with red CI**: reviewers see the red X and either skip it (wasting the ping) or review broken code (wasting their time). Gate "request review" behind green CI via a GitHub Action that blocks review requests until checks pass.
- **Stale review requests**: a reviewer was requested, went on vacation, and the PR sits for a week. Use "stale PR" bots (e.g., `actions/stale`) to auto-unassign and re-ping after N days, or let the author manually reassign.
- **Merge queue + long-running CI = starvation**: if CI takes 30 minutes and the queue runs serially, 10 queued PRs take 5 hours to merge. Use parallel queue batches (GitHub Merge Queue supports this) or speed up CI so the queue isn't the bottleneck.
- **Converting draft → ready without notifying**: when you flip a draft to ready, the reviewers who were tagged earlier may not get re-pinged on some platforms. Explicitly comment `/ready` or re-request review so it surfaces in their notifications.
- **Merging before review on trivial PRs**: "it's just a typo" skips review and trains the team that review is optional. Either have a fast-path label (`typo`, `docs`) with reduced requirements documented, or review everything. The middle ground (sometimes skip, sometimes enforce) erodes trust in the process.
- **PR templates that nobody reads**: a 20-item checklist becomes visual noise. Keep the readiness checklist to 4-5 items max and make them concrete checkboxes. If the template is ignored, simplify it — don't add more items.

## Related
- `github-merge-queue.md`
- `pr-review-process-2026.md`
- `pr-templates-2026.md`
- `branch-protection-codeowners-2026.md`
- `stacked-prs-workflow-2026.md`
- `ai-assisted-code-review-2026.md`
