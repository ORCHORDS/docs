# branch-protection-and-codeowners

**Issue:** Branch protection + CODEOWNERS — review enforcement
**Date:** 2026-08-09
**Status:** documented

## Symptom
Anyone can push to main. A bad commit breaks production.
Reviews are optional. The senior dev is paged. You
wish you had enforced reviews.

## Root cause
**Without protection, anyone can merge.** Use
branch protection + CODEOWNERS.

**Source:** GitHub docs:
https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners

## The "branch protection" concept

Branch protection is the gate:
- **Required PR:** No direct push
- **Required reviews:** N approvals
- **Required CI:** Tests pass
- **Required CODEOWNERS:** Right experts
- **Block force push:** History preserved

The gate is enforced.

## The "recommended protection" pattern

For main branch:
```
☑ Require PR before merging
☑ Required approvals: 1-2
☑ Dismiss stale approvals
☑ Require review from Code Owners
☑ Require approval of most recent push
☑ Require status checks
☑ Require branches to be up to date
☑ Require conversation resolution
☑ Block force pushes
☑ Block deletions
☑ Do not allow bypassing (even admins)
```

The main is protected.

## The "CODEOWNERS" concept

CODEOWNERS maps paths to owners:
- **Auto-assign:** When PR touches a path
- **Required approval:** Before merge
- **Expert review:** Domain knowledge

The owners are mapped.

## The "CODEOWNERS file" pattern

For the file:
```
# File: .github/CODEOWNERS

# Default owners (everything)
* @org/maintainers

# Frontend
/src/components/ @frontend-team
/src/pages/ @frontend-team
*.tsx @frontend-team
*.css @frontend-team

# Backend
/src/api/ @backend-team
/src/services/ @backend-team

# Infrastructure
/terraform/ @platform-team
/docker/ @platform-team

# Security sensitive
/src/auth/ @security-team @backend-team
/src/payments/ @security-team

# CI/CD
/.github/ @devops-team
```

The owners are per path.

## The "CODEOWNERS syntax" pattern

For syntax:
- **Pattern:** Same as .gitignore
- **Owners:** Users or teams
- **Last match wins:** Precedence
- **No negation:** Unlike .gitignore
- **Wildcard:** `*` matches anything

The syntax is gitignore-like.

## The "team vs user" pattern

For owners:
- **Use teams:** Not individual users
- **Why:** Survives team changes
- **Permission:** Write or Maintain

The teams are stable.

## The "CODEOWNERS location" pattern

For the file location (in priority order):
1. `.github/CODEOWNERS` (recommended)
2. `CODEOWNERS` (root)
3. `docs/CODEOWNERS`

The location is `.github/CODEOWNERS`.

## The "branch protection via Terraform" pattern

For Terraform:
```hcl
resource "github_branch_protection" "main" {
  repository_id = github_repository.example.id
  pattern       = "main"

  required_pull_request_reviews {
    required_approving_review_count = 2
    dismiss_stale_reviews           = true
    require_code_owner_reviews      = true
  }

  required_status_checks {
    strict   = true
    contexts = ["ci/test", "ci/lint", "ci/build"]
  }

  enforce_admins = true
}
```

The protection is code.

## The "ruleset" pattern

For newer rulesets:
```
Repository → Settings → Rules → Rulesets
New ruleset:
  Name: "Production Protection"
  Enforcement: Active
  Target branches: main, release/*
  Rules:
    - Require linear history
    - Require signed commits (optional)
    - Require PR
    - Require status checks
    - Block force pushes
```

The ruleset is the modern way.

## The "emergency bypass" pattern

For emergencies:
```
Bypass list:
  - Repository admins
  - Specific teams (e.g., Release Team)
  - Deploy keys
```

The bypass is defined + reviewed.

## The "CODEOWNERS errors" pattern

For errors:
- **Path:** Repository → Insights → Code owners errors
- **Issue:** Owner doesn't have write permission
- **Fix:** Grant write or change owner

The errors are visible.

## The "dismiss stale" pattern

For stale approvals:
- **Issue:** Approve, push new commit, merge
- **Fix:** Dismiss stale approvals
- **Result:** Re-review required

The stale is dismissed.

## The "require conversation resolution" pattern

For comments:
- **Issue:** Open comments on PR
- **Fix:** Require resolution
- **Result:** No unresolved comments

The conversations are resolved.

## The "branch protection anti-pattern" anti-patterns

### 1. No protection
- **Issue:** Anyone can merge
- **Fix:** Protect main

### 2. Admins bypass
- **Issue:** Rules don't apply
- **Fix:** enforce_admins = true

### 3. Optional CI
- **Issue:** Broken code ships
- **Fix:** Required status checks

### 4. No CODEOWNERS
- **Issue:** Wrong reviewers
- **Fix:** Map paths to teams

### 5. Force push allowed
- **Issue:** History lost
- **Fix:** Block force push

## The "CODEOWNERS anti-pattern" anti-patterns

### 1. Individual users
- **Issue:** User leaves, ownership gone
- **Fix:** Use teams

### 2. Empty teams
- **Issue:** No review possible
- **Fix:** Ensure team has members

### 3. No global fallback
- **Issue:** Uncovered paths
- **Fix:** Add `* @org/team` as first line

### 4. Too many owners
- **Issue:** Review fatigue
- **Fix:** One team per path

## Verification
- **Test:** Branch is protected
- **Test:** CODEOWNERS is enforced
- **Test:** Admins follow rules
- **Live:** PRs require reviews
- **Audit:** Quarterly review

## Gotchas
- **The "no protection" anti-pattern.** Always protect.
- **The "admins bypass" anti-pattern.** enforce_admins.
- **The "individual users" anti-pattern.** Use teams.

## Related
- `github/github-actions-reusable-workflows.md`
- `github/pr-template-and-issue-templates.md`
- `github/dependabot-config.md`
- `github/pat-self-merge-workaround.md`
- GitHub docs: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners
- DevToolHub: https://devtoolhub.com/github-codeowners-permissions-best-practices/
- GitScrum: https://docs.gitscrum.com/en/best-practices/configuring-branch-protection-rules
