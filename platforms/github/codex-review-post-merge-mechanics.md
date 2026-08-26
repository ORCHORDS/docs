# codex-review-post-merge-mechanics

**Issue:** A fleet merges PRs fast and reviewer findings arrive after the merge. Teams assume post-merge review is impossible (the PR is closed) and findings get lost. Observed running Codex as an external reviewer on the example project campaign (9 PRs, one with 7/7 findings fixed post-merge).

**Date:** 2026-08-15
**Repo:** example-org/example-repo (fork example-org/example-repo)
**Author:** ORCHORDS
**Status:** published

## Post-merge review mechanics

1. **`@codex review` works on MERGED PRs.** The comment triggers the review on the closed PR's diff exactly like an open one — the review gate does not require the PR to be open.
2. **Findings surface as PR review comments:** fetch via `gh api repos/{owner}/{repo}/pulls/{n}/comments` (and `/reviews`); they do not always appear in the unified issue timeline.
3. **Fix follow-ups as new PRs** referencing the merged one ("addresses Codex finding on #343") — never force-push new commits into the merged branch.
4. **Re-review is silent by default.** After fixing, re-trigger the review and watch the API for new comments; absence of findings after a re-trigger that previously produced 7 means clean (verify via the API, not the UI timeline).
5. **Evidence in the fix PR:** paste the finding text + the fix + the verification output (test run, log excerpt) so the reviewer can confirm without re-deriving.

## The transient-refusal trap

1. **Usage-limit refusals look like refusals, not errors.** A "cannot review now" response from Codex is almost always a rate/limit window, not a policy block.
2. **Retry later instead of declaring the reviewer dead** — the working pattern was: refusal → wait → re-trigger → review completes normally.
3. **Distinguish the two failure classes:** limit refusals repeat verbatim and clear with time; configuration failures repeat identically forever and mention setup/auth.
4. **Never silently drop review on refusal** — the loop is: trigger, read response, if limited then schedule retry, if config then fix setup.
5. **Batch reviews inside limit windows** — trigger reviews for several PRs together rather than serially exhausting the window.

## Operational loop that worked

1. Merge PR → immediately comment `@codex review`.
2. Poll `pulls/{n}/comments` after the expected latency window.
3. Findings present → fix-PR per finding cluster with evidence.
4. Re-trigger review on the fix-PR; confirm silence via API.
5. Log findings count per PR in the master-issue status comment — the campaign record showed which PRs needed review attention.

## Related

- `codex-review-merge-gate.md`
- `../issues/master-issue-checkoff-followup-protocol.md`
