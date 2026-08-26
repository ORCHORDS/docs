# secrets-detection-git-history

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A developer commits a `.env` file and pushes to GitHub. GitHub secret
scanning emails an alert within 30 seconds: `CLOUDFLARE_API_TOKEN` is
now public. Removing the file in a follow-up commit does not help —
the secret remains in the prior commit and public-repository crawlers
have likely already indexed it. Rotating the token requires
invalidating a live production key.

## Context

Secrets in git history are permanently accessible: every clone, fork,
and archive holds the full history. Even in private repositories, any
collaborator who cloned before the push retains the secret. `git
revert` does not help — the bytes remain in the history object.
Remediation requires both immediate rotation and history rewriting.
Prevention requires scanning before the push leaves the developer's
machine.

## Tool comparison — gitleaks, TruffleHog, git-secrets

| Tool | Scope | Custom rules | CI-ready |
|---|---|---|---|
| gitleaks | Full history + pre-commit | TOML config | Yes |
| TruffleHog | Deep entropy + regex | Yes | Yes |
| git-secrets | Pre-commit, AWS focus | Regex | Yes |

**gitleaks** is the recommended default: covers pre-commit scanning
and full history audits, integrates with GitHub Actions, and ships
curated patterns for 150+ secret types.

```bash
# Scan the full repo history
gitleaks detect --source . --log-opts="--all"

# Scan only staged changes (pre-commit mode)
gitleaks protect --staged

# SARIF output for GitHub Security tab
gitleaks detect --source . --report-format sarif \
  --report-path gitleaks.sarif
```

## Pre-commit hooks for scanning

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.21.2
    hooks:
      - id: gitleaks
```

```bash
pre-commit install          # install for all developers
pre-commit run gitleaks --all-files   # run manually
```

```toml
# .gitleaks.toml — allowlist known false positives
[allowlist]
  description = "Known test fixtures"
  paths = ["tests/fixtures/", "docs/examples/"]
  regexes = ["EXAMPLE_KEY_DO_NOT_USE"]
```

## GitHub secret scanning push protection

Enable at the organization level:
`Settings → Code security → Secret scanning → Push protection`

GitHub scans every push for 200+ token patterns and blocks the push
when a match is found. Bypasses are possible with a reason code;
audit them weekly at `Settings → Code security → Secret scanning →
Bypasses`.

## Remediation when a secret is committed

**Step 1 — Rotate the secret immediately.** Rewriting history is
slower than a live credential exploit.

```bash
# Cloudflare: revoke at dash.cloudflare.com/profile/api-tokens
# Then update the new token in GitHub Actions secrets and
# wrangler secrets — never in wrangler.toml or .dev.vars
```

**Step 2 — Rewrite history with git filter-repo.**

```bash
pip install git-filter-repo

# Remove a file from all history
git filter-repo --path .env --invert-paths

# Replace a secret string with a placeholder
git filter-repo \
  --replace-text <(echo "actualSecret==>REDACTED")

# Force-push all branches after rewriting
git push --force-with-lease origin main
```

**Step 3 — Notify all collaborators.** Anyone who cloned before the
rewrite must re-clone. Assume the secret was already harvested.

## Anti-patterns

- Using `git revert` as remediation — the secret persists in history.
- Relying on `.gitignore` for previously tracked files.
- Using `git filter-branch` — deprecated; use `git filter-repo`.
- Skipping rotation and only rewriting history.
- Storing secrets in `wrangler.toml [vars]` — they are plain-text
  in source control; use `wrangler secret put` instead.

## Gotchas

- **Hooks are bypass-able.** `git commit --no-verify` skips them.
  CI scanning is mandatory as a backstop.
- **False positives cause hook fatigue.** Maintain a `.gitleaks.toml`
  allowlist for test fixtures; review it quarterly.
- **History rewrites invalidate all branches.** Coordinate during a
  freeze window when no PRs are open.
- **Forks retain history.** A public fork captures the secret before
  the rewrite. Treat any public exposure as a confirmed compromise.

## Verification

- `gitleaks detect --source . --log-opts="--all"` exits 0 on main
  after a history rewrite.
- `.dev.vars` is in `.gitignore` and `git log --all -- .dev.vars`
  returns no results.
- GitHub `Settings → Code security → Secret scanning` shows zero
  open alerts.
- A test commit with a fake high-entropy string triggers the
  pre-commit hook and is rejected before reaching the index.

## Related

- `security/secrets-detection-pre-commit.md`
- `security/git-history-secret-removal.md`
- `security/api-key-rotation-zero-downtime.md`
- `security/secrets-encryption-at-rest.md`
- `security/gitleaks-cloudflare-webhook.md`

## Source URLs (verified 2026-08-17)

- https://github.com/gitleaks/gitleaks
- https://github.com/newren/git-filter-repo
- https://docs.github.com/en/code-security/secret-scanning/about-secret-scanning
- https://docs.github.com/en/code-security/secret-scanning/push-protection-for-repositories-and-organizations
- https://pre-commit.com/
- https://trufflesecurity.com/trufflehog
