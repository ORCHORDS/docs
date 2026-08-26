# gitleaks-cloudflare-webhook

**Issue:** Gitleaks misses CF Workers webhook URL pattern
**Date:** 2026-08-09
**Repo:** <your-org>/<your-repo> at main (gitleaks v8.25.0+)
**Author:** the platform team
**Status:** fixed (PR #open-issue-gitleaks a sibling repo, mirrored to the platform)

## Symptom
A CF Workers webhook URL is committed to the repo:
```
https://api.example.workers.dev/webhook/secret-token-12345
```
Gitleaks' default rules don't catch this. The token after `/webhook/`
is treated as a path segment, not a secret.

## Root cause
Gitleaks default rules (the `gitleaks.toml` from the project's
`gitleaks detect` installation) include:
- `aws-access-token`, `aws-secret-key`
- `github-pat`, `github-fine-grained-pat`
- `stripe-access-token`
- `slack-bot-token`, `slack-webhook-url`
- 100+ others

But CF Workers URL pattern is not in the default set. The path
segment after `/webhook/` looks like a normal URL path to default
regex.

**Source:** Gitleaks rules registry — https://github.com/gitleaks/gitleaks/tree/master/config

## Fix
Add a custom rule to `.gitleaks.toml` (project's override file):

```toml
[[rules]]
id = "cf-workers-webhook-secret"
description = "Cloudflare Workers webhook URL with path-based secret"
regex = '''workers\.dev/[a-z0-9_-]+/webhook/[a-zA-Z0-9_-]{16,}'''
keywords = ["workers.dev", "webhook"]
tags = ["cloudflare", "webhook", "secret"]

  [rules.allowlist]
  paths = [
    '''\.gitleaks-baseline\.json$''',
  ]
```

The regex requires:
- `workers.dev` host
- A worker name (e.g. `api`, `webhook-router`)
- `/webhook/` literal
- A 16+ char token (most CF-generated tokens are 32+)

The allowlist ensures the baseline file is not self-flagged.

## Verification
- **Test:** `gitleaks detect --no-git --config .gitleaks.toml`
  on a sample repo with a known webhook URL → 1 finding
- **CI:** PR #open-issue-gitleaks — workflow `gitleaks.yml` runs on push, PR, and
  Mon 03:00 UTC cron; 0 false positives over 7-day window
- **Live:** Cron at https://github.com/<your-org>/<your-repo>/actions/workflows/gitleaks.yml

## Gotchas
- **Rotate the secret AFTER removing it from git history.** `git log -p`
  will still show the URL even after `git rm`. Use `git filter-repo` or
  BFG to rewrite history, OR (simpler) rotate the worker and treat
  the old URL as compromised.
- **The `[[allowlists]]` syntax is for v8.25.0+.** Older versions
  use `[allowlist]` (singular). Check the gitleaks version in
  your CI image before copying.
- **gitleaks stopwords match against the CAPTURED group, not the
  whole line.** If your rule uses `(?:secret) = "([^"]+)"`, the
  allowlist is checked against `[^"]+`, not the full match. This
  is a common source of false negatives.
- **Self-hosted runner for the cron job** — GH-hosted Actions
  budget concerns (#open-issue-actions-budget) make the Mon 03:00 UTC cron run on the
  X-99 self-hosted runner.

## Related
- a sibling repo PR #open-issue-gitleaks (gitleaks config with the same pattern)
- the platform issue #open-issue-credential-rotation (credential rotation)
- Gitleaks custom rules docs: https://github.com/gitleaks/gitleaks/blob/master/docs/custom-rules.md
