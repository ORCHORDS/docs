# never-store-secrets-in-env-files

**Issue:** Secrets committed in .env files leak through git history even after deletion
**Date:** 2026-08-11
**Status:** documented

## What happened
A developer committed a `.env` file containing a production database password. The file was removed in the next commit, but git history retained it. Three months later, a public mirror of the repo was created. A security researcher found the credential using `git log -S`. The password had never been rotated because "the file was deleted." Full database contents were accessible for 90 days.

## The lesson
Secrets must never enter the repository, not even briefly. Use a secrets manager (Vault, AWS Secrets Manager, GCP Secret Manager) and inject secrets at runtime via environment variables set by your deployment platform, not by files on disk. Add `.env` to `.gitignore` globally and pre-commit hooks that scan for secrets.

## Why it matters
Git history is forever. Deleting a file does not delete its history. Any clone, mirror, or fork carries the secret. Rotation is the only cure but is often skipped because "we deleted the file."

## How to apply
- [ ] Add `.env`, `*.pem`, `*.key`, `*_rsa` to `.gitignore` and the global gitignore.
- [ ] Install a pre-commit secret scanner (e.g., `detect-secrets`, `gitleaks`) that blocks commits containing high-entropy strings.
- [ ] Store secrets in a secrets manager and reference them by name, never by value, in code.
- [ ] Run `git log -S <secret>` in CI to catch secrets that slip through.
- [ ] Rotate any secret immediately upon discovery that it was committed, regardless of how briefly.

## Related
- `rotate-credentials-after-every-breach.md`
- `security-review-before-not-after.md`
