# GitHub Actions `workflow_run` Trigger Security

The `workflow_run` event fires when a workflow in your repo completes. It is the
go-to mechanism for running privileged jobs (deployments, release publishing,
commenting back on PRs) because unlike `pull_request` it can access secrets even
when the triggering workflow came from a fork. That same privilege is exactly
why it is one of the most abused triggers in the Actions ecosystem.

## Symptom

You see one or more of the following:

- A `workflow_run` job ran with secrets exposed, but the triggering workflow
  YAML was submitted from a brand-new fork with no review.
- Security tooling (CodeQL, GitHub Advanced Security, or a third-party scanner)
  flags your `workflow_run` workflow as "high-risk trigger" or "secret exposure
  via untrusted workflow."
- A dependabot or fork-contributed change to the triggering workflow caused the
  downstream privileged job to behave differently than expected.
- Your deployment ran against a PR that was later closed/force-pushed, because
  `workflow_run` does not automatically re-trigger on upstream changes.
- The `GITHUB_TOKEN` in the `workflow_run` has write scope on the repo even
  though the triggering PR workflow was sandboxed to read-only.

## Why it happens

`workflow_run` executes in the context of the default branch (usually `main`),
not the branch that triggered the upstream workflow. This means:

1. **Secrets are available** — environment and repo secrets are injected as if
   the workflow ran on `main`, regardless of where the PR came from.
2. **The triggering workflow YAML is attacker-controlled** — a fork can submit
   a workflow that runs `on: pull_request`, passes, and then your
   `workflow_run` blindly trusts its outputs/artifacts.
3. **No automatic re-run on upstream change** — if the PR is force-pushed after
   the `workflow_run` fires, the privileged job already ran against stale state.

## Fix

1. **Never trust artifacts from the triggering workflow without validation.**
   If the upstream workflow uploaded build artifacts, verify the commit SHA
   inside the artifact matches the PR head SHA before consuming them.

2. **Re-fetch PR metadata via the API** inside the `workflow_run` job and check
   that the PR author is a collaborator or that the PR is approved before doing
   anything privileged:
   ```yaml
   - name: Verify PR is approved
     env:
       GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
     run: |
       PR_NUMBER=$(gh api repos/${{ github.repository }}/commits/${{ github.event.workflow_run.head_sha }}/pulls --jq '.[0].number')
       APPROVED=$(gh api repos/${{ github.repository }}/pulls/$PR_NUMBER/reviews --jq '[.[] | select(.state=="APPROVED")] | length')
       if [ "$APPROVED" -eq 0 ]; then echo "No approval — exiting"; exit 1; fi
   ```

3. **Restrict `permissions:` to the minimum needed** — even with `workflow_run`,
   set explicit read-only or specific write scopes at the job level.

4. **Prefer `pull_request` with `pull_request_target` only if you understand
   the fork-execution model** — and even then, gate on labels or approvals
   before running build scripts from the PR.

## Gotchas

- `workflow_run` does **not** re-trigger if the upstream workflow is re-run
  manually unless you use the API; the event only fires once per completed run.
- The `github.event.workflow_run.head_branch` for PR-triggered runs is a
  **special `refs/pull/<n>/merge` ref**, not the contributor's actual branch
  name — code that string-matches branch names will silently break.
- GitHub does **not** send `workflow_run` events to forks** — only the base
  repo receives them, so testing in a fork will never fire the downstream job.
- If the triggering workflow is **disabled** or its YAML is deleted from the
  default branch, `workflow_run` silently stops firing with no error or alert.
- The `workflow_run` event payload contains `workflow_run.conclusion` — always
  check it equals `"success"` before acting; a failed upstream run still fires
  the event with `conclusion: "failure"`.
- Rate limits: a busy repo with many PRs can generate hundreds of
  `workflow_run` events per hour, each consuming a queued-job slot and minutes.
- Self-hosted runners receiving `workflow_run` jobs from untrusted upstream
  workflows inherit the full runner environment — isolate these runners or use
  GitHub-hosted ephemeral runners for the privileged leg.

## Sources

- [Triggering a workflow: workflow_run (GitHub Docs)](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#workflow_run)
- [Hardening GitHub Actions: Lessons from Recent Attacks (Wiz)](https://www.wiz.io/blog/github-actions-security-guide)
- [GitHub Actions Security Best Practices Cheat Sheet (GitGuardian)](https://blog.gitguardian.com/github-actions-security-cheat-sheet/)
- [Security hardening for GitHub Actions (GitHub Docs)](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions)
