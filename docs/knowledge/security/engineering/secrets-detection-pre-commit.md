# secrets-detection-pre-commit

**Issue:** Hardcoded secrets committed to git are immediately at risk even if quickly removed from HEAD
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Developers accidentally commit API keys, database passwords, or private keys. Even if the secret is removed in a follow-up commit, it remains in git history and is often already indexed by GitHub's secret scanning or public repository crawlers within seconds.

## Pattern / Solution
```bash
# Install pre-commit hook with detect-secrets
pip install detect-secrets pre-commit

# .pre-commit-config.yaml
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']

# Initialize baseline (allowlist known false positives)
detect-secrets scan > .secrets.baseline

# Or use gitleaks
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.4
    hooks:
      - id: gitleaks
```
```bash
# Install for all developers
pre-commit install  # installs hooks into .git/hooks/pre-commit

# CI enforcement — scan entire history
gitleaks detect --source . --log-opts="--all"
```

## Gotchas
- Pre-commit hooks can be bypassed with `git commit --no-verify` — enforce with CI scanning too.
- False positives from test fixtures and example configs cause hook fatigue — maintain a baseline/allowlist.
- GitHub Advanced Security secret scanning catches secrets on push but after-the-fact — pre-commit is the first line.
- `.env.example` files with placeholder values still trigger some scanners — use clearly non-secret placeholders like `YOUR_API_KEY_HERE`.

## Related
- `git-history-secret-removal.md`
- `api-key-rotation-zero-downtime.md`
- `secrets-encryption-at-rest.md`
