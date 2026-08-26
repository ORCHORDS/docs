# codeowners-advanced-2026

**Issue:** A team has a CODEOWNERS file but no one reviews PRs consistently. The file has 5 entries. The team has 30 contributors. The "owners" don't know they're owners. PRs wait 3 weeks for review.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

CODEOWNERS is a GitHub feature, not a culture. The 2026 default is CODEOWNERS + a documented review rotation + a Slack channel for unblocking + branch protection enforcing.

## Root cause

CODEOWNERS alone doesn't get PRs reviewed. The 2026 production pattern is the full review system: CODEOWNERS, branch protection, review rotation, escalation, and "ask in chat if blocked" conventions.

## The 4 required GitHub settings

For CODEOWNERS to work, 4 settings must be in place.

1. **CODEOWNERS file** in `/.github/CODEOWNERS`, `docs/CODEOWNERS`, or root
2. **Branch protection** "Require review from Code Owners" on protected branches
3. **Required reviewers** count (typically 1-2)
4. **CODEOWNERS syntax** with valid patterns

The 4 settings are minimum; without them, CODEOWNERS is documentation only.

## The 5 CODEOWNERS syntax elements

| Element | Example | Meaning |
|---|---|---|
| Pattern | `/docs/` | path glob |
| Owner | `@myorg/team-docs` | team or user |
| Comment | `# docs team` | optional, ignored |
| Last match wins | `/apps/web/ @org/web-team` then `/apps/ @org/all` | both apply, more specific wins |
| Negation | `!/apps/experimental/` | exception (not owner) |

The 5 elements cover the standard syntax. Last-match-wins is the most-misunderstood; the 2026 default is to put the most specific pattern last.

## The 5-section CODEOWNERS template

```
# Lines starting with # are comments
# Each line is a path pattern and one or more owners

# Default owners for everything (last match wins, so this is the fallback)
/                                          @myorg/platform-team

# Frontend
/apps/web/                                 @myorg/web-team
/apps/web/src/auth/                        @myorg/security-team
/apps/mobile/                              @myorg/mobile-team

# Backend
/services/api/                             @myorg/api-team
/services/workers/                         @myorg/workers-team

# Infrastructure
/infra/                                    @myorg/infra-team
/.github/workflows/                        @myorg/devops-team
/docker-compose.yml                        @myorg/infra-team
/k8s/                                      @myorg/infra-team

# Documentation
/docs/                                     @myorg/docs-team
README.md                                  @myorg/docs-team
*.md                                       @myorg/docs-team

# Sensitive files
/secrets/                                  @myorg/security-team
*.env                                      @myorg/security-team
```

The 5 sections: defaults, frontend, backend, infrastructure, sensitive. The pattern is layered; most specific last.

## The 5 ownership patterns

| Pattern | When | Example |
|---|---|---|
| Team ownership | most code | `@myorg/api-team` |
| Individual ownership | single owner per file | `@alice` |
| Shared ownership | cross-team | `@myorg/web-team @myorg/design-team` |
| Optional review | non-blocking | `[Optional] @myorg/perf-team` |
| Default owner | catch-all | `*  @myorg/triage-team` |

The 5 patterns cover team, individual, shared, optional, and default.

## The 5-step implementation

1. **Map code to teams** — for each major directory, identify the owning team
2. **Write CODEOWNERS** — `/.github/CODEOWNERS` with the mapping
3. **Configure branch protection** — "Require review from Code Owners" on `main`
4. **Notify teams** — Slack/email each team; confirm the GitHub team membership
5. **Set the review rotation** — which team member reviews when the primary is out

The 5 steps take 1-2 days; the discipline takes months.

## The 5 best practices

1. **Owners are teams, not individuals.** `@myorg/api-team` not `@alice`. Team rotation handles vacations.
2. **Specific patterns last.** Last match wins; put `/apps/web/auth/ @security-team` after `/apps/web/ @web-team`.
3. **The default owner is for triage.** `* @myorg/triage-team` catches PRs that don't match a more specific pattern.
4. **Document the rotation.** A `REVIEWERS.md` or wiki page names who reviews when.
5. **CODEOWNERS is not the whole review system.** Combine with PR templates, branch protection, escalation.

## The 5 anti-patterns

1. **CODEOWNERS file but no branch protection.** CODEOWNERS is documentation only; PRs merge without review.
2. **Individual owners only.** Alice is on vacation; PRs wait.
3. **Too many owners per file.** Every owner is a review; 5 owners = 5 reviews required.
4. **No rotation.** The "owner" is the same person every PR; burnout.
5. **Sensitive files not in CODEOWNERS.** Security team not in CODEOWNERS for `/secrets/` or `*.env`.

