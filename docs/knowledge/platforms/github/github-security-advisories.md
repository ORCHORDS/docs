# github-security-advisories

**Issue:** Creating and managing GitHub Security Advisories for responsible disclosure
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A vulnerability is reported privately. The team needs to coordinate a fix, request a CVE, and publish the advisory — all without exposing the vulnerability before a patch is available.

## Pattern / Solution
GitHub Security Advisories (GSA) provide a private collaboration space for vulnerability remediation with built-in CVE request support.

**Creating a draft advisory (UI: Security → Advisories → New draft):**
- Title: brief vulnerability description
- CVE ID: request from GitHub (free, 1–3 days) or bring your own
- CVSS score: calculated from the vector you provide
- CWE: weakness enumeration category
- Affected packages: ecosystem, package name, vulnerable version range, patched version

**Via API:**
```bash
gh api repos/OWNER/REPO/security-advisories \
  --method POST \
  --field summary="SQL injection in user search endpoint" \
  --field description="The search parameter is not sanitized..." \
  --field severity="high" \
  --field 'vulnerabilities[0][package][ecosystem]=npm' \
  --field 'vulnerabilities[0][package][name]=@myorg/api' \
  --field 'vulnerabilities[0][vulnerable_version_range]="< 2.1.3"' \
  --field 'vulnerabilities[0][patched_versions]="2.1.3"'
```

**Temporary private fork for fix development:**
The advisory UI offers "Start a temporary private fork" — a private fork linked to the advisory where collaborators can develop and review the patch without exposing it in the public repo.

**Publishing the advisory:**
```bash
gh api repos/OWNER/REPO/security-advisories/GHSA-xxxx-xxxx-xxxx \
  --method PATCH \
  --field state=published
```

**Typical disclosure timeline:**
1. Receive report → create draft advisory
2. Invite reporter as collaborator
3. Develop fix in temporary private fork
4. Request CVE
5. Coordinate disclosure date with reporter
6. Merge fix, publish advisory, tag release

## Gotchas
- Published advisories are permanent and indexed by GHSA ID — draft carefully before publishing
- The temporary private fork is deleted when the advisory is published
- Only repo admins and security managers can create advisories
- GitHub auto-requests a CVE when you publish if you didn't bring your own — this can take 1–3 business days
- Dependabot alerts for the advisory only fire after publishing, not during draft

## Related
- `github-secret-scanning.md`
- `github-code-scanning-codeql.md`
- `github-dependency-review.md`
