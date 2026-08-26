# github-secret-scanning

**Issue:** Detecting and remediating secrets accidentally committed to GitHub repos
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A developer commits an API key or token to a public repo. GitHub Secret Scanning detects known patterns (AWS keys, Stripe tokens, GitHub PATs, etc.) and can alert or block the push.

## Pattern / Solution
Secret Scanning is enabled by default for public repos. For private/internal repos it requires GitHub Advanced Security (GHAS).

**Enable via Settings → Security → Secret scanning:**
- Enable alerts
- Enable push protection (blocks commits containing secrets)
- Configure notification recipients

**Push protection (blocks before push reaches GitHub):**
When push protection is enabled, a `git push` containing a known secret pattern is rejected:
```
remote: error: GH013: Repository rule violations found for refs/heads/main.
remote: - GITHUB SECRET SCANNING PUSH PROTECTION
remote:   —— GitHub Personal Access Token ——————————————————————————————
remote:    locations:
remote:      - commit: abc123
remote:        path: config/settings.py:12
remote:   To push, remove secret from commit history or bypass with justification.
```

**Bypassing push protection (with justification):**
```bash
# The push URL is provided in the error; open it in browser to provide justification
# Or use --allow-empty commit trick to bypass (requires "bypass secret scanning" permission)
```

**Custom secret patterns (regex):**
```bash
gh api repos/OWNER/REPO/secret-scanning/custom-patterns \
  --method POST \
  --field name="Internal API Key" \
  --field pattern='MYAPP-[A-Z0-9]{32}' \
  --field secret_type="myapp_api_key"
```

**Listing detected secrets:**
```bash
gh api repos/OWNER/REPO/secret-scanning/alerts \
  --jq '.[] | {state, secret_type, html_url}'
```

**Remediating a detected secret:**
1. Revoke the secret immediately at the provider (don't wait)
2. Remove from git history: `git filter-repo --path <file> --invert-paths`
3. Force push (coordinate with team)
4. Resolve the alert in the UI

## Gotchas
- Revoking the secret is the first priority — even if you remove it from git history, it may have been seen by GitHub's scan engine or mirrored by bots within seconds of the push
- `git filter-repo` is the modern replacement for `git filter-branch` and BFG — use it
- Push protection can be bypassed by users with appropriate permissions — it's a soft gate, not a hard block
- Secret Scanning only scans the default branch and pull request branches — old branches with secrets may remain unscanned
- Custom patterns apply to new pushes and existing content — enabling a new pattern triggers a re-scan of the full repo history

## Related
- `github-security-advisories.md`
- `github-code-scanning-codeql.md`
- `github-actions-secrets-management.md`