## The 4 required-status-check rules

Beyond CODEOWNERS, 4 status checks reinforce the review.

1. **CI passes** — tests, lint, type check
2. **Signed commits** — for supply chain integrity
3. **No force-push** — branch protection
4. **Linear history** — squash or rebase merges

The 4 rules are standard for protected branches; CODEOWNERS is the 5th.

## The 4 escalation rules

When a PR is stuck, 4 escalation paths.

1. **24 hours no review** → ping in the team's Slack channel
2. **48 hours no review** → ping the team's lead or manager
3. **72 hours no review** → reassign to a default reviewer (e.g., the team lead)
4. **1 week no review** → merge with explicit approval from lead + post-merge review

The 4 escalations prevent the "3-week wait" failure mode. Document them; automate the pings.

## The 5 GitHub teams to set up

A 2026 production GitHub org has 5+ teams.

1. **Engineering / engineering-team** — all engineers
2. **Frontend / web-team** — web engineers
3. **Backend / api-team** — backend engineers
4. **Infrastructure / infra-team** — DevOps / SRE
5. **Security / security-team** — security engineers

CODEOWNERS references teams; the teams have members. The pattern scales as the org grows.

## The 3 CODEOWNERS debugging tips

1. **Use the GitHub CODEOWNERS validator.** `https://github.com/REPO/CODEOWNERS` shows the active file.
2. **Test the path glob.** Create a test file in the path; check the PR for the expected reviewer.
3. **Check the "Request review from code owners" UI.** The PR page shows who is requested; the CODEOWNERS resolved list is visible.

The 3 tips catch most CODEOWNERS issues.

## The 5-step CODEOWNERS rollout

1. **Pilot on 1 repo.** Get 1 team, 1 CODEOWNERS file, 1 PR through the system.
2. **Measure review time.** Before/after; the metric is "median time to first review."
3. **Iterate.** Fix path patterns that don't match; fix teams that don't have members.
4. **Roll out to other repos.** Same pattern, team-specific files.
5. **Quarterly review.** Teams change; CODEOWNERS should match the current org.

The 5 steps are a quarter, not a sprint.

## The 5 best practices for sensitive code

For sensitive files (secrets, auth, encryption):

1. **Owners are the security team** — not the dev team
2. **Pattern is broad** — `/secrets/`, `*.env`, `**/credentials*`
3. **2 required reviewers** — not 1
4. **PR template emphasizes security review** — separate from regular review
5. **CODEOWNERS + secret scanning** — the second catches what the first misses

The 5 practices are the security baseline; teams adapt to their threat model.

## Verification

The tell that CODEOWNERS is well-implemented:

- A CODEOWNERS file is in `/.github/CODEOWNERS`
- Branch protection "Require review from Code Owners" is on
- All code paths have an owner; no `*` is the only entry
- The median time to first review is <24 hours
- Sensitive files have a specific security owner

The tell it isn't:

- CODEOWNERS file but no branch protection
- Long wait times for reviews
- "The owner is on vacation" is a common phrase
- Sensitive files don't have a security owner
- CODEOWNERS owners are individuals, not teams

## Gotchas

- **Last match wins.** The order in CODEOWNERS matters; put specific patterns last.
- **Teams need members.** `@myorg/team` with no members means no review is required.
- **CODEOWNERS is enforced by branch protection.** Without the setting, the file is documentation.
- **The PR page shows the resolved owners.** Use it to verify the pattern matches.
- **CODEOWNERS doesn't require approvals; it requires reviews.** Branch protection handles the count.

## Related

- `worktree/branch-protection-codeowners-2026.md` — branch protection
- `worktree/signed-commits-2026.md` — commit signing
- `worktree/pr-templates-2026.md` — PR templates
- `worktree/release-please-semantic-release.md` — release automation

## Source URLs (verified 2026-08-10)

- https://docs.github.com/en/repositories/creating-and-managing-repositories/about-code-owners — CODEOWNERS docs
- https://docs.github.com/en/repositories/creating-and-managing-repositories/managing-rulesets-for-a-repository — rulesets
- https://docs.github.com/en/organizations/organizing-members-into-teams — GitHub teams
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches — branch protection
- https://docs.github.com/en/organizations/organizing-members-into-teams/creating-a-team — team creation
- https://github.blog/developer-skills/github/how-to-write-a-great-pull-request-description/ — PR description
- https://www.codesee.io/learning-center/knowledge-base/pull-request-best-practices — PR best practices
- https://backstage.spotify.com/blog/practical-guide-to-pr-reviews/ — PR review guide
