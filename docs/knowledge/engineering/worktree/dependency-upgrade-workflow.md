# dependency-upgrade-workflow

**Issue:** Dependencies go months without updates, then a security CVE forces a panicked bulk upgrade
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The package.json hasn't been touched in 8 months. Dependabot opens 47 PRs at once. Upgrading major versions breaks the build. The team spends a full sprint on dependency remediation instead of features.

## Pattern / Solution
Treat dependency upgrades as a continuous, low-friction process rather than an occasional emergency.

**Automation setup (Renovate or Dependabot):**
```json
// renovate.json
{
  "schedule": ["every weekend"],
  "automerge": true,
  "automergeType": "pr",
  "packageRules": [
    {
      "matchUpdateTypes": ["patch"],
      "automerge": true
    },
    {
      "matchUpdateTypes": ["minor"],
      "automerge": false,
      "labels": ["dependency-minor"]
    },
    {
      "matchUpdateTypes": ["major"],
      "automerge": false,
      "labels": ["dependency-major"],
      "assignees": ["@tech-lead"]
    }
  ]
}
```

**Manual upgrade workflow for major versions:**
1. Read the changelog / migration guide
2. Upgrade in isolation (separate PR from any feature work)
3. Run the full test suite; address failures before merging
4. Check bundle size impact for frontend deps
5. Document breaking changes in the PR description

**Security CVE response SLA:**
| Severity | Response time |
|----------|--------------|
| Critical | Patch and deploy within 24h |
| High | Patch within 72h |
| Medium | Fix within next sprint |
| Low | Schedule in backlog |

**Audit commands:**
```bash
npm audit --audit-level=high
pip-audit
trivy image myapp:latest
```

## Gotchas
- Automerge for patch-only is safe only if you have good test coverage — verify before enabling
- "Peer dependency" mismatches block npm upgrades; use `--legacy-peer-deps` only as a last resort
- Lock files (`package-lock.json`, `yarn.lock`) must be committed; otherwise upgrades aren't reproducible

## Related
- `shift-left-security-testing.md`
- `sbom-slsa-2026.md`
- `dependabot-renovate-2026.md`
