# github-secret-scanning-custom-patterns

**Issue:** Defining custom secret patterns for GitHub secret scanning beyond the built-in detectors
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
GitHub ships ~200 built-in secret patterns (AWS keys, GitHub tokens, etc.). Custom patterns let you detect internal tokens or proprietary credential formats.

## Pattern / Solution
Via org or repo Settings → Security → Secret scanning → Custom patterns → New pattern:
```
Pattern name: Internal API Key
Secret format: myapp_[a-zA-Z0-9]{32}
Test string: myapp_abc123XYZ789def456GHI012jkl345
```
Via API:
```bash
gh api -X POST \
  /orgs/myorg/secret-scanning/custom-patterns \
  -f name="Internal API Key" \
  -f pattern='myapp_[a-zA-Z0-9]{32}'
```
Dry-run to check for existing matches before enabling:
- Click "Save and dry run" in the UI to see historical matches before activating alerts.

## Gotchas
- Custom patterns are PCRE2 regular expressions.
- Patterns that are too broad produce high false-positive volumes — test thoroughly.
- Push protection can be enabled per custom pattern; this blocks pushes containing matches.
- Dry-run scans historical commits; enabling the pattern produces alerts for all existing matches.
- Organisation-level patterns apply to all repos; repo-level patterns are local only.

## Related
- `github-secret-scanning.md`
- `github-advanced-security-setup.md`
