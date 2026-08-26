# secret-scanning-2026

**Issue:** A team accidentally commits an AWS access key. The team uses gitleaks, trufflehog, GitHub secret scanning. The team needs the 2026 reference for secret scanning and prevention.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 secret scanning layers

1. **Pre-commit.** gitleaks pre-commit hook blocks the commit.
2. **Pre-push / pre-receive.** gitleaks or trufflehog in git hooks.
3. **CI scan.** gitleaks-action, trufflehog on every PR.
4. **Repo-wide scan.** GitHub secret scanning, GitLab secret detection, periodic trufflehog.
5. **Runtime detection.** AWS GuardDuty, Azure Defender finding anomalous use of a leaked key.

## The 5-step adoption pattern

1. **Enable GitHub secret scanning** (free for public repos, paid for private).
2. **Add gitleaks pre-commit hook** for developer-time catch.
3. **Add gitleaks-action in CI** for catch at PR time.
4. **Rotate any historical leaks** found in git history (BFG Repo-Cleaner, git filter-repo).
5. **Set up runtime detection** for the cloud account to catch any leaked key in use.

## The 5 best practices

1. **Custom patterns** for org-specific tokens (not just generic AWS keys).
2. **Allow-list** for test fixtures, examples, documentation.
3. **Block push, not just warn.** Soft warnings get ignored.
4. **Rotation runbook** ready before the first leak.
5. **Pre-receive hooks** on protected branches for fast feedback.

## The 5 anti-patterns

1. **Relying only on GitHub secret scanning** (private repos need paid plan).
2. **Allowing test credentials to leak** by pattern-only detection.
3. **Rewriting history** without rotating the leaked secret. The key is still valid.
4. **No runbook for rotation** when a leak is found.
5. **Storing secrets in environment variables in CI logs** (some scanners miss these).

## Gotchas

- BFG and git filter-repo can rewrite history but force-push breaks shared branches.
- GitHub's "push protection" blocks commits with known patterns.
- Custom patterns have high false-positive rates; tune with allow-list.
- Some scanners only check committed files, not staged vs unstaged.
- gitleaks 8.0+ uses TOML config; older versions used `.gitleaks.toml`.

## Source URLs (verified 2026-08-10)

- https://github.com/gitleaks/gitleaks
- https://github.com/trufflesecurity/trufflehog
- https://docs.github.com/en/code-security/secret-scanning
- https://rtyley.github.io/bfg-repo-cleaner/
- https://github.com/newren/git-filter-repo
