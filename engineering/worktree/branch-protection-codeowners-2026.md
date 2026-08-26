# branch-protection-codeowners-2026

**Issue:** A developer pushes directly to `main`. A junior engineer merges a PR without review. A security-sensitive file is changed without security team approval. The team has no enforcement; conventions are wishful thinking.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Conventions without enforcement are suggestions. "We require two reviewers" is ignored when the merge button is one click away. "Security must review auth files" is bypassed when the security team is asleep.

## Root cause

Branch protection rules + CODEOWNERS files are the GitHub-native enforcement mechanism. They turn conventions into hard requirements: a PR cannot be merged without the right approvals, the right status checks, and (optionally) the right code owners signing off.

## The 5 branch protection settings

For `main` (and any release branch):

1. **Require pull request before merging** — no direct pushes
2. **Require approvals** — at least 2 for production
3. **Require review from Code Owners** — CODEOWNERS must approve
4. **Dismiss stale pull request approvals when new commits are pushed** — prevents sneak-in changes after approval
5. **Require status checks to pass before merging** — CI must be green

Plus:

- **Require linear history** — squash or rebase merges only
- **Include administrators** — even admins follow the rules
- **Block force pushes** — no rewriting history
- **Block branch deletion** — no accidental `git push origin --delete main`

## The CODEOWNERS file

A plain-text file mapping file patterns to GitHub users or teams:

```gitignore
# .github/CODEOWNERS

# Default owners for everything
*                          @myorg/platform-team

# Frontend
/frontend/                 @myorg/frontend-team
/frontend/components/      @myorg/design-system-team

# Backend
/backend/api/              @myorg/backend-team
/backend/auth/             @myorg/security-team
/backend/payments/         @myorg/payments-team @myorg/security-team

# Infrastructure
/infra/                    @myorg/devops-team
/.github/workflows/        @myorg/devops-team
/terraform/                @myorg/devops-team @myorg/security-team

# Documentation
/docs/                     @myorg/docs-team
*.md                       @myorg/docs-team

# Specific files
SECURITY.md                @myorg/security-team
/package.json              @myorg/release-team
```

**The last matching pattern wins.** This is the most important rule. A pattern for `*.md` followed by a pattern for `README.md` lets the second override the first for that specific file.

## The branch protection + CODEOWNERS binding

CODEOWNERS defines ownership (who is asked to review). Branch protection enforces review. The two are independent: a CODEOWNERS file alone doesn't block merge; branch protection with "Require review from Code Owners" does.

Enable in GitHub: Settings → Branches → Branch protection → Require review from Code Owners.

## The required reviewer rule (2026)

GitHub's required reviewer rule (generally available February 2026) is a stricter, organization-level alternative to CODEOWNERS for sensitive code:

```yaml
# GitHub Ruleset
- target: branch:main
  rules:
    - type: required_reviewers
      reviewers:
        - team: security-team
        - team: data-platform-team
      file_patterns:
        - '**/*.sql'
        - 'auth/**'
        - '!auth/tests/**'
```

You can require specific approvals on sensitive branches and critical code paths, scaling across repos, organizations, or the entire enterprise. Supports negation patterns using `!` (like `.gitignore`).

The required reviewer rule augments CODEOWNERS but doesn't replace it. CODEOWNERS is still the best for ownership and individual reviewer assignment.

## The CODEOWNERS requirements for review

For CODEOWNERS to function:

1. **Listed users must have at least Read access.** Contributors with no access don't receive review requests.
2. **For required approvals, users must have Write or Maintain access.** Read access is for comments; Write is for approval.
3. **Teams must have explicit repo access.** Listing a team with no access has no effect.
4. **Organization teams only.** `@org/team-name` only works in organization repos.
5. **The base branch of the PR uses its CODEOWNERS.** A PR to a fork uses the fork's CODEOWNERS.

## The five-enforcement policy

| Setting | Recommendation |
|---|---|
| Default branch protection on `main` | Required |
| PRs required (no direct push) | Required |
| Approvals | 2 for production, 1 for staging |
| CODEOWNERS review | Required for sensitive paths |
| Status checks | All required, no skip |
| Squash or rebase merge | Required (linear history) |
| Force push blocked | Required |
| Admin bypass | Disabled (admins follow rules) |
| Stale approval dismissal | Enabled |
| Branch deletion | Blocked |

## The CODEOWNERS maintenance pattern

- Version-control `CODEOWNERS` in the `.github/` directory
- Require 2 approvals on changes to `CODEOWNERS` (prevent single-engineer hijack)
- Assign a primary team (e.g., `@myorg/platform-team`) as the wildcard owner
- Quarterly review of team membership and file mappings
- Document the rationale for sensitive paths (e.g., why `/backend/auth/` requires security)

```gitignore
# Protect CODEOWNERS itself
/.github/CODEOWNERS         @myorg/platform-team
```

## The verification

The tell that branch protection + CODEOWNERS is working:

- A direct push to `main` is rejected
- A PR without 2 approvals cannot be merged
- A PR to `/backend/auth/` cannot be merged without security team approval
- A push that breaks CI is rejected
- Stale approvals are dismissed on new commits
- Admins cannot bypass the rules

The tell it isn't:

- A developer can push directly to `main`
- A PR merges with 0 or 1 approvals
- The security team learns about auth changes after merge
- A status check failure does not block merge
- The team has a "we tried to enforce but it's too annoying" culture

## Gotchas

- **CODEOWNERS file must be under 3 MB.** Larger files are silently not loaded.
- **Last matching pattern wins.** A general `*` rule followed by a specific rule lets the specific override.
- **Branch protection is per-branch.** `main`, `release/*`, and `develop` need separate rules.
- **Required reviewers must have Write access.** Read-only is for comments.
- **CODEOWNERS on base branch is what matters.** PRs use the base branch's version.
- **Required reviewer rule vs CODEOWNERS:** use both. CODEOWNERS for assignment, required reviewer for sensitive paths.
- **Admin bypass is the #1 reason conventions fail.** Include administrators in the policy.
- **Stale approval dismissal is non-negotiable.** A push after approval resets the review; without this, sneak-in changes slip through.

## Related

- `worktree/conventional-commits-2026.md` — clean commits
- `worktree/release-please-semantic-release.md` — automated versioning
- `worktree/husky-lint-staged.md` — local pre-commit gates
- `worktree/git-rerere.md` — conflict resolution for long-lived branches

## Source URLs (verified 2026-08-10)

- https://github.blog/changelog/2026-02-17-required-reviewer-rule-is-now-generally-available/
- https://docs.github.com/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners
- https://www.youtube.com/watch?v=emt8s5smrjc
- https://tenthirtyam.org/dispatches/2026/03/25/codeowners-automating-code-review-ownership/
- https://www.arnica.io/blog/what-every-developer-should-know-about-github-codeowners
