# github-security-policy-file

**Issue:** Creating a SECURITY.md file to define vulnerability reporting procedures
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Without a security policy, researchers report vulnerabilities as public issues, exposing users before a fix is ready.

## Pattern / Solution
`.github/SECURITY.md` (or `SECURITY.md` in root):
```markdown
# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 2.x     | Yes       |
| 1.x     | No        |

## Reporting a Vulnerability

Do not open a public GitHub issue for security vulnerabilities.

Report security issues via GitHub's private vulnerability reporting:
1. Go to the Security tab of this repository.
2. Click "Report a vulnerability".
3. Fill in the details.

Alternatively, email security@example.com with subject line
`[SECURITY] <brief description>`.

We aim to acknowledge reports within 48 hours and provide a fix
timeline within 7 days.

## Disclosure Policy

We follow coordinated disclosure. We will credit reporters in release
notes unless anonymity is requested.
```
Enable private vulnerability reporting:
- Settings → Security → Private vulnerability reporting → Enable.

## Gotchas
- GitHub shows a "Report a vulnerability" button on the Security tab only when private reporting is enabled.
- SECURITY.md in `.github/` of the special org `.github` repo applies org-wide.
- Include a PGP key for encrypted email reports if handling high-severity CVEs.
- Link SECURITY.md in your README so it is discoverable.

## Related
- `github-security-advisories.md`
- `github-advanced-security-setup.md`
- `github-ghas-code-scanning.md`
