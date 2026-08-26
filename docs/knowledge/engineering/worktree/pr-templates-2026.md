# pr-templates-2026

**Issue:** A team reviews PRs. Each PR is a wall of code with no context. The reviewer asks "what does this do?" 3 times. The PR is approved without the reviewer understanding. The CI passes. Production breaks.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

PR templates are the highest-leverage free tool in 2026. They force the author to provide context, link issues, document the test plan, and flag the migration story. The cost is 5 minutes per PR; the savings is hours of review time.

## Root cause

Without a template, PRs default to "no description." The reviewer has to read every diff line to understand intent. With a template, the author pre-loads the context the reviewer needs.

## The 8-section PR template

A 2026 production PR template has 8 sections.

```markdown
## What
One-paragraph summary of the change. What does the code do?

## Why
L1 cite: the specific mechanism that motivated the change. Link to issue, RFC, or bug.

## Scope
What this PR does NOT do. Explicit out-of-scope list.

## What's inside
- File-by-file change summary
- Notable design decisions
- Links to relevant code (file_path:line_number format)

## How to verify
- Test plan (unit / integration / E2E / manual)
- Commands to run locally
- Screenshots / recordings for UI changes
- Acceptance criteria checklist

## Risks
- What could go wrong
- Backwards-incompatibility impact
- Migration story for users
- Rollback plan

## Follow-up
- Known TODOs (link to issues)
- Future improvements
- "Don't merge yet if X isn't done"

## Per lessons applied
For self-improving-agent PRs: which fleet lessons informed this change.
```

The 8 sections take the author 5-15 minutes to fill. The reviewer reads the description in 30 seconds and has full context.

## The 5-section lightweight variant

For teams that find the 8-section template heavy.

```markdown
## What
## Why
## How to verify
## Risks
## Follow-up
```

The 5 sections are the minimum useful PR description. The full 8 sections are the discipline-strong version.

## The PR template file

GitHub: `.github/pull_request_template.md`
GitLab: `.gitlab/merge_request_templates/Default.md`
Bitbucket: default pull request description

The file is auto-populated when a new PR is opened. The author fills it in.

## The 4 PR size limits

| Limit | Lines | Review time |
|---|---|---|
| Optimal | <200 | <30 minutes |
| Acceptable | <400 | <1 hour |
| Hard limit | <800 | 1-2 hours, often needs split |
| Unacceptable | >1000 | split required |

The 2026 research: PRs over 400 lines have 2-3x the defect rate of PRs under 200 lines. Split early.

## The 5 review disciplines

1. **Review the description first.** If the What / Why is unclear, ask before reading the diff.
2. **Review the tests.** A PR without tests is incomplete; push back.
3. **Review the migration story.** A breaking change without a migration guide is not done.
4. **Review the rollback plan.** A feature without a rollback is a risk.
5. **Review for scope creep.** A PR that touches 3 unrelated areas should be split.

The 5 disciplines take 5 minutes to learn and save hours per PR.

## The 3 anti-patterns

1. **No template.** Every PR is a wall of code; every review starts from zero.
2. **Vague descriptions.** "Fix bug" / "Refactor" / "Update" without context. The template's What/Why sections force specificity.
3. **Large PRs with no test plan.** A 2000-line PR with "tested locally" is unverifiable.

## The CODEOWNERS + template combination

The 2026 production pattern combines CODEOWNERS (who must review) with the PR template (what the review needs to cover).

The CODEOWNERS file maps paths to owners; the PR template ensures each PR has the context the owner needs. The owner can request changes based on the template, not the diff.

## The bot / automation PR exception

Bot PRs (dependabot, renovate, GitHub Actions automation) get a shorter template.

```markdown
## What
Automated dependency update. See linked PR / commit.

## How to verify
- CI passes
- Review the diff for breaking changes (major version bumps)

## Risks
Major version bumps may include breaking changes; see release notes.
```

The shorter template respects the bot's purpose (mechanical update) while ensuring the reviewer checks for breaking changes.

## The PR description as documentation

A well-written PR is a permanent record of why a change was made. Use the PR description for:

- The Why — the context that disappears when the issue tracker changes
- The Risks — what to watch in production
- The Follow-up — what's still TODO

The PR description outlives the branch. Use it well.

## The merge commit discipline

The merge commit should reference the PR. The squash commit message should include the PR title + a brief summary.

```
feat(auth): add OAuth2 PKCE flow (#1234)

Adds PKCE to the OAuth2 flow for public clients.
Migration: no breaking changes; existing flows continue to work.
Refs: ABC-123
```

The squash commit message is searchable. Future maintainers find the PR via the message.

## Verification

The tell that PR templates are real:

- `.github/pull_request_template.md` exists and is enforced
- Every PR has What / Why / How to verify / Risks
- PR size is monitored (median <200 lines)
- The review process has documented disciplines
- The bot PR exception is short and specific

The tell it isn't:

- No template; PRs default to "no description"
- 1000+ line PRs are routine
- "Fixed" / "Updated" descriptions
- No test plan in PRs
- No risks section

## Gotchas

- **Templates can be ignored.** GitHub only auto-populates; the author can clear it. Enforce via PR review (template is the first check).
- **Multiple templates per repo.** GitHub supports multiple templates in `.github/PULL_REQUEST_TEMPLATE/` directory. Useful for bot vs human vs hotfix.
- **The 200-line limit is approximate.** A 400-line PR with clear sections is fine; a 200-line PR with no description is not.
- **The "Why" is the most important section.** If the reviewer can't explain the Why after reading, the PR isn't ready.
- **The "Risks" section makes the team think.** Writing "what could go wrong" surfaces issues before merge.

## Related

- `worktree/branch-protection-codeowners-2026.md` — the protection rules
- `worktree/branch-strategies-2026.md` — branch patterns
- `worktree/conventional-commits-2026.md` — commit message format
- `worktree/release-please-semantic-release.md` — release automation

## Source URLs (verified 2026-08-10)

- https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/creating-a-pull-request-template-for-your-repository
- https://docs.gitlab.com/user/project/description_templates/
- https://github.blog/developer-skills/github/how-to-write-a-great-pull-request-description/
- https://www.pullrequest.com/blog/how-to-write-a-pull-request-description/
- https://www.codesee.io/learning-center/knowledge-base/pull-request-best-practices
- https://backstage.spotify.com/blog/practical-guide-to-pr-reviews/
- https://github.com/ai/r/git-tips
- https://conventionalcomments.org/ — review comment format
