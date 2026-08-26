# github-rulesets-2026

**Issue:** Using GitHub Rulesets (the successor to branch protection rules) for flexible, layered repo governance
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Legacy branch protection rules are repo-scoped and don't compose well across an org. Rulesets (GA in 2024, expanded in 2025–2026) replace them with org-wide, layered, bypassable policies that apply to branches and tags.

## Pattern / Solution
Rulesets live at org level (apply to all/selected repos) or repo level. Multiple rulesets stack — more restrictive rules win.

**Create a repo ruleset via API:**
```bash
gh api repos/OWNER/REPO/rulesets \
  --method POST \
  --input - <<'EOF'
{
  "name": "main-branch-protection",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "include": ["refs/heads/main", "refs/heads/release/**"],
      "exclude": []
    }
  },
  "bypass_actors": [
    {"actor_id": 5, "actor_type": "Team", "bypass_mode": "pull_request"}
  ],
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {"type": "pull_request",
     "parameters": {
       "required_approving_review_count": 1,
       "dismiss_stale_reviews_on_push": true,
       "require_code_owner_review": true,
       "require_last_push_approval": true
     }},
    {"type": "required_status_checks",
     "parameters": {
       "required_status_checks": [{"context": "test"}, {"context": "lint"}],
       "strict_required_status_checks_policy": false
     }},
    {"type": "required_signatures"}
  ]
}
EOF
```

**Org-level ruleset (applies to all repos matching a pattern):**
- Created in Org Settings → Rules → Rulesets
- Can target repos by name pattern, topic, or visibility

**Enforcement modes:**
- `active` — enforced; violations are blocked
- `evaluate` — violations are logged but not blocked (dry-run mode)
- `disabled` — ruleset inactive

**Bypass actors:**
Specific teams, roles, or apps can be granted bypass in `pull_request` mode (only via PRs) or `always` mode (including direct pushes).

**Listing active rulesets for a branch:**
```bash
gh api repos/OWNER/REPO/rules/branches/main
```

## Gotchas
- Legacy branch protection rules and Rulesets coexist — GitHub evaluates both; the stricter rule wins
- `evaluate` mode is invaluable before enforcing a new org-wide ruleset — run it for a sprint to catch false positives
- Bypass actors granted `always` mode can push directly to protected branches — audit regularly
- Tag rulesets use `target: "tag"` — branches and tags have separate rulesets
- `required_signatures` requires all commits be GPG or SSH signed; this can break bots that don't sign commits

## Related
- `branch-protection-and-codeowners.md`
- `github-required-status-checks.md`
- `github-merge-queue.md`
