# GitHub Actions `pull_request_target` Trigger Poisoning

`pull_request_target` is the most dangerous trigger in GitHub Actions. It was
created to let CI run against pull requests from forks **with access to
secrets**, but it executes the workflow file from the **base branch** (default
branch), not the PR's fork. The moment you add a `run:` step or a build action
that checks out the PR code, an attacker can execute arbitrary code in a
secrets-privileged context. This is a top-tier supply-chain attack vector.

## Symptom

- A security audit, Dependabot security alert, or external researcher reports
  that your `pull_request_target` workflow is vulnerable to arbitrary code
  execution from forks.
- A bot or labeler workflow worked fine for months, then someone added a
  "helpful" `run: npm ci && npm test` step to it — that single edit turned a
  safe automation into an RCE path for any fork.
- You see unexpected secret exfiltration patterns (outbound calls to unknown
  hosts) in your audit log shortly after a suspicious PR was opened.
- GitHub's own security scanner or a tool like StepSecurity Harden-Runner
  flags outbound network calls during a `pull_request_target` job.

## Why it happens

`pull_request_target` provides: a `GITHUB_TOKEN` with write permissions (as
configured on the base branch), access to all repo secrets, and execution of
the base-branch workflow YAML. The workflow *definition* is safe, but anything
that acts on untrusted PR content is not.

The classic poison pattern:
```yaml
# DANGEROUS — checks out fork code and runs it with secrets
on: pull_request_target
jobs:
  test:
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}  # fork code!
      - run: npm install   # runs package.json scripts from the fork
```
Any `preinstall`/`postinstall` script in the fork's `package.json` now runs
with your secrets in `env`.

## Fix

1. **Never checkout PR code and run build/test steps in a `pull_request_target`
   job.** If you need to run CI against fork code, use `pull_request` (which is
   sandboxed — no secrets) instead.

2. **If you must use `pull_request_target` for label/comment automation, treat
   the PR as untrusted data, not code:**
   ```yaml
   on: pull_request_target
   jobs:
     label:
       runs-on: ubuntu-latest
       permissions:
         pull-requests: write
       steps:
         # NO checkout of PR code
         - uses: actions/labeler@v5
           with:
             repo-token: ${{ secrets.GITHUB_TOKEN }}
   ```

3. **Gate any privileged action behind a maintainer label:**
   `if: contains(github.event.pull_request.labels.*.name, 'safe-to-test')`

4. **Use `pull_request` + `workflow_run`** for "run fork code, then do something
   privileged on success" — the `workflow_run` leg can re-verify the PR state
   before touching secrets (see the `workflow_run` security KB article).

## Gotchas

- Adding `permissions: {}` (empty) to the job does **not** make checkout-and-run
  safe — the problem is the code execution, not the token scope. The fork's
  build scripts can still read files, scan the runner filesystem, and phone home.
- The `github.event.pull_request.head.repo.full_name` for a fork PR points to a
  repo the attacker controls; checking out `head.sha` without `ref:` still
  resolves to the fork's commit.
- GitHub auto-disables `pull_request_target` workflows on a repo if it detects
  abuse, but this is reactive — the first malicious PR may already have run.
- `issue_comment` + `/test` bot commands have the **same risk** if they checkout
  and run the PR branch; the comment event has write token + secrets by default.
- Dependabot PRs run on the same base-branch workflow for `pull_request_target`,
  so they are "trusted" by definition — but a compromised Dependabot ecosystem
  action could still exploit this trust boundary.
- Reviewers who run the workflow locally via `act` will **not** reproduce the
  fork execution context — the vulnerability only manifests in GitHub's hosted
  environment, making it hard to catch in local testing.

## Sources

- [Keeping your GitHub Actions and workflows secure Part 1: Preventing pwn requests (GitHub Security Lab)](https://securitylab.github.com/research/github-actions-preventing-pwn-requests/)
- [Events that trigger workflows: pull_request_target (GitHub Docs)](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#pull_request_target)
- [Security hardening for GitHub Actions (GitHub Docs)](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions)
- [Top 10 GitHub Actions Security Pitfalls (Arctiq)](https://arctiq.com/blog/top-10-github-actions-security-pitfalls-the-ultimate-guide-to-bulletproof-workflows)
